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

# ── Priority queue for yfinance rate limiting ──────────────────────────────────
PRIORITY_HIGH   = 1   # user-facing interactive (analysis tab)
PRIORITY_MEDIUM = 2   # user-initiated, less urgent (watchlist, charts)
PRIORITY_LOW    = 3   # background batch (recommendations, S&P 500 bulk)


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
    _SUBMIT_TIMEOUT  = 60.0   # max seconds a caller blocks

    def __init__(self):
        self._pq               = queue.PriorityQueue()
        self._seq              = itertools.count()
        self._last_call        = 0.0
        self._call_count       = 0
        self._call_count_reset = 0.0
        self._worker = threading.Thread(target=self._run, daemon=True, name='yfinance-queue-worker')
        self._worker.start()

    def submit(self, fn, priority=PRIORITY_MEDIUM):
        """
        Enqueue *fn* at *priority* and block until the worker executes it.

        Returns the return value of fn(), or re-raises any exception fn raised.
        Raises TimeoutError if the worker does not execute within _SUBMIT_TIMEOUT.
        """
        event  = threading.Event()
        holder = {}  # mutable container for result or exception
        enqueue_ts = time.time()
        seq = next(self._seq)
        self._pq.put((priority, seq, fn, event, holder, enqueue_ts))
        signalled = event.wait(timeout=self._SUBMIT_TIMEOUT)
        if not signalled:
            raise TimeoutError(f'yfinance queue timeout after {self._SUBMIT_TIMEOUT}s')
        if 'exc' in holder:
            raise holder['exc']
        return holder.get('result')

    def _run(self):
        """Worker loop — executes queued functions with rate-limiting."""
        while True:
            try:
                priority, seq, fn, event, holder, enqueue_ts = self._pq.get()

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
                                self._pq.put((priority, seq, fn, event, holder, enqueue_ts))
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
                if now - self._call_count_reset > 60:
                    if self._call_count > 0:
                        logger.info('yfinance calls in last minute: %d', self._call_count)
                    self._call_count = 0
                    self._call_count_reset = now
                self._call_count += 1
                self._last_call = time.time()

                # ── Execute ────────────────────────────────────────────────
                try:
                    holder['result'] = fn()
                except Exception as exc:
                    holder['exc'] = exc
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


def _queue_call(fn, priority=PRIORITY_MEDIUM):
    """Submit *fn* to the yfinance queue and return its result."""
    return _yf_queue.submit(fn, priority=priority)


_RETRY_DELAY = 3        # seconds to wait after a rate-limit hit
_MAX_RETRIES = 3        # retry attempts per yfinance attribute


def _fetch_with_retry(fn, label, priority=PRIORITY_MEDIUM):
    """Call *fn()* via the queue up to _MAX_RETRIES times, retrying on rate-limit errors."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return _queue_call(fn, priority=priority)
        except Exception as exc:
            msg = str(exc).lower()
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
            return entry['data']
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
        return cached

    fetch_start = start - timedelta(days=_MAX_WARMUP_DAYS)
    stock = _get_ticker(ticker)
    hist = _queue_call(lambda: stock.history(start=fetch_start, end=end), priority=priority)

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
        return cached

    stock = _get_ticker(ticker)
    info = _queue_call(lambda: stock.info, priority=priority)
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
        return cached

    stock = _get_ticker(ticker)
    try:
        cal = _queue_call(lambda: stock.get_earnings_dates(limit=limit), priority=priority)
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
        return cached

    spy = _get_ticker('SPY')
    hist = _queue_call(lambda: spy.history(start=start, end=end), priority=priority)

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
        return cached

    spy = _get_ticker('SPY')
    hist = _queue_call(lambda: spy.history(period=period), priority=priority)

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
        return cached

    stock = _get_ticker(ticker)
    data = {}

    pt = _fetch_with_retry(lambda: stock.analyst_price_targets, f'{ticker} price_targets', priority=priority)
    if pt:
        data['price_targets'] = pt

    rs = _fetch_with_retry(lambda: stock.recommendations_summary, f'{ticker} recommendations_summary', priority=priority)
    if rs is not None and hasattr(rs, 'empty') and not rs.empty:
        data['recommendations_summary'] = rs

    ud = _fetch_with_retry(lambda: stock.upgrades_downgrades, f'{ticker} upgrades_downgrades', priority=priority)
    if ud is not None and hasattr(ud, 'empty') and not ud.empty:
        data['upgrades_downgrades'] = ud.head(50)

    ee = _fetch_with_retry(lambda: stock.earnings_estimate, f'{ticker} earnings_estimate', priority=priority)
    if ee is not None and hasattr(ee, 'empty') and not ee.empty:
        data['earnings_estimate'] = ee

    re_ = _fetch_with_retry(lambda: stock.revenue_estimate, f'{ticker} revenue_estimate', priority=priority)
    if re_ is not None and hasattr(re_, 'empty') and not re_.empty:
        data['revenue_estimate'] = re_

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
