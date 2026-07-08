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
_INFO_TTL = 600         # 10 minutes — balances price freshness with Yahoo rate limits
_EARNINGS_TTL = 3600    # 1 hour — rarely changes intraday
_SPY_TTL = 600          # 10 minutes — shared across all RS calculations
_ANALYST_TTL = 1800     # 30 minutes — analyst data changes infrequently

# Maximum warmup any strategy needs (mean-reversion, ma-confluence, 52-week)
_MAX_WARMUP_DAYS = 280

# ── yfinance property timeout (seconds) ────────────────────────────────────────
# Prevents hangs when yfinance properties access Yahoo Finance slowly or infinitely
# Reduced to 5s in production where Yahoo is rate-limiting/slow. Better to skip data
# than to block the entire request for 20+ seconds.
_YFINANCE_PROPERTY_TIMEOUT = 5

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

    _CALL_INTERVAL   = 0.3    # seconds between calls (~200 calls/min, was 0.6 to handle burst traffic)
    _PROMOTE_AFTER_S = 30.0   # promote after this many seconds waiting
    # Worker bounds how long the yfinance call itself may run; caller bound is
    # strictly larger so the worker has time to record completion (or a hang)
    # before the caller raises TimeoutError on the wait event.
    _WORKER_CALL_TIMEOUT = 20.0
    _SUBMIT_TIMEOUT      = 30.0

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

    def record_endpoint_call(self, endpoint_type):
        """Increment the per-endpoint counter under the record lock.

        Cache-hit paths (no queue submission) call this from caller threads;
        the worker reads/clears the same dict under the same lock, so plain
        dict mutation from many callers would otherwise risk RuntimeError or
        lost updates.
        """
        if not endpoint_type:
            return
        with self._record_lock:
            self._min_endpoint_calls[endpoint_type] = (
                self._min_endpoint_calls.get(endpoint_type, 0) + 1
            )

    def _run(self):
        """Worker loop — executes queued functions with rate-limiting."""
        while True:
            # Pre-declare so the outer except can safely signal the caller
            # even if dequeue or unpack fails.
            event = None
            try:
                item = self._pq.get()
                # Unpack: may have endpoint_type (7 elements) or not (6 elements for backwards compat)
                if len(item) == 7:
                    priority, seq, fn, event, holder, enqueue_ts, endpoint_type = item
                else:
                    priority, seq, fn, event, holder, enqueue_ts = item
                    endpoint_type = None

                # ── Starvation prevention ──────────────────────────────────
                # If this item has waited too long, bump its priority by one
                # and re-enqueue. The PriorityQueue itself will then re-dequeue
                # the highest-priority item — no manual peek/swap (which races
                # with concurrent producers and can leave the worker holding
                # the wrong item).
                waited = time.time() - enqueue_ts
                if priority > PRIORITY_HIGH and waited > self._PROMOTE_AFTER_S:
                    promoted = max(PRIORITY_HIGH, priority - 1)
                    logger.debug('Promoting item (waited %.1fs): %d→%d', waited, priority, promoted)
                    self._pq.put((promoted, seq, fn, event, holder, enqueue_ts, endpoint_type))
                    continue

                # ── Rate gate ──────────────────────────────────────────────
                now = time.time()
                elapsed = now - self._last_call
                if elapsed < self._CALL_INTERVAL:
                    time.sleep(self._CALL_INTERVAL - elapsed)

                # ── Call accounting ────────────────────────────────────────
                now = time.time()
                if now - self._call_count_reset >= 60:
                    # Snapshot capture + log + reset all touch the per-minute
                    # counters that caller threads also mutate (via
                    # record_endpoint_call). Do them under one record_lock so
                    # iteration / reassignment cannot race with caller writes.
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

                        # ── log + reset ────────────────────────────────────
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
                # Run fn() in a guarded thread so a hanging yfinance call
                # cannot permanently block the worker and stall the entire queue.
                _fn_result = {}
                _fn_exc    = {}

                def _run():
                    try:
                        _fn_result['val'] = fn()
                    except Exception as _e:
                        _fn_exc['exc'] = _e

                _t = threading.Thread(target=_run, daemon=True)
                _t.start()
                _t.join(timeout=self._WORKER_CALL_TIMEOUT)

                try:
                    if _t.is_alive():
                        # fn() is still hanging — move on, do not block the worker
                        self._min_timeouts += 1
                        holder['exc'] = TimeoutError(
                            f'yfinance call hung for {self._WORKER_CALL_TIMEOUT}s, worker moving on'
                        )
                        logger.warning('yfinance call hung after %ss (%s) — worker unblocked',
                                       self._WORKER_CALL_TIMEOUT, endpoint_type or 'unknown')
                    elif 'exc' in _fn_exc:
                        self._min_failures += 1
                        holder['exc'] = _fn_exc['exc']
                    else:
                        holder['result'] = _fn_result.get('val')
                        self._min_successes += 1
                    if endpoint_type:
                        # Use the same lock-taking helper as caller-side cache
                        # hits so writes from this worker thread and the many
                        # caller threads do not race on the dict.
                        self.record_endpoint_call(endpoint_type)
                finally:
                    event.set()

            except Exception as outer:
                logger.error('YFinanceQueue worker error: %s', outer, exc_info=True)
                if event is not None:
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


