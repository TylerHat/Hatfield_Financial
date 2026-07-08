"""row_features tests: (1) parity with the legacy inline prewarm math the
HFA-069 refactor replaced, and (2) the no-lookahead property the walk-forward
engine depends on."""

import numpy as np
import pandas as pd
import pytest

from services import row_features as rf


def _synthetic_ohlcv(n=280, seed=7, drift=0.0004):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.015, n)
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range('2024-01-02', periods=n)
    close = pd.Series(close, index=dates)
    high = close * (1 + rng.uniform(0.0, 0.02, n))
    low = close * (1 - rng.uniform(0.0, 0.02, n))
    return pd.DataFrame({'Open': close, 'High': high, 'Low': low,
                         'Close': close, 'Volume': 1_000_000}, index=dates)


@pytest.fixture(scope='module')
def hist():
    return _synthetic_ohlcv()


# ── Parity with the legacy inline formulas ──────────────────────────────

def test_macd_status_matches_legacy(hist):
    close = hist['Close']
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    macd_val, signal_val = float(macd.iloc[-1]), float(sig.iloc[-1])
    prev_macd, prev_sig = float(macd.iloc[-2]), float(sig.iloc[-2])
    if prev_macd <= prev_sig and macd_val > signal_val:
        legacy = 'BULLISH CROSSOVER'
    elif prev_macd >= prev_sig and macd_val < signal_val:
        legacy = 'BEARISH CROSSOVER'
    elif macd_val > signal_val:
        legacy = 'BULLISH'
    else:
        legacy = 'BEARISH'
    assert rf.latest(rf.macd_status_series(close), decimals=None) == legacy


def test_trend_alignment_matches_legacy(hist):
    close = hist['Close']
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    current = float(close.iloc[-1])
    legacy = 'N/A'
    if len(close) >= 200 and not pd.isna(ma200.iloc[-1]):
        m20, m50, m200 = float(ma20.iloc[-1]), float(ma50.iloc[-1]), float(ma200.iloc[-1])
        if current > m20 > m50 > m200:
            legacy = 'Strong Uptrend'
        elif current < m20 < m50 < m200:
            legacy = 'Strong Downtrend'
        elif current > m200:
            legacy = 'Bullish (Mixed)'
        else:
            legacy = 'Bearish (Mixed)'
    assert rf.latest(rf.trend_alignment_series(close), decimals=None) == legacy


def test_trend_alignment_short_history_falls_back():
    hist = _synthetic_ohlcv(n=120)
    close = hist['Close']
    label = rf.latest(rf.trend_alignment_series(close), decimals=None)
    assert label in ('Bullish (Short-term)', 'Bearish (Short-term)')


def test_vol_ratio_matches_legacy(hist):
    close = hist['Close']
    high_low = hist['High'] - hist['Low']
    high_pc = (hist['High'] - close.shift(1)).abs()
    low_pc = (hist['Low'] - close.shift(1)).abs()
    tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    legacy = round(float(atr.iloc[-1]) / float(atr.mean()), 2)
    assert rf.latest(rf.vol_ratio_series(hist)) == pytest.approx(legacy, abs=1e-9)


def test_momentum_1m_matches_legacy(hist):
    close = hist['Close']
    legacy = (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100
    assert rf.latest(rf.momentum_1m_series(close), decimals=None) == pytest.approx(legacy)


def test_momentum_6m1m_window(hist):
    close = hist['Close']
    expected = (float(close.iloc[-22]) / float(close.iloc[-148]) - 1) * 100
    assert rf.latest(rf.momentum_6m1m_series(close), decimals=None) == pytest.approx(expected)


def test_momentum_6m1m_excess_subtracts_spy(hist):
    close = hist['Close']
    spy = close * 1.5  # identical returns → excess must be ~0
    excess = rf.latest(rf.momentum_6m1m_series(close, spy), decimals=None)
    assert excess == pytest.approx(0.0, abs=1e-9)


def test_spy_alignment_survives_mixed_tz_awareness(hist):
    """yfinance endpoints disagree on tz-awareness (Ticker.history is
    tz-aware NY, bulk yf.download can be naive, or vice versa). Alignment
    must work in every combination — regression for the sector-rotation
    live path (HFA-069)."""
    close = hist['Close']
    spy = close * 1.5
    tz_close = close.copy()
    tz_close.index = close.index.tz_localize('America/New_York')
    tz_spy = spy.copy()
    tz_spy.index = spy.index.tz_localize('America/New_York')

    for c, s in [(close, tz_spy), (tz_close, spy), (tz_close, tz_spy)]:
        excess = rf.latest(rf.momentum_6m1m_series(c, s), decimals=None)
        assert excess == pytest.approx(0.0, abs=1e-9)
        assert rf.momentum_6m1m_series(c, s).index.equals(c.index)


def test_fifty_two_week_position_matches_legacy(hist):
    close = hist['Close']
    hi = float(close.tail(252).max())
    lo = float(close.tail(252).min())
    legacy = (float(close.iloc[-1]) - lo) / (hi - lo) * 100
    assert rf.latest(rf.fifty_two_week_position_series(close), decimals=None) == pytest.approx(legacy)


def test_realized_vol_strict_window():
    hist = _synthetic_ohlcv(n=100)  # < 127 bars → not enough for the strict window
    assert rf.latest(rf.realized_vol_series(hist['Close'])) is None
    hist = _synthetic_ohlcv(n=280)
    rv = rf.latest(rf.realized_vol_series(hist['Close']))
    assert rv is not None and 5 < rv < 60  # ~1.5% daily vol → ~24% annualized


# ── No-lookahead property ────────────────────────────────────────────────

def test_feature_frame_has_no_lookahead(hist):
    """Every feature value at bar k must be unchanged when all data after
    bar k is removed — the invariant the walk-forward engine relies on."""
    full = rf.compute_feature_frame(hist)
    k = 200
    trunc = rf.compute_feature_frame(hist.iloc[:k])
    for col in full.columns:
        a, b = full[col].iloc[:k], trunc[col]
        if pd.api.types.is_string_dtype(a) or a.dtype == object:
            assert (a.fillna('~') == b.fillna('~')).all(), f'lookahead in {col}'
        else:
            assert np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float),
                               equal_nan=True), f'lookahead in {col}'
