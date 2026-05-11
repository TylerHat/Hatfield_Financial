"""Analyst Conviction — Top 10 strategy.

Filters the universe to consensus `strong_buy` names with at least 3 analysts,
then ranks by **Bayesian-shrunk** target upside %. Shrinkage handles the small-
sample problem: a stock with 2 analysts and 60% upside is heavily corrected
toward the strong_buy universe mean, while a stock with 25 analysts is trusted
almost as-is.

Shrinkage equation (Empirical Bayes / James–Stein):

    adjusted_upside = (n * stock_upside + k * mu) / (n + k)

where
    n            = numberOfAnalysts
    stock_upside = targetUpsidePct
    mu           = mean targetUpsidePct of the strong_buy filtered universe
                   (computed fresh each rebalance in prepare())
    k            = 10  (prior strength — phantom average analysts added to
                   every stock; tuned so the median S&P-500 name retains
                   ~60-65% of its own signal)

The shrunk upside is then mapped to a 0-100 score by clamping to [-10%, +50%]
and linear-scaling. Buy ≥ 60, sell ≤ 50.
"""

from .base import EtfStrategy, StrategyConfig


PRIOR_STRENGTH_K = 10.0
MIN_ANALYSTS = 3
UPSIDE_FLOOR_PCT = -10.0
UPSIDE_CEIL_PCT = 50.0


def _row_qualifies(row: dict) -> bool:
    """Strong_buy consensus + ≥3 analysts + has an upside target."""
    if row.get('recommendationKey') != 'strong_buy':
        return False
    n = row.get('numberOfAnalysts')
    if n is None or n < MIN_ANALYSTS:
        return False
    if row.get('targetUpsidePct') is None:
        return False
    return True


def _shrunk_upside(stock_upside: float, n: int, mu: float, k: float = PRIOR_STRENGTH_K) -> float:
    return (n * stock_upside + k * mu) / (n + k)


def _score_from_upside(shrunk_upside: float) -> int:
    clamped = max(UPSIDE_FLOOR_PCT, min(UPSIDE_CEIL_PCT, shrunk_upside))
    return round((clamped - UPSIDE_FLOOR_PCT) / (UPSIDE_CEIL_PCT - UPSIDE_FLOOR_PCT) * 100)


class AnalystConvictionStrategy(EtfStrategy):
    config = StrategyConfig(
        id='analyst-conviction-top10',
        name='Analyst Conviction — Top 10',
        description=(
            "Buys the top 10 strong_buy-rated names by analyst price target "
            "upside, with Bayesian shrinkage (k=10) so low-coverage outliers "
            "are pulled toward the strong_buy universe mean. Requires ≥3 "
            "analysts. Buy ≥ 60, sell ≤ 50."
        ),
        buy_threshold=60.0,
        sell_threshold=50.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def __init__(self):
        # Set in prepare(); fallback used if prepare() wasn't called (e.g. a
        # one-off score() from serialize_state with no qualifying universe).
        self._mu: float | None = None

    def prepare(self, recs: list[dict]) -> None:
        upsides = [r['targetUpsidePct'] for r in recs if _row_qualifies(r)]
        self._mu = sum(upsides) / len(upsides) if upsides else None

    def is_eligible(self, row: dict) -> bool:
        # Standard liquidity check + our strong_buy / coverage filter.
        if row.get('currentPrice') is None:
            return False
        return _row_qualifies(row)

    def score(self, row: dict):
        if not _row_qualifies(row):
            return None
        if self._mu is None:
            # No qualifying universe to anchor shrinkage — abstain rather than
            # guess. This only happens if score() is called without prepare()
            # having seen any strong_buys (edge case in serialize_state).
            return None
        shrunk = _shrunk_upside(row['targetUpsidePct'], row['numberOfAnalysts'], self._mu)
        return _score_from_upside(shrunk)
