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

# Maximum warmup any strategy needs (mean-reversion, ma-confluence, 52-week)
_MAX_WARMUP_DAYS = 280


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
    # Normalize dates to date-only strings for cache key stability
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')
    key = f'ohlcv:{ticker}:{start_str}:{end_str}'

    cached = _cache_get(key, _OHLCV_TTL)
    if cached is not None:
        return cached

    fetch_start = start - timedelta(days=_MAX_WARMUP_DAYS)
    stock = yf.Ticker(ticker)
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

    stock = yf.Ticker(ticker)
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

    stock = yf.Ticker(ticker)
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

    Parameters
    ----------
    start : datetime
    end : datetime

    Returns
    -------
    pandas.DataFrame or None
    """
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')
    key = f'spy:{start_str}:{end_str}'

    cached = _cache_get(key, _SPY_TTL)
    if cached is not None:
        return cached

    spy = yf.Ticker('SPY')
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

    spy = yf.Ticker('SPY')
    hist = spy.history(period=period)

    if hist is not None and not hist.empty:
        _cache_set(key, hist)
        return hist
    return None


def clear_cache(prefix=None):
    """Clear all cache entries, or only those matching a key prefix."""
    with _lock:
        if prefix is None:
            _cache.clear()
        else:
            keys = [k for k in _cache if k.startswith(prefix)]
            for k in keys:
                del _cache[k]
