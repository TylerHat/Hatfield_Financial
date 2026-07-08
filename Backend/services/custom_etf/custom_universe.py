"""Row builder for Custom ETF strategies with a fixed `custom_universe`.

Strategies like Sector Rotation trade a small fixed ticker list (SPDR
sector ETFs) that never appears in the S&P 500 recommendations snapshot.
This module synthesizes recommendation-style rows for those tickers from
price history alone, using the same services/row_features math as the
prewarm — so scores are directly comparable and the walk-forward backtest
engine reconstructs identical fields.

Rows carry only price-derived fields (plus Markov). No .info fetch — a
custom-universe strategy that needed fundamentals would also be
backtest-unsafe, which defeats the point of a fixed price universe.
"""

from __future__ import annotations

import logging

from cache import SimpleCache
import data_fetcher
from services import row_features as rf
from services.markov import analyze_markov

logger = logging.getLogger(__name__)

_cache = SimpleCache()
_ROWS_TTL = 900  # 15 min — matches the freshness of the recs snapshot's prices
_HISTORY_PERIOD = '10mo'  # same window the recommendations prewarm uses
_MIN_BARS = 50


def _row_from_history(ticker: str, hist_df, spy_close) -> dict | None:
    frame = rf.compute_feature_frame(hist_df, spy_close)

    def last(col, decimals=2):
        return rf.latest(frame[col], decimals=decimals)

    current_price = last('currentPrice', decimals=4)
    if current_price is None or current_price <= 0:
        return None

    row = {
        'ticker': ticker,
        'name': ticker,
        'currentPrice': current_price,
        'momentum': last('momentum'),
        'momentum6m': last('momentum6m'),
        'momentum6mAbs': last('momentum6mAbs'),
        'realizedVol': last('realizedVol'),
        'trendAlignment': last('trendAlignment', decimals=None),
        'macdStatus': last('macdStatus', decimals=None),
        'fiftyTwoWeekPosition': last('fiftyTwoWeekPosition'),
        'rsiValue': last('rsiValue', decimals=1),
        'volRatio': last('volRatio'),
        'markovRegime': None,
        'markovBull3d': None,
        'markovBull5d': None,
        'markovBear5d': None,
    }

    try:
        markov = analyze_markov(hist_df['Close'].to_numpy(dtype=float))
        if markov is not None:
            row['markovRegime'] = markov['current_regime']
            f5 = markov['forecast'].get('5d')
            f3 = markov['forecast'].get('3d')
            if f5:
                row['markovBull5d'] = round(f5['bull'], 4)
                row['markovBear5d'] = round(f5['bear'], 4)
            if f3:
                row['markovBull3d'] = round(f3['bull'], 4)
    except Exception:
        pass

    return row


def build_rows_for_universe(tickers) -> list[dict]:
    """Recommendation-style rows for a fixed ticker list. Cached 15 min."""
    tickers = tuple(tickers)
    key = 'custom_universe_rows:' + ','.join(tickers)
    cached = _cache.get(key, _ROWS_TTL)
    if cached is not None:
        return cached

    try:
        ohlc = data_fetcher.get_many_ohlcv(
            list(tickers), period=_HISTORY_PERIOD,
            priority=data_fetcher.PRIORITY_MEDIUM,
        )
    except Exception as e:
        logger.error('custom universe OHLCV fetch failed: %s', e)
        return []

    spy_close = None
    try:
        spy_hist = data_fetcher.get_spy_period(_HISTORY_PERIOD,
                                               priority=data_fetcher.PRIORITY_MEDIUM)
        if spy_hist is not None and not spy_hist.empty:
            spy_close = spy_hist['Close'].dropna()
    except Exception as e:
        logger.warning('custom universe SPY fetch failed — momentum will be absolute: %s', e)

    rows = []
    for t in tickers:
        hist = ohlc.get(t)
        if hist is None or hist.empty or len(hist) < _MIN_BARS:
            logger.debug('custom universe: insufficient history for %s — skipping', t)
            continue
        try:
            row = _row_from_history(t, hist, spy_close)
        except Exception as e:
            logger.warning('custom universe row build failed for %s: %s', t, e)
            continue
        if row:
            rows.append(row)

    if rows:
        _cache.set(key, rows)
    return rows
