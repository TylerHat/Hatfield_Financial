"""Low Volatility — Defensive Top 10 strategy.

Defensive factor sleeve: ranks the universe by low *cross-sectional*
realized volatility plus balance-sheet quality. Captures the low-volatility
anomaly (Frazzini–Pedersen "Betting Against Beta", Baker–Bradley–Wurgler) —
historically better risk-adjusted returns than CAPM predicts, and
uncorrelated to both Buy Score and Momentum, making it the natural ballast
leg of a 3-factor stool.

Corrected in HFA-069. The original implementation scored `volRatio` —
current ATR divided by the stock's OWN average ATR — i.e. "is this stock
quieter than its own past", a volatility-compression signal. A high-beta
name in a temporary calm scored 100 on the 35% component while a utility at
its normal vol scored 60, so the sleeve wasn't defensive. The corrected
sleeve ranks `realizedVol` (annualized σ of daily returns, ~6 months — see
services/row_features.realized_vol_series) against the rest of the
universe: lowest-vol names score highest, which is the anomaly as actually
documented.

Score components (0-100 weighted blend):
  - Low realized vol       35%   100 − percentile of row['realizedVol']
  - ROE                    20%   row['returnOnEquity']
  - Low debt               15%   row['debtToEquity']
  - Inverted overall risk  15%   row['overallRisk']
  - Gross margin           15%   row['grossMargins']

historical_backtest_safe = False: the quality components (ROE, debt,
margins, governance risk) come from today's .info snapshot — yfinance
serves no point-in-time history for them, so a historical backtest would
apply today's balance sheet to past dates.
"""

from .base import EtfStrategy, StrategyConfig, cross_sectional_percentile


def _roe_score(r):
    if r is None: return 50
    if r >= 0.20: return 100
    if r >= 0.15: return 80
    if r >= 0.10: return 60
    if r >= 0.05: return 40
    if r >= 0: return 20
    return 0


def _debt_score(de):
    if de is None: return 50
    if de < 30: return 100
    if de < 60: return 80
    if de < 100: return 60
    if de < 200: return 40
    return 20


def _gross_margin_score(g):
    if g is None: return 50
    if g >= 0.50: return 100
    if g >= 0.40: return 80
    if g >= 0.30: return 60
    if g >= 0.20: return 40
    if g >= 0.10: return 20
    return 0


def _risk_score(r):
    # yfinance overallRisk is 1 (lowest) to 10 (highest). Invert to 0-100.
    if r is None:
        return 50
    return max(0, min(100, (11 - r) / 10 * 100))


class LowVolDefensiveStrategy(EtfStrategy):
    # ROE / debt / margins / overallRisk are today-snapshot .info fields —
    # not reconstructable historically. See base.EtfStrategy.
    historical_backtest_safe = False

    config = StrategyConfig(
        id='low-vol-defensive',
        name='Low Volatility — Defensive Top 10',
        description=(
            'Buys the top 10 names combining the lowest realized volatility '
            'in the universe (annualized σ, cross-sectional rank) with '
            'balance-sheet quality (high ROE, low debt, durable margins). '
            'Buy at score ≥ 65, sell at ≤ 55. Defensive ballast — captures '
            'the low-vol anomaly; lowest correlation to Buy Score and '
            'Momentum.'
        ),
        buy_threshold=65.0,
        sell_threshold=55.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def __init__(self):
        # Sorted realizedVol values for the current universe; set in prepare().
        self._sorted_vol: list[float] = []

    def prepare(self, recs: list[dict]) -> None:
        self._sorted_vol = sorted(
            r['realizedVol'] for r in recs
            if r.get('realizedVol') is not None and r.get('currentPrice') is not None
        )

    def is_eligible(self, row: dict) -> bool:
        return row.get('currentPrice') is not None and row.get('realizedVol') is not None

    def score(self, row: dict):
        rv = row.get('realizedVol')
        if rv is None:
            return None
        pct = cross_sectional_percentile(self._sorted_vol, rv)
        if pct is None:
            # Universe too small to rank — abstain rather than guess.
            return None
        vol_score = 100 - pct  # lowest vol in the universe → 100

        roe = _roe_score(row.get('returnOnEquity'))
        debt = _debt_score(row.get('debtToEquity'))
        risk = _risk_score(row.get('overallRisk'))
        gm = _gross_margin_score(row.get('grossMargins'))

        composite = (
            vol_score * 0.35
            + roe * 0.20
            + debt * 0.15
            + risk * 0.15
            + gm * 0.15
        )
        return round(composite)
