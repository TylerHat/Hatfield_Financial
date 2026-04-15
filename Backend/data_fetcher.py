"""
Shared data-fetching layer with in-memory caching.

All routes should use these helpers instead of calling yfinance directly.
This eliminates redundant fetches when the user switches strategies on the
same ticker, and keeps SPY data cached globally.
"""

import itertools
import logging
import queue
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

import yfinance as yf

logger = logging.getLogger(__name__)

# ── yfinance session note ───────────────────────────────────────────────────
# yfinance now uses curl_cffi internally, which is incompatible with
# requests_cache / requests_ratelimiter Session objects.  Do NOT pass a
# custom `session=` to yf.Ticker or yf.download — let yfinance manage its
# own HTTP client.  Rate limiting is handled by the app-level _throttle()
# below, and response caching is handled by the in-process `_cache` dict.

# ── Cache storage ────────────────────────────────────────────────────────────

_cache = {}
_lock = threading.Lock()

# TTLs (seconds)
_OHLCV_TTL = 300       # 5 minutes — covers strategy switching
_INFO_TTL = 1800        # 30 minutes — fundamentals change slowly
_EARNINGS_TTL = 3600    # 1 hour — rarely changes intraday
_SPY_TTL = 600          # 10 minutes — shared across all RS calculations
_ANALYST_TTL = 1800     # 30 minutes — analyst data changes infrequently

# Maximum warmup any strategy needs (mean-reversion, ma-confluence, 52-week)
_MAX_WARMUP_DAYS = 280

# ── yfinance property timeout (seconds) ────────────────────────────────────────
# Prevents hangs when yfinance properties access Yahoo Finance slowly or infinitely
_YFINANCE_PROPERTY_TIMEOUT = 10

# ── Priority queue for yfinance rate limiting ──────────────────────────────────
PRIORITY_HIGH   = 1   # user-facing interactive (analysis tab)
PRIORITY_MEDIUM = 2   # user-initiated, less urgent (watchlist, charts)
PRIORITY_LOW    = 3   # background batch (recommendations, S&P 500 bulk)


def _get_yfinance_property(stock, prop_name, timeout=_YFINANCE_PROPERTY_TIMEOUT):
    """
    Safely access a yfinance Ticker property with a timeout.
    Returns None if the property access times out or raises an exception.
    """
    result = [None]
    exception = [None]

    def access_property():
        try:
            result[0] = getattr(stock, prop_name)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=access_property, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.warning(f'yfinance property {prop_name} timed out after {timeout}s')
        return None

    if exception[0]:
        logger.debug(f'yfinance property {prop_name} failed: {exception[0]}')
        return None

    return result[0]


