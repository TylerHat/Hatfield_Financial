"""
Shared data-fetching layer with in-memory caching.

All routes should use these helpers instead of calling yfinance directly.
This eliminates redundant fetches when the user switches strategies on the
same ticker, and keeps SPY data cached globally.
"""

import threading
import time
from datetime import datetime, timedelta

import yfinance as yf

# ── Cache storage ────────────────────────────────────────────────────────────

_cache = {}
_lock = threading.Lock()

# TTLs (seconds)
_OHLCV_TTL = 300       # 5 minutes — covers strategy switching
_INFO_TTL = 900         # 15 minutes — fundamentals change slowly
_EARNINGS_TTL = 3600    # 1 hour — rarely changes intraday
_SPY_TTL = 600          # 10 minutes — shared across all RS calculations
_ANALYST_TTL = 1800     # 30 minutes — analyst data changes infrequently

# Maximum warmup any strategy needs (mean-reversion, ma-confluence, 52-week)
_MAX_WARMUP_DAYS = 280

# ── Rate-limit throttle ─────────────────────────────────────────────────────
# Minimum seconds between yfinance HTTP calls to avoid Yahoo 429s.
_MIN_CALL_INTERVAL = 0.25  # 4 calls/sec max
_last_call_ts = 0.0
_throttle_lock = threading.Lock()


def _throttle():
    """Sleep if needed to stay under the yfinance call rate."""
    global _last_call_ts
    with _throttle_lock:
        now = time.time()
        elapsed = now - _last_call_ts
        if elapsed < _MIN_CALL_INTERVAL:
            time.sleep(_MIN_CALL_INTERVAL - elapsed)
        _last_call_ts = time.time()


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
    """Get or create a cached yf.Ticker object."""
    symbol = symbol.upper()
    with _ticker_lock:
        if symbol not in _ticker_objects:
            _ticker_objects[symbol] = yf.Ticker(symbol)
        return _ticker_objects[symbol]


# ── Public API ───────────────────────────────────────────────────────────────

def get_ohlcv(ticker, start, end):
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

    _throttle()
    fetch_start = start - timedelta(days=_MAX_WARMUP_DAYS)
    stock = _get_ticker(ticker)
    hist = stock.history(start=fetch_start, end=end)

    if hist is not None and not hist.empty:
        _cache_set(key, hist)
        return hist
    return None


def get_ticker_info(ticker):
    """
    Fetch the .info dict for a ticker with caching (15-min TTL).

    Returns
    -------
    dict or None
    """
    ticker = ticker.upper()
    key = f'info:{ticker}'

    cached = _cache_get(key, _INFO_TTL)
    if cached is not None:
        return cached

    _throttle()
    stock = _get_ticker(ticker)
    info = stock.info
    if info:
        _cache_set(key, info)
        return info
    return None


def get_earnings_dates(ticker, limit=20):
    """
    Fetch earnings dates for a ticker with caching (1-hour TTL).

    Returns
    -------
    pandas.DataFrame or None
    """
    ticker = ticker.upper()
    key = f'earnings:{ticker}'

    cached = _cache_get(key, _EARNINGS_TTL)
    if cached is not None:
        return cached

    _throttle()
    stock = _get_ticker(ticker)
    try:
        cal = stock.get_earnings_dates(limit=limit)
        if cal is not None and not cal.empty:
            _cache_set(key, cal)
            return cal
    except Exception:
        pass
    return None


def get_spy_history(start, end):
    """
    Fetch SPY OHLCV with a dedicated 10-min cache.
    Shared across stock_info, relative_strength, and backtest routes.
    """
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')
    key = f'spy:{start_str}:{end_str}'

    cached = _cache_get(key, _SPY_TTL)
    if cached is not None:
        return cached

    _throttle()
    spy = _get_ticker('SPY')
    hist = spy.history(start=start, end=end)

    if hist is not None and not hist.empty:
        _cache_set(key, hist)
        return hist
    return None


def get_spy_period(period='3mo'):
    """
    Fetch SPY by period string (e.g. '3mo', '1y') with 10-min cache.
    Used by stock_info for relative-strength cards.
    """
    key = f'spy_period:{period}'

    cached = _cache_get(key, _SPY_TTL)
    if cached is not None:
        return cached

    _throttle()
    spy = _get_ticker('SPY')
    hist = spy.history(period=period)

    if hist is not None and not hist.empty:
        _cache_set(key, hist)
        return hist
    return None


def get_analyst_data(ticker):
    """
    Fetch analyst-specific data (price targets, recommendation counts,
    upgrades/downgrades, earnings & revenue estimates) with 30-min TTL.

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

    _throttle()
    try:
        pt = stock.analyst_price_targets
        if pt:
            data['price_targets'] = pt
    except Exception:
        pass

    try:
        rs = stock.recommendations_summary
        if rs is not None and not rs.empty:
            data['recommendations_summary'] = rs
    except Exception:
        pass

    _throttle()
    try:
        ud = stock.upgrades_downgrades
        if ud is not None and not ud.empty:
            data['upgrades_downgrades'] = ud.head(50)
    except Exception:
        pass

    try:
        ee = stock.earnings_estimate
        if ee is not None and not ee.empty:
            data['earnings_estimate'] = ee
    except Exception:
        pass

    try:
        re_ = stock.revenue_estimate
        if re_ is not None and not re_.empty:
            data['revenue_estimate'] = re_
    except Exception:
        pass

    if data:
        _cache_set(key, data)
    return data if data else None


def clear_cache(prefix=None):
    """Clear all cache entries, or only those matching a key prefix."""
    with _lock:
        if prefix is None:
            _cache.clear()
        else:
            keys = [k for k in _cache if k.startswith(prefix)]
            for k in keys:
                del _cache[k]
