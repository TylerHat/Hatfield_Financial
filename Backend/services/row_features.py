"""Price-derived recommendation-row features — single source of truth.

Every rec-row field that is computable from OHLCV alone lives here as a
*vectorized series* function (value for every bar), consumed by two callers:

  - routes/recommendations.py   — live prewarm: evaluates each series at the
    last bar (``.iloc[-1]``), so the live row is by construction the same
    number the backtest engine would produce for "today".
  - services/custom_etf/walk_forward.py — backtest engine: precomputes the
    full feature frame once per ticker, then reads row *i* for the bar at
    each rebalance date. Point-in-time correctness falls out of the rolling
    construction: nothing at bar *i* looks past bar *i*.

If a formula here changes, live scores and backtest scores change together.
That is the point — the HFA-069 review found the previous Markov backtest
drifting from the live strategy because the two had separate implementations.

All functions are pure (Series in, Series out). No Flask, no I/O, no caching.

Parity note: the live prewarm subtracts a *scalar* SPY return (SPY's own last
N bars) while the series functions subtract a *date-aligned* SPY series. For
S&P-500 names the two differ only when a stock skipped a trading day SPY
traded — sub-0.1% cases, fractions of a percent in value.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.indicators import compute_rsi

# ── Canonical windows (trading days) ────────────────────────────────────
# Shared by data_fetcher's SPY helpers and both feature consumers. Change
# here, not at call sites.
MOMENTUM_1M_WINDOW = 21      # ~1 month; matches the legacy iloc[-22] math
MOMENTUM_6M_WINDOW = 126     # ~6 months
MOMENTUM_6M_SKIP = 21        # skip the most recent month (short-term reversal)
REALIZED_VOL_WINDOW = 126    # ~6 months of daily returns
TRADING_DAYS_PER_YEAR = 252


def pct_return_series(close: pd.Series, window: int) -> pd.Series:
    """Trailing ``window``-bar simple return in percent, per bar.

    ``pct_return_series(close, 21).iloc[-1]`` equals the legacy scalar
    ``(close.iloc[-1] / close.iloc[-22] - 1) * 100``.
    """
    return (close / close.shift(window) - 1) * 100


def _align_spy(close: pd.Series, spy_close: pd.Series) -> pd.Series:
    """Reindex a SPY close series onto the stock's trading calendar.

    yfinance endpoints disagree on index tz-awareness (`Ticker.history` is
    tz-aware America/New_York; bulk `yf.download` frames may come back
    naive, or vice versa). Comparing mixed indexes raises in pandas, so when
    exactly one side is tz-aware, align on naive dates and restore the
    stock's original index on the result.
    """
    spy_aware = spy_close.index.tz is not None
    close_aware = close.index.tz is not None
    if spy_aware == close_aware:
        return spy_close.reindex(close.index, method='ffill')

    spy_naive = spy_close.copy()
    if spy_aware:
        spy_naive.index = spy_close.index.tz_localize(None)
    target = close.index.tz_localize(None) if close_aware else close.index
    aligned = spy_naive.reindex(target, method='ffill')
    aligned.index = close.index
    return aligned


def momentum_1m_series(close: pd.Series, spy_close: pd.Series | None = None) -> pd.Series:
    """1-month return in %, minus SPY's same-window return when supplied.

    This is the legacy ``momentum`` field (kept for the Recommendations
    table and Buy Score). Note the horizon: 1-month relative strength is a
    *reversal*-prone signal — portfolio strategies should prefer
    ``momentum_6m1m_series``.
    """
    stock = pct_return_series(close, MOMENTUM_1M_WINDOW)
    if spy_close is None:
        return stock
    spy = pct_return_series(_align_spy(close, spy_close), MOMENTUM_1M_WINDOW)
    return stock - spy


def momentum_6m1m_series(close: pd.Series, spy_close: pd.Series | None = None) -> pd.Series:
    """6-1 month momentum in %: the 126-bar return ending 21 bars ago,
    minus SPY's same-window return when supplied.

    Skipping the most recent month follows the Jegadeesh–Titman / Carhart
    construction — 1-month returns mean-revert, so the classic momentum
    factor excludes them. Needs ``MOMENTUM_6M_SKIP + MOMENTUM_6M_WINDOW``
    (147) prior bars; NaN before that.
    """
    stock = pct_return_series(close, MOMENTUM_6M_WINDOW).shift(MOMENTUM_6M_SKIP)
    if spy_close is None:
        return stock
    spy = pct_return_series(_align_spy(close, spy_close), MOMENTUM_6M_WINDOW).shift(MOMENTUM_6M_SKIP)
    return stock - spy


def realized_vol_series(close: pd.Series, window: int = REALIZED_VOL_WINDOW) -> pd.Series:
    """Annualized realized volatility in %, from daily log returns.

    Strict ``min_periods=window`` so every non-NaN value is measured over
    the same horizon — required for the cross-sectional percentile ranking
    in the Low Vol strategy to compare like with like.
    """
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window, min_periods=window).std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100


def macd_status_series(close: pd.Series) -> pd.Series:
    """Per-bar MACD status label. Same formula the Recommendations table
    used inline: EMA12−EMA26 vs its EMA9 signal, crossover on the bar the
    relationship flips."""
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()

    prev_macd = macd.shift(1)
    prev_sig = sig.shift(1)
    cross_up = (prev_macd <= prev_sig) & (macd > sig)
    cross_dn = (prev_macd >= prev_sig) & (macd < sig)

    status = np.select(
        [cross_up, cross_dn, macd > sig],
        ['BULLISH CROSSOVER', 'BEARISH CROSSOVER', 'BULLISH'],
        default='BEARISH',
    )
    return pd.Series(status, index=close.index)


def trend_alignment_series(close: pd.Series) -> pd.Series:
    """Per-bar trend alignment label from MA20/50/200 ordering. Falls back
    to the short-term (MA20/50) labels while MA200 is still warming up,
    mirroring the legacy inline logic."""
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    have200 = ma200.notna()
    have50 = ma50.notna()
    strong_up = (close > ma20) & (ma20 > ma50) & (ma50 > ma200)
    strong_dn = (close < ma20) & (ma20 < ma50) & (ma50 < ma200)

    label = np.select(
        [
            have200 & strong_up,
            have200 & strong_dn,
            have200 & (close > ma200),
            have200,
            have50 & (close > ma20) & (ma20 > ma50),
            have50,
        ],
        [
            'Strong Uptrend',
            'Strong Downtrend',
            'Bullish (Mixed)',
            'Bearish (Mixed)',
            'Bullish (Short-term)',
            'Bearish (Short-term)',
        ],
        default='N/A',
    )
    return pd.Series(label, index=close.index)


def vol_ratio_series(hist_df: pd.DataFrame) -> pd.Series:
    """Per-bar ATR(14) divided by the running mean of ATR — the legacy
    ``volRatio`` display field ("is this stock quieter/noisier than its own
    history"). NOT a cross-sectional volatility measure; portfolio
    strategies should use ``realized_vol_series`` instead."""
    close = hist_df['Close']
    high_low = hist_df['High'] - hist_df['Low']
    high_pc = (hist_df['High'] - close.shift(1)).abs()
    low_pc = (hist_df['Low'] - close.shift(1)).abs()
    tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    # expanding mean at the last bar == atr.mean() over the whole series,
    # which is exactly the legacy scalar computation.
    return atr / atr.expanding().mean()


def fifty_two_week_position_series(close: pd.Series) -> pd.Series:
    """Per-bar position within the trailing 252-bar high/low range, 0-100.

    ``min_periods=1`` mirrors the legacy fallback (``close.tail(252)`` on a
    shorter series uses whatever history exists). The live prewarm prefers
    yfinance's own fiftyTwoWeekHigh/Low when present; this series is the
    price-history construction used as its fallback and by the backtest
    engine.
    """
    high = close.rolling(252, min_periods=1).max()
    low = close.rolling(252, min_periods=1).min()
    rng = high - low
    with np.errstate(divide='ignore', invalid='ignore'):
        pos = (close - low) / rng * 100
    return pos.where(rng > 0)


def latest(series: pd.Series, decimals: int | None = 2):
    """Last value of a series as a rounded float, or None when NaN/empty.
    Convenience for the live prewarm's scalar row fields."""
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return None
    if isinstance(val, str):
        return val
    return round(float(val), decimals) if decimals is not None else float(val)


def compute_feature_frame(hist_df: pd.DataFrame, spy_close: pd.Series | None = None) -> pd.DataFrame:
    """All price-derived rec-row features for every bar of ``hist_df``.

    Used by the walk-forward backtest engine: computed once per ticker,
    then row *i* provides the fields a live recommendations row would have
    carried at that bar. Column names match the rec-row keys exactly.
    """
    close = hist_df['Close']
    frame = pd.DataFrame(index=hist_df.index)
    frame['currentPrice'] = close
    frame['momentum'] = momentum_1m_series(close, spy_close)
    frame['momentum6m'] = momentum_6m1m_series(close, spy_close)
    frame['momentum6mAbs'] = momentum_6m1m_series(close)
    frame['realizedVol'] = realized_vol_series(close)
    frame['trendAlignment'] = trend_alignment_series(close)
    frame['macdStatus'] = macd_status_series(close)
    frame['fiftyTwoWeekPosition'] = fifty_two_week_position_series(close)
    frame['rsiValue'] = compute_rsi(close)
    if {'High', 'Low'}.issubset(hist_df.columns):
        frame['volRatio'] = vol_ratio_series(hist_df)
    else:
        frame['volRatio'] = np.nan
    return frame
