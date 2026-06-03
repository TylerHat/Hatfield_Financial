"""Shared technical-indicator primitives.

These were previously duplicated across `routes/` files with slightly
different formulas — most notably RSI, which `routes/stock_info.py` used
to compute with `ewm(com=period-1)` while every other call site used
Wilder's `ewm(alpha=1/period, adjust=False)`. The two formulas differ by
~2-5 RSI points on the same data, so the analysis tab's RSI card disagreed
with the RSI chart signal RSI for every ticker. This module is now the
single source of truth.

All functions are pure (Series in, Series/scalar out). No Flask, no I/O,
no caching — caching belongs in data_fetcher.
"""

from __future__ import annotations

import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI from a close-price series.

    Uses `ewm(alpha=1/period, adjust=False)` — the canonical Wilder
    smoothing — for both the average gain and average loss. Returns a
    Series the same length as `close` with NaN until the smoothing has
    enough history to stabilise.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))


def macd_strength(macd_hist: pd.Series, lookback: int = 30) -> pd.Series:
    """Normalize the absolute MACD histogram against its own recent mean
    magnitude, returning a unit-free "momentum strength" Series.

    Output semantics:
        1.0  = today's |hist| matches the rolling ``lookback``-day mean
        >1.0 = today is stronger than the typical recent magnitude
        <1.0 = today is weaker

    Why: raw |macd - signal| values don't translate across instruments
    — 0.5 is a huge spread for SPY but tiny for a $400 stock. The
    normalised ratio is the same comparison the macd_crossover strategy
    already used internally for its signal score; lifting it into a
    shared helper lets the stock-info display "STRONG / WEAK MOMENTUM"
    badge agree with the signal-side score.
    """
    recent_mag = macd_hist.abs().rolling(lookback).mean()
    return macd_hist.abs() / recent_mag.replace(0, float('nan'))