# Negative cache for tickers that legitimately return no data
# (delisted, halted, ticker typo'd). Without this, every request to
# `get_ticker_info('XYZ')` for an unknown XYZ hits Yahoo's rate limiter
# fresh. Short TTL so a temporarily-bad ticker recovers quickly.
_NEGATIVE_TTL = 60   # seconds — known-bad keys re-check after 1 min
_negative_cache = {}  # key -> timestamp when marked bad


def _is_known_bad(key, ttl=_NEGATIVE_TTL):
    with _lock:
        ts = _negative_cache.get(key)
        if ts is None:
            return False
        if (time.time() - ts) < ttl:
            return True
        del _negative_cache[key]
        return False


def _mark_known_bad(key):
    with _lock:
        _negative_cache[key] = time.time()


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

def get_ohlcv(ticker, start, end, priority=PRIORITY_MEDIUM, warmup_days=None):
    """
    Fetch OHLCV history for a single ticker with caching.

    Fetches `warmup_days` of pre-history before `start` so the caller's
    indicator can stabilise. Defaults to ``_MAX_WARMUP_DAYS`` (280) for
    backwards-compat — that's the right window for MA200 / 52-week /
    mean-reversion strategies. Light strategies (RSI=60, BB=40, RS=20)
    can pass a smaller value to cut Yahoo bandwidth ~30% per call.

    The cache key includes the warmup so different callers don't
    cross-contaminate. A 60-day-warmup caller and a 280-day-warmup
    caller get separate entries.

    Parameters
    ----------
    ticker : str
    start : datetime   – the user-visible start date
    end : datetime     – the user-visible end date
    priority : int     – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
    warmup_days : int  – pre-history days before `start` (default _MAX_WARMUP_DAYS)

    Returns
    -------
    pandas.DataFrame or None
    """
    ticker = ticker.upper()
    if warmup_days is None:
        warmup_days = _MAX_WARMUP_DAYS
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')
    key = f'ohlcv:{ticker}:{start_str}:{end_str}:w{warmup_days}'

    cached = _cache_get(key, _OHLCV_TTL)
    if cached is not None:
        _yf_queue.record_endpoint_call('get_ohlcv')
        return cached

    fetch_start = start - timedelta(days=warmup_days)
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
        _yf_queue.record_endpoint_call('get_ticker_info')
        return cached

    # Negative-cache fast path: tickers that recently returned no data
    # (delisted, halted, typo) skip the Yahoo round-trip for _NEGATIVE_TTL.
    if _is_known_bad(key):
        _yf_queue.record_endpoint_call('get_ticker_info')
        return None

    stock = _get_ticker(ticker)
    # Use _fetch_with_retry to handle 404 "No fundamentals data" errors gracefully
    info = _fetch_with_retry(lambda: stock.info, f'{ticker} info', priority=priority, endpoint_type='get_ticker_info')
    if info:
        _cache_set(key, info)
        return info
    # Cache the negative result so the next caller for this ticker doesn't
    # also burn a Yahoo quota slot.
    _mark_known_bad(key)
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
    # Include `limit` in the cache key so callers asking for different
    # window sizes don't share a cached value. The previous bare
    # f'earnings:{ticker}' key let stock_info (limit=4) and stock_data
    # (limit=20) cross-contaminate — whichever wrote first served a
    # wrong-size DataFrame to the other.
    key = f'earnings:{ticker}:{limit}'

    cached = _cache_get(key, _EARNINGS_TTL)
    if cached is not None:
        _yf_queue.record_endpoint_call('get_earnings_dates')
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
        _yf_queue.record_endpoint_call('get_spy_history')
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
        _yf_queue.record_endpoint_call('get_spy_period')
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
        _yf_queue.record_endpoint_call('get_analyst_data')
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


