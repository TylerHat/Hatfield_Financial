"""Momentum — Top 10 Trending strategy.

Pure trend factor: ranks the universe by trailing price momentum confirmed by
trend-quality signals (alignment, MACD, 52-week position). Designed to be
low-correlation to the Buy Score strategy so the two run as complementary
factor sleeves.

Score components (0-100 weighted blend):
  - Price momentum         50%   row['momentum'], clamped -20% → +40%
  - Trend alignment        25%   row['trendAlignment']
  - MACD status            15%   row['macdStatus']
  - 52-week position       10%   row['fiftyTwoWeekPosition']
"""

from .base import EtfStrategy, StrategyConfig


_TREND_MAP = {
    'Strong Uptrend': 100, 'Bullish (Mixed)': 75, 'Bullish (Short-term)': 75,
    'N/A': 50, 'Bearish (Mixed)': 25, 'Bearish (Short-term)': 25, 'Strong Downtrend': 0,
}
_MACD_MAP = {
    'BULLISH CROSSOVER': 100, 'BULLISH': 70, 'BEARISH': 30, 'BEARISH CROSSOVER': 0,
}


def _momentum_score(m):
    if m is None:
        return None
    clamped = max(-20, min(40, m))
    return (clamped + 20) / 60 * 100


def compute_momentum_score(row: dict):
    mom = _momentum_score(row.get('momentum'))
    if mom is None:
        return None

    trend = _TREND_MAP.get(row.get('trendAlignment'), 50)
    macd = _MACD_MAP.get(row.get('macdStatus'), 50)
    pos52 = row.get('fiftyTwoWeekPosition') if row.get('fiftyTwoWeekPosition') is not None else 50

    composite = mom * 0.50 + trend * 0.25 + macd * 0.15 + pos52 * 0.10
    return round(composite)


class MomentumTop10Strategy(EtfStrategy):
    config = StrategyConfig(
        id='momentum-top10',
        name='Momentum — Top 10 Trending',
        description=(
            'Buys the top 10 names with the strongest trailing price momentum '
            'confirmed by trend alignment and MACD. Buy at score ≥ 70, sell at '
            '≤ 60. Pure trend factor — low correlation to Buy Score, captures '
            'the academic momentum premium (Jegadeesh–Titman / Carhart).'
        ),
        buy_threshold=70.0,
        sell_threshold=60.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def score(self, row: dict):
        return compute_momentum_score(row)
