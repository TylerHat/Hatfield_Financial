"""Sector Momentum Rotation — Top 3 SPDR sectors. Added in HFA-069.

Dual-momentum sector rotation (Antonacci): hold the sector ETFs with the
strongest 6-1 month RELATIVE momentum vs SPY, but only while their
ABSOLUTE 6-1 month return is positive. When a sector's own trend turns
negative it becomes ineligible regardless of relative rank — in broad bear
markets nothing qualifies and the sleeve sits in cash, which is the
defensive half of the dual-momentum design.

Universe: the 11 SPDR select-sector ETFs (fixed `custom_universe` — rows
are built from price history by services/custom_etf/custom_universe.py, not
the S&P 500 recommendations snapshot).

Score: 6-1M excess return vs SPY, clamped ±15% and scaled to 0-100
(0% excess = 50). Buy ≥ 60 (≈ +3% excess), sell ≤ 45 (≈ −1.5% excess) —
the asymmetric band gives a modest hold hysteresis so leadership rotations,
not noise, drive turnover.

All inputs are price-derived → historical_backtest_safe = True.
"""

from .base import EtfStrategy, StrategyConfig


SECTOR_ETFS = (
    'XLB',   # Materials
    'XLC',   # Communication Services
    'XLE',   # Energy
    'XLF',   # Financials
    'XLI',   # Industrials
    'XLK',   # Technology
    'XLP',   # Consumer Staples
    'XLRE',  # Real Estate
    'XLU',   # Utilities
    'XLV',   # Health Care
    'XLY',   # Consumer Discretionary
)

EXCESS_CLAMP_PCT = 15.0   # ±15% 6-1M excess return maps to the 0-100 ends


def compute_sector_rotation_score(row: dict):
    excess = row.get('momentum6m')
    if excess is None:
        return None
    clamped = max(-EXCESS_CLAMP_PCT, min(EXCESS_CLAMP_PCT, excess))
    return round((clamped + EXCESS_CLAMP_PCT) / (2 * EXCESS_CLAMP_PCT) * 100)


class SectorRotationStrategy(EtfStrategy):
    # momentum6m / momentum6mAbs are price-derived.
    historical_backtest_safe = True

    config = StrategyConfig(
        id='sector-rotation-top3',
        name='Sector Rotation — Top 3 Momentum',
        description=(
            'Rotates among the 11 SPDR sector ETFs: holds the top 3 by '
            '6-1 month return vs SPY, and only while the sector\'s own '
            '6-1 month return is positive (dual momentum — falls back to '
            'cash in broad downtrends). Buy at score ≥ 60, sell at ≤ 45.'
        ),
        buy_threshold=60.0,
        sell_threshold=45.0,
        max_positions=3,
        starting_capital=100_000.0,
        slippage_bps=5.0,
        custom_universe=SECTOR_ETFS,
    )

    def is_eligible(self, row: dict) -> bool:
        if row.get('currentPrice') is None or row.get('momentum6m') is None:
            return False
        # Absolute-momentum gate: the sector's own 6-1M return must be
        # positive. Relative winners inside a falling market don't qualify.
        abs_mom = row.get('momentum6mAbs')
        return abs_mom is not None and abs_mom > 0

    def score(self, row: dict):
        return compute_sector_rotation_score(row)