_INSIDER_TTL = 3600        # 1 hour — insider filings update infrequently
_INSTITUTIONAL_TTL = 3600  # 1 hour — 13F filings are quarterly


def _safe_val(v):
    """Return None for NaN/None, else the value as-is."""
    if v is None:
        return None
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    return v


def _find_col(df_cols, *candidates):
    """
    Return the first column name in df_cols that matches any candidate
    (case-insensitive, ignoring leading # and whitespace).
    """
    normalized = {c.lower().strip().lstrip('#'): c for c in df_cols}
    for candidate in candidates:
        key = candidate.lower().strip().lstrip('#')
        if key in normalized:
            return normalized[key]
    return None


def get_insider_transactions(ticker, limit=10, priority=PRIORITY_MEDIUM):
    """
    Fetch recent insider transactions for a ticker with 1-hour TTL.

    Uses dynamic column detection to handle yfinance version differences:
      - old: filer / shares / value / text / startDate / ownership
      - new: Insider / #Shares / Value / Transaction / Date / Position

    Parameters
    ----------
    ticker : str
    limit : int      – max rows to return
    priority : int   – queue priority

    Returns
    -------
    list[dict] or None
    """
    ticker = ticker.upper()
    key = f'insider:{ticker}'

    cached = _cache_get(key, _INSIDER_TTL)
    if cached is not None:
        _yf_queue.record_endpoint_call('get_insider_transactions')
        return cached

    stock = _get_ticker(ticker)
    try:
        df = _fetch_with_retry(
            lambda: stock.insider_transactions,
            f'{ticker} insider_transactions',
            priority=priority,
            endpoint_type='get_insider_transactions',
        )
        if df is None or (hasattr(df, 'empty') and df.empty):
            logger.debug(f'get_insider_transactions({ticker}): empty or None DataFrame')
            return None

        cols = list(df.columns)
        logger.info(f'get_insider_transactions({ticker}): columns={cols}, rows={len(df)}')

        # Locate each logical field dynamically
        c_filer    = _find_col(cols, 'Insider', 'filer', 'Name')
        c_shares   = _find_col(cols, '#Shares', 'Shares', 'shares', 'Share')
        c_value    = _find_col(cols, 'Value', 'value')
        c_text     = _find_col(cols, 'Transaction', 'text', 'Text', 'Type', 'type')
        c_date     = _find_col(cols, 'Date', 'startDate', 'Start Date', 'Start_Date')
        c_own      = _find_col(cols, 'Ownership', 'ownership', 'Position', 'position')

        rows = []
        for _, row in df.head(limit).iterrows():
            try:
                filer  = _safe_val(row[c_filer])  if c_filer  else None
                shares = _safe_val(row[c_shares]) if c_shares else None
                value  = _safe_val(row[c_value])  if c_value  else None
                text   = _safe_val(row[c_text])   if c_text   else None
                own    = _safe_val(row[c_own])    if c_own    else None

                # Date: may be in the index if it's a DatetimeIndex
                date_val = None
                if c_date:
                    date_val = _safe_val(row[c_date])
                if date_val is None and hasattr(df.index, 'dtype'):
                    # DatetimeIndex — use row's index label
                    idx = row.name
                    if idx is not None:
                        date_val = idx

                entry = {
                    'filer': str(filer) if filer is not None else None,
                    'text':  str(text)  if text  is not None else None,
                    'shares': int(float(shares)) if shares is not None else None,
                    'value':  float(value)       if value  is not None else None,
                    'ownership': str(own) if own is not None else None,
                    'date': str(date_val)[:10] if date_val is not None else None,
                }
                rows.append(entry)
            except Exception as row_exc:
                logger.debug(f'get_insider_transactions({ticker}) row parse error: {row_exc}')
                continue

        if rows:
            _cache_set(key, rows)
            return rows
        logger.warning(f'get_insider_transactions({ticker}): DataFrame had {len(df)} rows but none parsed (cols={cols})')
    except Exception as exc:
        logger.warning(f'get_insider_transactions({ticker}): {exc}')
    return None


