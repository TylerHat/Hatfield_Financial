"""52-Week-High Momentum — Top 10 strategy. Added in HFA-069.

George & Hwang (2004): proximity to the 52-week high predicts returns
better than plain past-return momentum — anchoring makes investors slow to
bid a stock through a salient reference price, so names pressing their
highs keep drifting. The effect is distinct from (and complementary to) the
6-1 month return factor in `momentum-top10`.

Score components (0-100 weighted blend):
  - 52-week position       70%   row['fiftyTwoWeekPosition'] (0 = at 52w
                                 low, 100 = at 52w high)
  - Trend alignment        20%   row['trendAlignment']
  - MACD status            10%   row['macdStatus']

Buy ≥ 85 admits only names within ~10-15% of their high AND in an uptrend;
sell ≤ 70 exits once a holding slides roughly a third down its 52-week
range or the trend breaks. Wide buy/sell hysteresis keeps turnover low —
the GH effect plays out over months.

All inputs are price-derived → historical_backtest_safe = True.
"""

from .base import EtfStrategy, StrategyConfig


_TREND_MAP = {
    'Strong Uptrend': 100, 'Bullish (Mixed)': 75, 'Bullish (Short-term)': 75,
    'N/A': 50, 'Bearish (Mixed)': 25, 'Bearish (Short-term)': 25, 'Strong Downtrend': 0,
}
_MACD_MAP = {
    'BULLISH CROSSOVER': 100, 'BULLISH': 70, 'BEARISH': 30, 'BEARISH CROSSOVER': 0,
}


def compute_fifty_two_week_high_score(row: dict):
    pos52 = row.get('fiftyTwoWeekPosition')
    if pos52 is None:
        return None
    trend = _TREND_MAP.get(row.get('trendAlignment'), 50)
    macd = _MACD_MAP.get(row.get('macdStatus'), 50)
    composite = pos52 * 0.70 + trend * 0.20 + macd * 0.10
    return round(composite)


class FiftyTwoWeekHighStrategy(EtfStrategy):
    # fiftyTwoWeekPosition / trendAlignment / macdStatus are all price-derived.
    historical_backtest_safe = True

    config = StrategyConfig(
        id='52-week-high-top10',
        name='52-Week-High Momentum — Top 10',
        description=(
            'Buys the top 10 names pressing their 52-week highs, confirmed '
            'by trend alignment and MACD (George–Hwang anchoring effect). '
            'Buy at score ≥ 85, sell at ≤ 70 — exits once a holding slides '
            'about a third down its 52-week range or the trend breaks.'
        ),
        buy_threshold=85.0,
        sell_threshold=70.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def is_eligible(self, row: dict) -> bool:
        return (row.get('currentPrice') is not None
                and row.get('fiftyTwoWeekPosition') is not None)

    def score(self, row: dict):
        return compute_fifty_two_week_high_score(row)