class YFinanceQueue:
    """
    Single-worker priority queue for all yfinance HTTP calls.

    Callers submit a callable and block on a threading.Event until the
    worker executes it and stores the result. The worker enforces a
    minimum inter-call interval to avoid hitting Yahoo's rate limiter.

    Priority levels (lower int = higher priority):
        PRIORITY_HIGH   = 1   — interactive/user-facing requests
        PRIORITY_MEDIUM = 2   — user-initiated, less urgent
        PRIORITY_LOW    = 3   — background batch operations

    Starvation prevention: items waiting longer than _PROMOTE_AFTER_S
    seconds are promoted one level (3→2, 2→1) on dequeue.
    """

    _CALL_INTERVAL   = 0.6    # seconds between calls (~100 calls/min)
    _PROMOTE_AFTER_S = 30.0   # promote after this many seconds waiting
    _SUBMIT_TIMEOUT  = 15.0   # max seconds a caller blocks (reduced from 60s to fail fast on hangs)

    def __init__(self):
        self._pq               = queue.PriorityQueue()
        self._seq              = itertools.count()
        self._last_call        = 0.0
        self._call_count       = 0
        self._call_count_reset = 0.0
        self._worker = threading.Thread(target=self._run, daemon=True, name='yfinance-queue-worker')
        self._worker.start()

        # ── Recording state (admin API monitoring) ──────────────────────────
        self._record_lock      = threading.Lock()
        self._recording        = False
        self._record_target    = 0        # 5 or 10
        self._record_start_min = None     # unix ts of minute boundary when recording starts
        self._recorded_data    = []       # list of per-minute snapshot dicts
        self._recording_done   = False    # True once N minutes captured

        # ── Per-current-minute counters (reset each minute) ──────────────────
        self._min_successes = 0
        self._min_failures  = 0
        self._min_timeouts  = 0
        self._min_cache_hits   = 0
        self._min_cache_misses = 0
        self._min_endpoint_calls = {}  # dict of {endpoint_type: count}

    def submit(self, fn, priority=PRIORITY_MEDIUM, endpoint_type=None):
        """
        Enqueue *fn* at *priority* and block until the worker executes it.

        Returns the return value of fn(), or re-raises any exception fn raised.
        Raises TimeoutError if the worker does not execute within _SUBMIT_TIMEOUT.

        Parameters
        ----------
        fn : callable
            The function to execute
        priority : int
            Queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
        endpoint_type : str, optional
            Label for monitoring (e.g., 'get_ohlcv', 'get_ticker_info')
        """
        event  = threading.Event()
        holder = {}  # mutable container for result or exception
        enqueue_ts = time.time()
        seq = next(self._seq)
        self._pq.put((priority, seq, fn, event, holder, enqueue_ts, endpoint_type))
        signalled = event.wait(timeout=self._SUBMIT_TIMEOUT)
        if not signalled:
            raise TimeoutError(f'yfinance queue timeout after {self._SUBMIT_TIMEOUT}s')
        if 'exc' in holder:
            raise holder['exc']
        return holder.get('result')

    def start_recording(self, minutes: int):
        """Start a new recording session. Records immediately."""
        with self._record_lock:
            if self._recording:
                return {'status': 'already_recording'}
            # Start recording immediately; first snapshot comes at next minute boundary
            now = time.time()
            self._record_start_min = now  # Start immediately
            self._record_target    = minutes
            self._recorded_data    = []
            self._recording_done   = False
            self._recording        = True
            return {'status': 'started', 'starts_at': now}

    def get_status(self):
        """Return current recording state + captured data."""
        with self._record_lock:
            completed = len(self._recorded_data)
            return {
                'recording':     self._recording,
                'done':          self._recording_done,
                'target':        self._record_target,
                'completed':     completed,
                'starts_at':     self._record_start_min,
                'data':          list(self._recorded_data),  # copy
            }

    def clear_recording(self):
        """Stop and wipe all recorded data."""
        with self._record_lock:
            self._recording      = False
            self._recording_done = False
            self._record_start_min = None
            self._recorded_data  = []
            self._record_target  = 0

    def _run(self):
        """Worker loop — executes queued functions with rate-limiting."""
        while True:
            try:
                item = self._pq.get()
                # Unpack: may have endpoint_type (7 elements) or not (6 elements for backwards compat)
                if len(item) == 7:
                    priority, seq, fn, event, holder, enqueue_ts, endpoint_type = item
                else:
                    priority, seq, fn, event, holder, enqueue_ts = item
                    endpoint_type = None

                # ── Starvation prevention ──────────────────────────────────
                waited = time.time() - enqueue_ts
                if priority > PRIORITY_HIGH and waited > self._PROMOTE_AFTER_S:
                    promoted = max(PRIORITY_HIGH, priority - 1)
                    logger.debug('Promoting item (waited %.1fs): %d→%d', waited, priority, promoted)
                    priority = promoted
                    # Re-insert at promoted priority if there are higher-pri items ahead
                    if not self._pq.empty():
                        try:
                            nxt = self._pq.get_nowait()
                            if nxt[0] < priority:
                                self._pq.put((priority, seq, fn, event, holder, enqueue_ts, endpoint_type))
                                self._pq.put(nxt)
                                continue
                            else:
                                self._pq.put(nxt)
                        except queue.Empty:
                            pass

                # ── Rate gate ──────────────────────────────────────────────
                now = time.time()
                elapsed = now - self._last_call
                if elapsed < self._CALL_INTERVAL:
                    time.sleep(self._CALL_INTERVAL - elapsed)

                # ── Call accounting ────────────────────────────────────────
                now = time.time()
                if now - self._call_count_reset >= 60:
                    # ── capture snapshot if recording ────────────────────────
                    with self._record_lock:
                        if self._recording and not self._recording_done:
                            # Capture if recording started before or at this minute boundary
                            # (now is the current time, and we just hit a new minute boundary)
                            if self._record_start_min and now >= self._record_start_min:
                                snapshot = {
                                    'minute':       datetime.utcfromtimestamp(self._call_count_reset).strftime('%H:%M:%S UTC'),
                                    'total_calls':  self._call_count,
                                    'successes':    self._min_successes,
                                    'failures':     self._min_failures,
                                    'timeouts':     self._min_timeouts,
                                    'cache_hits':   self._min_cache_hits,
                                    'cache_misses': self._min_cache_misses,
                                    'queue_depth':  self._pq.qsize(),
                                    'endpoint_calls': dict(self._min_endpoint_calls),  # copy
                                }
                                self._recorded_data.append(snapshot)
                                if len(self._recorded_data) >= self._record_target:
                                    self._recording      = False
                                    self._recording_done = True

                    # ── log + reset ────────────────────────────────────────
                    if self._call_count > 0:
                        endpoints_str = ', '.join(f'{k}={v}' for k, v in sorted(self._min_endpoint_calls.items()))
                        if endpoints_str:
                            endpoints_str = f' ({endpoints_str})'
                        logger.info('yfinance calls in last minute: %d (ok=%d fail=%d timeout=%d)%s',
                                    self._call_count, self._min_successes, self._min_failures, self._min_timeouts, endpoints_str)
                    self._call_count    = 0
                    self._call_count_reset = now
                    self._min_successes = 0
                    self._min_failures  = 0
                    self._min_timeouts  = 0
                    self._min_cache_hits   = 0
                    self._min_cache_misses = 0
                    self._min_endpoint_calls = {}
                self._call_count += 1
                self._last_call = time.time()

                # ── Execute ────────────────────────────────────────────────
                try:
                    holder['result'] = fn()
                    self._min_successes += 1
                    # Track endpoint type
                    if endpoint_type:
                        self._min_endpoint_calls[endpoint_type] = self._min_endpoint_calls.get(endpoint_type, 0) + 1
                except TimeoutError as exc:
                    self._min_timeouts += 1
                    holder['exc'] = exc
                    if endpoint_type:
                        self._min_endpoint_calls[endpoint_type] = self._min_endpoint_calls.get(endpoint_type, 0) + 1
                except Exception as exc:
                    self._min_failures += 1
                    holder['exc'] = exc
                    if endpoint_type:
                        self._min_endpoint_calls[endpoint_type] = self._min_endpoint_calls.get(endpoint_type, 0) + 1
                finally:
                    event.set()

            except Exception as outer:
                logger.error('YFinanceQueue worker error: %s', outer, exc_info=True)
                try:
                    event.set()
                except Exception:
                    pass


