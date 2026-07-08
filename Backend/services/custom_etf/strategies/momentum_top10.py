"""Momentum — Top 10 Trending strategy.

Cross-sectional momentum factor: ranks the universe by 6-1 month excess
return (the Jegadeesh–Titman / Carhart construction — the trailing 6-month
window ending one month ago, relative to SPY), confirmed by trend-quality
signals. Designed to be low-correlation to the Buy Score strategy so the two
run as complementary factor sleeves.

Corrected in HFA-069. The original implementation ranked on `momentum`
(1-MONTH relative return) — the horizon where short-term *reversal*
dominates, the opposite of the cited momentum premium — and its absolute
0-100 mapping needed a ~+10% one-month excess move to clear the buy bar, so
the sleeve sat in cash outside earnings-pop months. The corrected sleeve:

  - ranks on `momentum6m` (6-1M excess return, % — see
    services/row_features.momentum_6m1m_series), and
  - maps it to a cross-sectional percentile within the day's universe
    (prepare() hook), so "strong momentum" always means "strong vs peers
    today", not "strong vs a hard-coded bar" — self-calibrating across
    high- and low-dispersion markets.

Score components (0-100 weighted blend):
  - Momentum percentile     50%   rank of row['momentum6m'] in the universe
  - Trend alignment         25%   row['trendAlignment']
  - MACD status             15%   row['macdStatus']
  - 52-week position        10%   row['fiftyTwoWeekPosition']

The trend/MACD confirmations double as a soft absolute-momentum gate: in a
broad downtrend even the best relative-momentum names lose ~15-20 composite
points from bearish confirmations and fall below the buy bar, pushing the
sleeve toward cash.

All inputs are price-derived → historical_backtest_safe = True: the
walk-forward engine can reconstruct every field point-in-time.
"""

from .base import EtfStrategy, StrategyConfig, cross_sectional_percentile


_TREND_MAP = {
    'Strong Uptrend': 100, 'Bullish (Mixed)': 75, 'Bullish (Short-term)': 75,
    'N/A': 50, 'Bearish (Mixed)': 25, 'Bearish (Short-term)': 25, 'Strong Downtrend': 0,
}
_MACD_MAP = {
    'BULLISH CROSSOVER': 100, 'BULLISH': 70, 'BEARISH': 30, 'BEARISH CROSSOVER': 0,
}


class MomentumTop10Strategy(EtfStrategy):
    # Every input (momentum6m, trendAlignment, macdStatus,
    # fiftyTwoWeekPosition) is reconstructable from price history alone.
    historical_backtest_safe = True

    config = StrategyConfig(
        id='momentum-top10',
        name='Momentum — Top 10 Trending',
        description=(
            'Buys the top 10 names by 6-1 month excess return vs SPY '
            '(cross-sectional percentile), confirmed by trend alignment and '
            'MACD. Buy at score ≥ 70, sell at ≤ 60. Classic Jegadeesh–Titman '
            'momentum — skips the most recent month, where returns '
            'mean-revert. Low correlation to Buy Score.'
        ),
        buy_threshold=70.0,
        sell_threshold=60.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def __init__(self):
        # Sorted momentum6m values for the current universe; set in prepare().
        self._sorted_mom: list[float] = []

    def prepare(self, recs: list[dict]) -> None:
        self._sorted_mom = sorted(
            r['momentum6m'] for r in recs
            if r.get('momentum6m') is not None and r.get('currentPrice') is not None
        )

    def score(self, row: dict):
        m = row.get('momentum6m')
        if m is None:
            return None
        pct = cross_sectional_percentile(self._sorted_mom, m)
        if pct is None:
            # Universe too small to rank — abstain rather than guess.
            return None

        trend = _TREND_MAP.get(row.get('trendAlignment'), 50)
        macd = _MACD_MAP.get(row.get('macdStatus'), 50)
        pos52 = row.get('fiftyTwoWeekPosition') if row.get('fiftyTwoWeekPosition') is not None else 50

        composite = pct * 0.50 + trend * 0.25 + macd * 0.15 + pos52 * 0.10
        return round(composite)