def get_institutional_holders(ticker, limit=15, priority=PRIORITY_MEDIUM):
    """
    Fetch institutional holders + major holders summary for a ticker (1-hour TTL).

    Uses dynamic column detection to handle yfinance version differences.
    % Out values are stored as-is from yfinance (already a percentage, e.g. 5.23 = 5.23%).

    Returns a dict with:
      'holders'      – list of dicts (top holders from stock.institutional_holders)
      'major'        – dict of summary stats from stock.major_holders
      'totalCount'   – number of institutional holders (from major_holders)

    Parameters
    ----------
    ticker : str
    limit : int      – max holder rows to return
    priority : int   – queue priority
    """
    ticker = ticker.upper()
    key = f'institutional:{ticker}'

    cached = _cache_get(key, _INSTITUTIONAL_TTL)
    if cached is not None:
        _yf_queue.record_endpoint_call('get_institutional_holders')
        return cached

    stock = _get_ticker(ticker)
    result = {}

    # ── institutional_holders ─────────────────────────────────────────────
    try:
        ih = _fetch_with_retry(
            lambda: stock.institutional_holders,
            f'{ticker} institutional_holders',
            priority=priority,
            endpoint_type='get_institutional_holders',
        )
        if ih is not None and hasattr(ih, 'empty') and not ih.empty:
            cols = list(ih.columns)
            logger.info(f'get_institutional_holders({ticker}): institutional_holders cols={cols}, rows={len(ih)}')

            c_holder = _find_col(cols, 'Holder', 'holder', 'Institution', 'Name')
            c_shares = _find_col(cols, 'Shares', 'shares', '#Shares')
            c_pct    = _find_col(cols, '% Out', 'pctHeld', '% Held', 'pctOut', '% Outstanding')
            c_value  = _find_col(cols, 'Value', 'value')
            c_date   = _find_col(cols, 'Date Reported', 'dateReported', 'Date', 'Report Date')

            rows = []
            for _, row in ih.head(limit).iterrows():
                try:
                    holder  = _safe_val(row[c_holder]) if c_holder else None
                    shares  = _safe_val(row[c_shares]) if c_shares else None
                    pct_raw = _safe_val(row[c_pct])    if c_pct    else None
                    value   = _safe_val(row[c_value])  if c_value  else None
                    date_r  = _safe_val(row[c_date])   if c_date   else None

                    # yfinance returns % Out as a decimal fraction (0.0523 = 5.23%)
                    pct_out = None
                    if pct_raw is not None:
                        pct_f = float(pct_raw)
                        # If value is > 1, it's already a percentage; otherwise multiply by 100
                        pct_out = round(pct_f if pct_f > 1 else pct_f * 100, 2)

                    entry = {
                        'holder': str(holder) if holder is not None else None,
                        'shares': int(float(shares)) if shares is not None else None,
                        'pctOut': pct_out,
                        'value': float(value) if value is not None else None,
                        'dateReported': str(date_r)[:10] if date_r is not None else None,
                    }
                    rows.append(entry)
                except Exception as row_exc:
                    logger.debug(f'get_institutional_holders({ticker}) ih row error: {row_exc}')
                    continue
            if rows:
                result['holders'] = rows
        elif ih is not None:
            logger.debug(f'get_institutional_holders({ticker}): institutional_holders is empty')
    except Exception as exc:
        logger.warning(f'get_institutional_holders({ticker}) institutional_holders: {exc}')

    # ── major_holders ─────────────────────────────────────────────────────
    try:
        mh = _fetch_with_retry(
            lambda: stock.major_holders,
            f'{ticker} major_holders',
            priority=priority,
            endpoint_type='get_institutional_holders',
        )
        if mh is not None and hasattr(mh, 'empty') and not mh.empty:
            cols = list(mh.columns)
            logger.info(f'get_institutional_holders({ticker}): major_holders cols={cols}, rows={len(mh)}')
            major = {}

            for _, row in mh.iterrows():
                try:
                    # Columns vary by yfinance version: integer (0,1) or named ('Value','name')
                    col_list = list(row.index)
                    val_col = col_list[0]
                    lbl_col = col_list[1] if len(col_list) > 1 else None
                    val = row[val_col]
                    lbl = str(row[lbl_col]).lower() if lbl_col else str(row.name).lower()
                    v = _safe_val(val)
                    if v is None:
                        continue
                    fv = float(v)
                    # Convert fraction → percent where needed (values ≤ 1 are fractions)
                    pct = round(fv * 100, 2) if fv <= 1 else round(fv, 2)
                    if 'insider' in lbl:
                        major['insidersPct'] = pct
                    elif 'float' in lbl and 'institution' in lbl:
                        major['institutionsFloatPct'] = pct
                    elif 'institution' in lbl and 'count' not in lbl and 'number' not in lbl:
                        major['institutionsPct'] = pct
                    elif 'count' in lbl or 'number' in lbl:
                        major['institutionsCount'] = int(fv)
                except Exception as row_exc:
                    logger.debug(f'get_institutional_holders({ticker}) mh row error: {row_exc}')
                    continue
            if major:
                result['major'] = major
                if 'institutionsCount' in major:
                    result['totalCount'] = major['institutionsCount']
        elif mh is not None:
            logger.debug(f'get_institutional_holders({ticker}): major_holders is empty')
    except Exception as exc:
        logger.warning(f'get_institutional_holders({ticker}) major_holders: {exc}')

    if result:
        _cache_set(key, result)
        return result
    logger.warning(f'get_institutional_holders({ticker}): no data retrieved from either property')
    return None