# Module-level singleton
_yf_queue = YFinanceQueue()


def _queue_call(fn, priority=PRIORITY_MEDIUM, endpoint_type=None):
    """Submit *fn* to the yfinance queue and return its result."""
    return _yf_queue.submit(fn, priority=priority, endpoint_type=endpoint_type)


_RETRY_DELAY = 3        # seconds to wait after a rate-limit hit
_MAX_RETRIES = 3        # retry attempts per yfinance attribute


def _fetch_with_retry(fn, label, priority=PRIORITY_MEDIUM, endpoint_type=None):
    """Call *fn()* via the queue up to _MAX_RETRIES times, retrying on rate-limit errors."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return _queue_call(fn, priority=priority, endpoint_type=endpoint_type)
        except Exception as exc:
            msg = str(exc).lower()
            # Skip 404 "No fundamentals data found" errors — some symbols don't have analyst data on Yahoo
            if '404' in msg or 'not found' in msg or 'no fundamentals data' in msg:
                logger.debug('%s not available on Yahoo Finance (404): %s', label, exc)
                return None
            if '429' in msg or 'rate' in msg or 'too many' in msg:
                if attempt < _MAX_RETRIES:
                    logger.warning('%s rate-limited, retrying in %ds (attempt %d/%d)',
                                   label, _RETRY_DELAY, attempt + 1, _MAX_RETRIES)
                    time.sleep(_RETRY_DELAY)
                    continue
                logger.warning('%s rate-limited, exhausted retries', label)
            else:
                logger.debug('%s fetch failed: %s', label, exc)
            return None
    return None


def _cache_get(key, ttl):
    """Return cached value if it exists and hasn't expired, else None."""
    with _lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry['ts']) < ttl:
            _yf_queue._min_cache_hits += 1
            return entry['data']
        _yf_queue._min_cache_misses += 1
        return None


