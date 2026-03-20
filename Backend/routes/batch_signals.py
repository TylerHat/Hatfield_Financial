"""
GET /api/strategy/<strategy_name>/batch
Runs a strategy on all S&P 500 stocks using cached OHLCV data.
Returns the most recent signal (within 30 days) for each ticker.
Cached per strategy for 30 minutes.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta

import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify

from cache import SimpleCache
from sp500 import get_sp500_tickers
from routes.recommendations import _cache as rec_cache, _OHLCV_CACHE_KEY, _CACHE_TTL

from routes.strategies.rsi import compute_signals as rsi_compute
from routes.strategies.bollinger_bands import compute_signals as bb_compute
from routes.strategies.macd_crossover import compute_signals as macd_compute
from routes.strategies.mean_reversion import compute_signals as mr_compute
from routes.strategies.volatility_squeeze import compute_signals as vs_compute
from routes.strategies.breakout_52week import compute_signals as bk_compute
from routes.strategies.ma_confluence import compute_signals as mac_compute
from routes.strategies.relative_strength import compute_signals as rs_compute
from routes.strategies.post_earnings_drift import compute_signals as ped_compute

batch_bp = Blueprint('batch_signals', __name__)

_batch_cache = SimpleCache()

RECENCY_CUTOFF = timedelta(days=30)

# Standard strategies: compute_signals(hist_df) -> list
STANDARD_STRATEGIES = {
    'rsi': rsi_compute,
    'bollinger-bands': bb_compute,
    'macd-crossover': macd_compute,
    'mean-reversion': mr_compute,
    'volatility-squeeze': vs_compute,
    '52-week-breakout': bk_compute,
    'ma-confluence': mac_compute,
}

# Special strategies that need extra data
SPECIAL_STRATEGIES = {'relative-strength', 'post-earnings-drift'}

ALL_STRATEGIES = set(STANDARD_STRATEGIES.keys()) | SPECIAL_STRATEGIES


def _get_last_recent_signal(signals):
    """Return the last signal if it's within the recency cutoff, else None."""
    if not signals:
        return None
    last = signals[-1]
    try:
        signal_date = datetime.strptime(last['date'], '%Y-%m-%d').date()
        if (date.today() - signal_date) <= RECENCY_CUTOFF:
            return last
    except Exception:
        pass
    return None


def _fetch_earnings_dates(ticker):
    """Fetch earnings dates for a single ticker. Returns (ticker, DatetimeIndex)."""
    try:
        stock = yf.Ticker(ticker)
        earnings = stock.earnings_dates
        if earnings is not None and not earnings.empty:
            return (ticker, earnings.index)
    except Exception:
        pass
    return (ticker, pd.DatetimeIndex([]))


def _run_standard_batch(strategy_name, raw_df, tickers):
    """Run a standard strategy on all tickers using cached OHLCV data."""
    compute_fn = STANDARD_STRATEGIES[strategy_name]
    result = {}

    for t in tickers:
        try:
            hist_df = raw_df[t].dropna(how='all')
            if hist_df.empty or len(hist_df) < 50:
                result[t] = None
                continue
            signals = compute_fn(hist_df)
            result[t] = _get_last_recent_signal(signals)
        except Exception:
            result[t] = None

    return result


def _run_relative_strength_batch(raw_df, tickers):
    """Run relative-strength strategy using SPY data from the cached OHLCV."""
    result = {}
    try:
        spy_close = raw_df['SPY']['Close'].dropna()
    except Exception:
        return {t: None for t in tickers}

    for t in tickers:
        try:
            hist_df = raw_df[t].dropna(how='all')
            if hist_df.empty or len(hist_df) < 50:
                result[t] = None
                continue
            signals = rs_compute(hist_df, spy_close)
            result[t] = _get_last_recent_signal(signals)
        except Exception:
            result[t] = None

    return result


def _run_post_earnings_batch(raw_df, tickers):
    """Run post-earnings-drift strategy, fetching earnings dates in parallel."""
    result = {}

    # Fetch earnings dates concurrently
    earnings_map = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(_fetch_earnings_dates, t): t for t in tickers}
        for future in as_completed(futures):
            try:
                t, earn_idx = future.result(timeout=10)
                earnings_map[t] = earn_idx
            except Exception:
                pass

    for t in tickers:
        try:
            hist_df = raw_df[t].dropna(how='all')
            earn_idx = earnings_map.get(t, pd.DatetimeIndex([]))
            if hist_df.empty or len(hist_df) < 10:
                result[t] = None
                continue
            signals = ped_compute(hist_df, earn_idx)
            result[t] = _get_last_recent_signal(signals)
        except Exception:
            result[t] = None

    return result


@batch_bp.route('/api/strategy/<strategy_name>/batch')
def batch_signals(strategy_name):
    if strategy_name not in ALL_STRATEGIES:
        return jsonify({
            'error': f'Unknown strategy: {strategy_name}. Valid: {sorted(ALL_STRATEGIES)}',
        }), 400

    # Check batch cache
    cache_key = f'batch_signals_{strategy_name}'
    cached = _batch_cache.get(cache_key, _CACHE_TTL)
    if cached:
        return jsonify(cached)

    # Get cached OHLCV data
    raw_df = rec_cache.get(_OHLCV_CACHE_KEY, _CACHE_TTL)
    if raw_df is None:
        return jsonify({
            'status': 'loading',
            'message': 'S&P 500 data not yet loaded. Please load the Recommendations tab first.',
        }), 202

    tickers = get_sp500_tickers()

    try:
        if strategy_name in STANDARD_STRATEGIES:
            signals = _run_standard_batch(strategy_name, raw_df, tickers)
        elif strategy_name == 'relative-strength':
            signals = _run_relative_strength_batch(raw_df, tickers)
        elif strategy_name == 'post-earnings-drift':
            signals = _run_post_earnings_batch(raw_df, tickers)
        else:
            signals = {t: None for t in tickers}

        signal_count = sum(1 for v in signals.values() if v is not None)

        result = {
            'strategy': strategy_name,
            'signals': signals,
            'signalCount': signal_count,
            'lastUpdated': datetime.utcnow().isoformat() + 'Z',
        }
        _batch_cache.set(cache_key, result)
        return jsonify(result)

    except Exception as e:
        return jsonify({
            'error': f'Failed to compute batch signals: {str(e)}',
            'signals': {},
        }), 500