def get_many_ohlcv(tickers, period='10mo', chunk_size=50, chunk_delay=0.5, priority=PRIORITY_LOW):
    """Bulk OHLCV download for many tickers.

    Returns ``{ticker: DataFrame}``. Used by the recommendations prewarm
    pipeline which consumes the returned dict directly — it does NOT
    seed the per-ticker date-range cache used by ``get_ohlcv``, because
    that cache keys on ``(ticker, start_str, end_str)`` while a bulk
    period fetch can't predict the start/end strings any future
    per-ticker caller will use. (Prior versions wrote to
    ``ohlcv_period:{t}:{period}``, which nothing ever read.)

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

        raw = None
        for attempt in range(_MAX_RETRIES + 1):
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
                break
            except Exception as exc:
                msg = str(exc).lower()
                retriable = any(s in msg for s in ('429', 'rate', 'too many', 'hung', 'timeout'))
                if attempt < _MAX_RETRIES and retriable:
                    sleep_s = _RETRY_DELAY * (2 ** attempt)
                    logger.warning('get_many_ohlcv chunk %d-%d retry %d/%d in %ds: %s',
                                   chunk_start, chunk_start + len(chunk),
                                   attempt + 1, _MAX_RETRIES, sleep_s, exc)
                    time.sleep(sleep_s)
                    continue
                logger.error('get_many_ohlcv chunk %d-%d failed after %d attempts: %s',
                             chunk_start, chunk_start + len(chunk), attempt + 1, exc)
                raw = None
                break

        if raw is None:
            # Per-ticker fallback so a single bad chunk doesn't drop 50 tickers.
            recovered = 0
            for t in chunk:
                try:
                    single = _queue_call(
                        lambda t=t: yf.download(
                            t,
                            period=period,
                            group_by='ticker',
                            threads=False,
                            progress=False,
                        ),
                        priority=priority,
                        endpoint_type='get_many_ohlcv_single',
                    )
                except Exception:
                    continue
                if single is None or single.empty:
                    continue
                df = single.dropna(how='all')
                if df.empty:
                    continue
                result[t] = df
                # No cache seed — see get_many_ohlcv docstring.
                recovered += 1
            logger.info('get_many_ohlcv chunk %d-%d fallback recovered %d/%d tickers',
                        chunk_start, chunk_start + len(chunk), recovered, len(chunk))
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
            # No cache seed — see get_many_ohlcv docstring. The prior
            # `ohlcv_period:{t}:{period}` key was never read by any
            # consumer; populating it cost write-time work + memory for
            # zero downstream benefit.

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


def get_spy_6m1m_return(priority=PRIORITY_MEDIUM):
    """Cached SPY 6-1 month % return: the ~6-month window ending ~1 month ago.

    Companion to ``get_spy_1m_return`` for the momentum6m rec-row field —
    the classic momentum construction skips the most recent month because
    1-month returns mean-revert. Windows come from services/row_features.py
    so the stock-side and SPY-side math can't drift apart.

    Parameters
    ----------
    priority : int   – queue priority (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
    """
    from services.row_features import MOMENTUM_6M_SKIP, MOMENTUM_6M_WINDOW
    hist = get_spy_period('10mo', priority=priority)
    if hist is None:
        return None
    close = hist['Close'].dropna()
    end_idx = MOMENTUM_6M_SKIP + 1                      # bar ~1 month ago
    start_idx = MOMENTUM_6M_SKIP + MOMENTUM_6M_WINDOW + 1   # bar ~7 months ago
    if len(close) < start_idx:
        return None
    return (float(close.iloc[-end_idx]) / float(close.iloc[-start_idx]) - 1) * 100


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
    with _ticker_lock:
        if symbol is None:
            _ticker_objects.clear()
        else:
            symbol = symbol.upper()
            if symbol in _ticker_objects:
                del _ticker_objects[symbol]
                logger.info(f'Cleared cached Ticker object for {symbol}')