def _cache_set(key, data):
    """Store data with current timestamp."""
    with _lock:
        _cache[key] = {'data': data, 'ts': time.time()}


# ── Ticker object cache ─────────────────────────────────────────────────────
# Reuse the same yf.Ticker object for the same symbol to avoid redundant
# session setup and allow yfinance internal caching.
_ticker_objects = {}
_ticker_lock = threading.Lock()


def _get_ticker(symbol):
    """Get or create a cached yf.Ticker object (yfinance manages its own session)."""
    symbol = symbol.upper()
    with _ticker_lock:
        if symbol not in _ticker_objects:
            _ticker_objects[symbol] = yf.Ticker(symbol)
        return _ticker_objects[symbol]


# ── Public API ───────────────────────────────────────────────────────────────

def get_ohlcv(ticker, start, end, priority=PRIORITY_MEDIUM):
    """
    Fetch OHLCV history for a single ticker with caching.

    Always fetches with the maximum warmup (280 days before `start`) so that
    any strategy can use the result without re-fetching.  The caller trims
    to its own needed window.

    Parameters
    ----------
    ticker : str
    start : datetime   – the user-visible start date
    end : datetime     – the user-visible end date
    priority : int     – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)

    Returns
    -------
    pandas.DataFrame or None
    """
    ticker = ticker.upper()
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')
    key = f'ohlcv:{ticker}:{start_str}:{end_str}'

    cached = _cache_get(key, _OHLCV_TTL)
    if cached is not None:
        # Track endpoint even on cache hit
        _yf_queue._min_endpoint_calls['get_ohlcv'] = _yf_queue._min_endpoint_calls.get('get_ohlcv', 0) + 1
        return cached

    fetch_start = start - timedelta(days=_MAX_WARMUP_DAYS)
    stock = _get_ticker(ticker)
    hist = _queue_call(lambda: stock.history(start=fetch_start, end=end), priority=priority, endpoint_type='get_ohlcv')

    if hist is not None and not hist.empty:
        _cache_set(key, hist)
        return hist
    return None


def get_ticker_info(ticker, priority=PRIORITY_MEDIUM):
    """
    Fetch the .info dict for a ticker with caching (15-min TTL).

    Parameters
    ----------
    ticker : str
    priority : int   – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)

    Returns
    -------
    dict or None
    """
    ticker = ticker.upper()
    key = f'info:{ticker}'

    cached = _cache_get(key, _INFO_TTL)
    if cached is not None:
        # Track endpoint even on cache hit
        _yf_queue._min_endpoint_calls['get_ticker_info'] = _yf_queue._min_endpoint_calls.get('get_ticker_info', 0) + 1
        return cached

    stock = _get_ticker(ticker)
    # Use _fetch_with_retry to handle 404 "No fundamentals data" errors gracefully
    info = _fetch_with_retry(lambda: stock.info, f'{ticker} info', priority=priority, endpoint_type='get_ticker_info')
    if info:
        _cache_set(key, info)
        return info
    return None


def get_earnings_dates(ticker, limit=20, priority=PRIORITY_MEDIUM):
    """
    Fetch earnings dates for a ticker with caching (1-hour TTL).

    Parameters
    ----------
    ticker : str
    limit : int      – max earnings dates to fetch
    priority : int   – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)

    Returns
    -------
    pandas.DataFrame or None
    """
    ticker = ticker.upper()
    key = f'earnings:{ticker}'

    cached = _cache_get(key, _EARNINGS_TTL)
    if cached is not None:
        # Track endpoint even on cache hit
        _yf_queue._min_endpoint_calls['get_earnings_dates'] = _yf_queue._min_endpoint_calls.get('get_earnings_dates', 0) + 1
        return cached

    stock = _get_ticker(ticker)
    try:
        cal = _queue_call(lambda: stock.get_earnings_dates(limit=limit), priority=priority, endpoint_type='get_earnings_dates')
        if cal is not None and not cal.empty:
            _cache_set(key, cal)
            return cal
    except Exception:
        pass
    return None


