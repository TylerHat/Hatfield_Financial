"""
Shared data-fetching layer with in-memory caching.

All routes should use these helpers instead of calling yfinance directly.
This eliminates redundant fetches when the user switches strategies on the
same ticker, and keeps SPY data cached globally.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta

import yfinance as yf
from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket
from pyrate_limiter import Duration, RequestRate, Limiter

logger = logging.getLogger(__name__)

# ── Shared HTTP session (cache + rate limit) ────────────────────────────────
# Every yfinance call — single-ticker via yf.Ticker, or bulk via yf.download —
# reuses this session so that:
#   1. Repeated requests within the cache TTL skip the network entirely.
#   2. New requests are paced by pyrate_limiter regardless of which thread
#      yfinance spawns internally (threads=True on yf.download bypasses our
#      app-level _throttle() but not this session-level limiter).

class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    pass


_CACHE_DIR = os.path.join(os.path.dirname(__file__), '.cache')
os.makedirs(_CACHE_DIR, exist_ok=True)

# 4 requests / second — matches the existing _MIN_CALL_INTERVAL budget.
_YF_SESSION = CachedLimiterSession(
    limiter=Limiter(RequestRate(4, Duration.SECOND * 1)),
    bucket_class=MemoryQueueBucket,
    backend=SQLiteCache(os.path.join(_CACHE_DIR, 'yfinance.cache'),
                        expire_after=300),
)

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

# ── Rate-limit throttle ─────────────────────────────────────────────────────
# Minimum seconds between yfinance HTTP calls to avoid Yahoo 429s.
_MIN_CALL_INTERVAL = 0.25  # 4 calls/sec max
_last_call_ts = 0.0
_throttle_lock = threading.Lock()


_call_count = 0
_call_count_reset = 0.0


def _throttle():
    """Sleep if needed to stay under the yfinance call rate."""
    global _last_call_ts, _call_count, _call_count_reset
    with _throttle_lock:
        now = time.time()
        # Log calls per minute
        if now - _call_count_reset > 60:
            if _call_count > 0:
                logger.info('yfinance calls in last minute: %d', _call_count)
            _call_count = 0
            _call_count_reset = now
        _call_count += 1
        elapsed = now - _last_call_ts
        if elapsed < _MIN_CALL_INTERVAL:
            time.sleep(_MIN_CALL_INTERVAL - elapsed)
        _last_call_ts = time.time()


_RETRY_DELAY = 3        # seconds to wait after a rate-limit hit
_MAX_RETRIES = 3        # retry attempts per yfinance attribute


def _fetch_with_retry(fn, label):
    """Call *fn()* up to _MAX_RETRIES times, retrying on rate-limit errors."""
    for attempt in range(_MAX_RETRIES + 1):
        _throttle()
        try:
            return fn()
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
    """Get or create a cached yf.Ticker object bound to the shared session."""
    symbol = symbol.upper()
    with _ticker_lock:
        if symbol not in _ticker_objects:
            _ticker_objects[symbol] = yf.Ticker(symbol, session=_YF_SESSION)
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

    pt = _fetch_with_retry(lambda: stock.analyst_price_targets, f'{ticker} price_targets')
    if pt:
        data['price_targets'] = pt

    rs = _fetch_with_retry(lambda: stock.recommendations_summary, f'{ticker} recommendations_summary')
    if rs is not None and hasattr(rs, 'empty') and not rs.empty:
        data['recommendations_summary'] = rs

    ud = _fetch_with_retry(lambda: stock.upgrades_downgrades, f'{ticker} upgrades_downgrades')
    if ud is not None and hasattr(ud, 'empty') and not ud.empty:
        data['upgrades_downgrades'] = ud.head(50)

    ee = _fetch_with_retry(lambda: stock.earnings_estimate, f'{ticker} earnings_estimate')
    if ee is not None and hasattr(ee, 'empty') and not ee.empty:
        data['earnings_estimate'] = ee

    re_ = _fetch_with_retry(lambda: stock.revenue_estimate, f'{ticker} revenue_estimate')
    if re_ is not None and hasattr(re_, 'empty') and not re_.empty:
        data['revenue_estimate'] = re_

    if data:
        _cache_set(key, data)
    return data if data else None


def get_many_ohlcv(tickers, period='10mo', chunk_size=50, chunk_delay=0.5):
    """Bulk OHLCV download for many tickers, routed through the shared session.

    Returns ``{ticker: DataFrame}``.  Populates the per-ticker ``ohlcv:`` cache
    entries used by ``get_ohlcv`` so later single-ticker reads hit the cache.

    Parameters
    ----------
    tickers : list[str]
    period : str              – yfinance period string (e.g. ``'10mo'``)
    chunk_size : int          – tickers per yf.download call
    chunk_delay : float       – seconds to sleep between chunks
    """
    tickers = [t.upper() for t in tickers]
    result = {}

    for chunk_start in range(0, len(tickers), chunk_size):
        chunk = tickers[chunk_start:chunk_start + chunk_size]
        _throttle()
        try:
            raw = yf.download(
                chunk,
                period=period,
                group_by='ticker',
                threads=True,
                progress=False,
                session=_YF_SESSION,
            )
        except Exception as exc:
            logger.error('get_many_ohlcv chunk %d-%d failed: %s',
                         chunk_start, chunk_start + len(chunk), exc)
            if chunk_start + chunk_size < len(tickers):
                time.sleep(chunk_delay)
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

        if chunk_start + chunk_size < len(tickers):
            time.sleep(chunk_delay)

    return result


def get_spy_1m_return():
    """Cached SPY trailing ~1-month % return (last close vs 22 trading days ago).

    Reused by recommendations + user_data routes to avoid three independent
    SPY fetches per page load.  Backed by ``get_spy_period('10mo')`` which has
    its own 10-minute TTL cache.
    """
    hist = get_spy_period('10mo')
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
