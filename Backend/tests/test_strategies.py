"""Custom ETF strategy scoring tests — bounds, threshold reachability,
eligibility gates, and the registry's backtest-safety contract (HFA-069)."""

import pytest

from services.custom_etf.strategies import STRATEGIES
from services.custom_etf.strategies.base import cross_sectional_percentile
from services.custom_etf.strategies.momentum_top10 import MomentumTop10Strategy
from services.custom_etf.strategies.low_vol_defensive import LowVolDefensiveStrategy
from services.custom_etf.strategies.fifty_two_week_high import FiftyTwoWeekHighStrategy
from services.custom_etf.strategies.sector_rotation import SectorRotationStrategy


def _universe(n=50, field='momentum6m', lo=-20.0, hi=30.0):
    """n rows with `field` spread linearly from lo to hi."""
    step = (hi - lo) / (n - 1)
    return [{'ticker': f'T{i:03d}', 'currentPrice': 100.0, field: lo + i * step}
            for i in range(n)]


# ── cross_sectional_percentile ───────────────────────────────────────────

def test_percentile_bounds_and_midpoint():
    vals = sorted(float(v) for v in range(100))
    assert cross_sectional_percentile(vals, 0.0) == 0.0
    assert cross_sectional_percentile(vals, 99.0) == 100.0
    assert cross_sectional_percentile(vals, 49.5) == pytest.approx(50.0, abs=1)


def test_percentile_refuses_tiny_sample():
    assert cross_sectional_percentile([1.0, 2.0, 3.0], 2.0) is None


# ── Momentum (corrected: 6-1M cross-sectional) ──────────────────────────

def test_momentum_top_decile_with_confirms_clears_buy_bar():
    strat = MomentumTop10Strategy()
    rows = _universe(50)
    strat.prepare(rows)
    top = {**rows[-1], 'trendAlignment': 'Strong Uptrend',
           'macdStatus': 'BULLISH', 'fiftyTwoWeekPosition': 90.0}
    score = strat.score(top)
    assert score >= strat.config.buy_threshold


def test_momentum_median_name_stays_below_buy_bar():
    strat = MomentumTop10Strategy()
    rows = _universe(50)
    strat.prepare(rows)
    mid = {**rows[25], 'trendAlignment': 'Bullish (Mixed)',
           'macdStatus': 'BULLISH', 'fiftyTwoWeekPosition': 70.0}
    assert strat.score(mid) < strat.config.buy_threshold


def test_momentum_bear_market_confirmations_gate_buys():
    """Best relative momentum in a broad downtrend should not clear the bar
    — the soft absolute-momentum gate via trend/MACD confirmations."""
    strat = MomentumTop10Strategy()
    rows = _universe(50, lo=-40.0, hi=-5.0)   # everything down vs SPY-adjusted
    strat.prepare(rows)
    best = {**rows[-1], 'trendAlignment': 'Strong Downtrend',
            'macdStatus': 'BEARISH', 'fiftyTwoWeekPosition': 20.0}
    assert strat.score(best) < strat.config.buy_threshold


def test_momentum_abstains_without_field_or_universe():
    strat = MomentumTop10Strategy()
    strat.prepare(_universe(5))               # below MIN_UNIVERSE_FOR_PERCENTILE
    assert strat.score({'ticker': 'X', 'currentPrice': 1.0, 'momentum6m': 10.0}) is None
    strat.prepare(_universe(50))
    assert strat.score({'ticker': 'X', 'currentPrice': 1.0}) is None


# ── Low Vol (corrected: cross-sectional realized vol) ───────────────────

def test_low_vol_ranks_cross_sectionally():
    strat = LowVolDefensiveStrategy()
    rows = _universe(50, field='realizedVol', lo=12.0, hi=45.0)
    strat.prepare(rows)
    quality = {'returnOnEquity': 0.22, 'debtToEquity': 25.0,
               'overallRisk': 1, 'grossMargins': 0.55}
    calm = strat.score({**rows[0], **quality})     # lowest σ in universe
    wild = strat.score({**rows[-1], **quality})    # highest σ in universe
    assert calm > wild
    assert calm >= strat.config.buy_threshold
    assert calm - wild == pytest.approx(35, abs=1)  # the 35% vol component


def test_low_vol_requires_realized_vol():
    strat = LowVolDefensiveStrategy()
    strat.prepare(_universe(50, field='realizedVol', lo=12.0, hi=45.0))
    assert not strat.is_eligible({'ticker': 'X', 'currentPrice': 1.0})
    assert strat.score({'ticker': 'X', 'currentPrice': 1.0}) is None


# ── 52-Week-High Momentum ────────────────────────────────────────────────

def test_fifty_two_week_high_scoring():
    strat = FiftyTwoWeekHighStrategy()
    at_high = {'ticker': 'A', 'currentPrice': 10.0, 'fiftyTwoWeekPosition': 95.0,
               'trendAlignment': 'Strong Uptrend', 'macdStatus': 'BULLISH'}
    assert strat.score(at_high) >= strat.config.buy_threshold  # 66.5+20+7 = 93.5
    slid = {**at_high, 'fiftyTwoWeekPosition': 68.0,
            'trendAlignment': 'Bullish (Mixed)', 'macdStatus': 'BEARISH'}
    assert strat.score(slid) <= strat.config.sell_threshold    # 47.6+15+3 = 65.6
    assert strat.score({'ticker': 'A', 'currentPrice': 10.0}) is None


# ── Sector Rotation (dual momentum) ─────────────────────────────────────

def test_sector_rotation_score_mapping():
    strat = SectorRotationStrategy()
    assert strat.score({'momentum6m': 0.0}) == 50
    assert strat.score({'momentum6m': 15.0}) == 100
    assert strat.score({'momentum6m': -20.0}) == 0   # clamped at −15
    assert strat.score({'momentum6m': None}) is None


def test_sector_rotation_absolute_momentum_gate():
    strat = SectorRotationStrategy()
    row = {'ticker': 'XLK', 'currentPrice': 200.0, 'momentum6m': 8.0}
    assert not strat.is_eligible({**row, 'momentum6mAbs': -2.0})  # falling sector
    assert not strat.is_eligible({**row, 'momentum6mAbs': None})
    assert strat.is_eligible({**row, 'momentum6mAbs': 5.0})


def test_sector_rotation_config():
    cfg = SectorRotationStrategy.config
    assert cfg.max_positions == 3
    assert len(cfg.custom_universe) == 11


# ── Registry contract ────────────────────────────────────────────────────

def test_registry_has_eight_strategies():
    assert len(STRATEGIES) == 8


def test_backtest_safety_flags():
    safe = {sid for sid, s in STRATEGIES.items() if s.historical_backtest_safe}
    assert safe == {'momentum-top10', '52-week-high-top10',
                    'sector-rotation-top3', 'markov-regime'}