def get_spy_history(start, end, priority=PRIORITY_MEDIUM):
    """
    Fetch SPY OHLCV with a dedicated 10-min cache.
    Shared across stock_info, relative_strength, and backtest routes.

    Parameters
    ----------
    start : datetime
    end : datetime
    priority : int   – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
    """
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')
    key = f'spy:{start_str}:{end_str}'

    cached = _cache_get(key, _SPY_TTL)
    if cached is not None:
        # Track endpoint even on cache hit
        _yf_queue._min_endpoint_calls['get_spy_history'] = _yf_queue._min_endpoint_calls.get('get_spy_history', 0) + 1
        return cached

    spy = _get_ticker('SPY')
    hist = _queue_call(lambda: spy.history(start=start, end=end), priority=priority, endpoint_type='get_spy_history')

    if hist is not None and not hist.empty:
        _cache_set(key, hist)
        return hist
    return None


def get_spy_period(period='3mo', priority=PRIORITY_MEDIUM):
    """
    Fetch SPY by period string (e.g. '3mo', '1y') with 10-min cache.
    Used by stock_info for relative-strength cards.

    Parameters
    ----------
    period : str     – e.g. '3mo', '1y'
    priority : int   – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
    """
    key = f'spy_period:{period}'

    cached = _cache_get(key, _SPY_TTL)
    if cached is not None:
        # Track endpoint even on cache hit
        _yf_queue._min_endpoint_calls['get_spy_period'] = _yf_queue._min_endpoint_calls.get('get_spy_period', 0) + 1
        return cached

    spy = _get_ticker('SPY')
    hist = _queue_call(lambda: spy.history(period=period), priority=priority, endpoint_type='get_spy_period')

    if hist is not None and not hist.empty:
        _cache_set(key, hist)
        return hist
    return None


def get_analyst_data(ticker, priority=PRIORITY_MEDIUM):
    """
    Fetch analyst-specific data (price targets, recommendation counts,
    upgrades/downgrades, earnings & revenue estimates) with 30-min TTL.

    Parameters
    ----------
    ticker : str
    priority : int   – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)

    Returns
    -------
    dict or None
    """
    ticker = ticker.upper()
    key = f'analyst:{ticker}'

    cached = _cache_get(key, _ANALYST_TTL)
    if cached is not None:
        # Track endpoint even on cache hit
        _yf_queue._min_endpoint_calls['get_analyst_data'] = _yf_queue._min_endpoint_calls.get('get_analyst_data', 0) + 1
        return cached

    stock = _get_ticker(ticker)
    data = {}
    timeout_count = 0

    pt = _fetch_with_retry(lambda: stock.analyst_price_targets, f'{ticker} price_targets', priority=priority, endpoint_type='get_analyst_data')
    if pt:
        data['price_targets'] = pt
    elif pt is None:
        timeout_count += 1

    rs = _fetch_with_retry(lambda: stock.recommendations_summary, f'{ticker} recommendations_summary', priority=priority, endpoint_type='get_analyst_data')
    if rs is not None and hasattr(rs, 'empty') and not rs.empty:
        data['recommendations_summary'] = rs
    elif rs is None:
        timeout_count += 1

    ud = _fetch_with_retry(lambda: stock.upgrades_downgrades, f'{ticker} upgrades_downgrades', priority=priority, endpoint_type='get_analyst_data')
    if ud is not None and hasattr(ud, 'empty') and not ud.empty:
        data['upgrades_downgrades'] = ud.head(50)
    elif ud is None:
        timeout_count += 1

    ee = _fetch_with_retry(lambda: stock.earnings_estimate, f'{ticker} earnings_estimate', priority=priority, endpoint_type='get_analyst_data')
    if ee is not None and hasattr(ee, 'empty') and not ee.empty:
        data['earnings_estimate'] = ee
    elif ee is None:
        timeout_count += 1

    re_ = _fetch_with_retry(lambda: stock.revenue_estimate, f'{ticker} revenue_estimate', priority=priority, endpoint_type='get_analyst_data')
    if re_ is not None and hasattr(re_, 'empty') and not re_.empty:
        data['revenue_estimate'] = re_
    elif re_ is None:
        timeout_count += 1

    # Log if multiple analyst properties timed out (indicates yfinance service issue)
    if timeout_count >= 3:
        logger.error(f'get_analyst_data({ticker}): {timeout_count}/5 properties timed out — Yahoo Finance may be slow or unavailable')

    if data:
        _cache_set(key, data)
    return data if data else None


def get_many_ohlcv(tickers, period='10mo', chunk_size=50, chunk_delay=0.5, priority=PRIORITY_LOW):
    """Bulk OHLCV download for many tickers.

    Returns ``{ticker: DataFrame}``.  Populates the per-ticker ``ohlcv:`` cache
    entries used by ``get_ohlcv`` so later single-ticker reads hit the cache.

    Parameters
    ----------
    tickers : list[str]
    period : str              – yfinance period string (e.g. ``'10mo'``)
    chunk_size : int          – tickers per yf.download call
    chunk_delay : float       – (deprecated) queue handles pacing now
    priority : int            – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
    """
    tickers = [t.upper() for t in tickers]
    result = {}

    for chunk_start in range(0, len(tickers), chunk_size):
        chunk = tickers[chunk_start:chunk_start + chunk_size]
        try:
            raw = _queue_call(
                lambda chunk=chunk: yf.download(
                    chunk,
                    period=period,
                    group_by='ticker',
                    threads=False,  # CRITICAL: threads=False to avoid bypassing queue
                    progress=False,
                ),
                priority=priority,
                endpoint_type='get_many_ohlcv',
            )
        except Exception as exc:
            logger.error('get_many_ohlcv chunk %d-%d failed: %s',
                         chunk_start, chunk_start + len(chunk), exc)
            continue

        # Single-ticker downloads return flat columns; multi returns MultiIndex.
        for t in chunk:
            try:
                if len(chunk) == 1:
                    df = raw.dropna(how='all')
                else:
                    df = raw[t].dropna(how='all')
            except Exception:
                continue
            if df is None or df.empty:
                continue
            result[t] = df

            # Seed per-ticker OHLCV cache so get_ohlcv() hits it later.
            # Use a period-scoped key to avoid colliding with date-ranged keys.
            cache_key = f'ohlcv_period:{t}:{period}'
            _cache_set(cache_key, df)

    return result


def get_spy_1m_return(priority=PRIORITY_MEDIUM):
    """Cached SPY trailing ~1-month % return (last close vs 22 trading days ago).

    Reused by recommendations + user_data routes to avoid three independent
    SPY fetches per page load.  Backed by ``get_spy_period('10mo')`` which has
    its own 10-minute TTL cache.

    Parameters
    ----------
    priority : int   – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
    """
    hist = get_spy_period('10mo', priority=priority)
    if hist is None:
        return None
    close = hist['Close'].dropna()
    if len(close) < 22:
        return None
    return (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100


def clear_cache(prefix=None):
    """Clear all cache entries, or only those matching a key prefix."""
    with _lock:
        if prefix is None:
            _cache.clear()
        else:
            keys = [k for k in _cache if k.startswith(prefix)]
            for k in keys:
                del _cache[k]


def clear_ticker_cache(symbol=None):
    """Clear cached yf.Ticker objects for a symbol (or all if symbol is None).

    This forces yfinance to create fresh Ticker instances and re-fetch data
    from Yahoo Finance. Necessary for 24/7 assets like crypto where cached
    Ticker objects hold stale .info data.
    """
    global _ticker_objects
    with _ticker_lock:
        if symbol is None:
            _ticker_objects.clear()
        else:
            symbol = symbol.upper()
            if symbol in _ticker_objects:
                del _ticker_objects[symbol]
                logger.info(f'Cleared cached Ticker object for {symbol}')
