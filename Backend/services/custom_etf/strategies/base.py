"""Strategy interface for the Custom ETF simulator.

Each strategy declares a config (thresholds, capital, sizing) and a `score`
function that maps a recommendation row → 0-100 score. The simulator engine
in services.custom_etf.simulator is strategy-agnostic and consumes any
EtfStrategy subclass through this interface.

Adding a new ETF: drop a new file in strategies/, subclass EtfStrategy, and
register it in strategies/__init__.py.
"""

from abc import ABC, abstractmethod
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

# Below this many observations a cross-sectional percentile is noise —
# prepare()-based strategies abstain rather than rank within a tiny sample.
MIN_UNIVERSE_FOR_PERCENTILE = 20


def cross_sectional_percentile(sorted_values, value):
    """Percentile rank (0-100) of ``value`` within ``sorted_values``
    (ascending list). Mid-rank convention for ties; min → 0, max → 100.
    Returns None when the sample is smaller than
    MIN_UNIVERSE_FOR_PERCENTILE. Used by strategies that rank a raw factor
    (momentum, realized vol) against the day's universe instead of an
    absolute curve — self-calibrating across market regimes.
    """
    n = len(sorted_values)
    if n < MIN_UNIVERSE_FOR_PERCENTILE:
        return None
    lo = bisect_left(sorted_values, value)
    hi = bisect_right(sorted_values, value)
    rank = (lo + hi - 1) / 2
    return max(0.0, min(100.0, rank / (n - 1) * 100))


@dataclass(frozen=True)
class StrategyConfig:
    id: str
    name: str
    description: str
    buy_threshold: float = 70.0
    sell_threshold: float = 65.0
    max_positions: int = 10
    starting_capital: float = 100_000.0
    slippage_bps: float = 5.0  # 0.05 % per fill
    # When set, the strategy trades this fixed ticker list instead of the
    # S&P 500 recommendations universe. Rows for these tickers are built
    # from price history via services/row_features (see
    # services.custom_etf.custom_universe). Tuple, not list — the dataclass
    # is frozen and configs are module-level singletons.
    custom_universe: tuple = None

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'buyThreshold': self.buy_threshold,
            'sellThreshold': self.sell_threshold,
            'maxPositions': self.max_positions,
            'startingCapital': self.starting_capital,
            'slippageBps': self.slippage_bps,
            'customUniverse': list(self.custom_universe) if self.custom_universe else None,
        }


class EtfStrategy(ABC):
    config: StrategyConfig

    # True when the strategy only consumes fields that are point-in-time
    # reconstructable from price/volume data alone (which is what yfinance
    # serves us historically). False when the strategy depends on
    # forward-looking analyst consensus data — `targetUpsidePct`,
    # `numberOfAnalysts`, `recommendationKey` — that yfinance only ever
    # returns at the "today" snapshot. A historical backtest using those
    # values on past dates leaks ~5-15% of hindsight into measured
    # returns. A future backtest engine should refuse / warn for any
    # strategy with this flag set to False.
    historical_backtest_safe: bool = True

    @abstractmethod
    def score(self, row: dict):
        """Return a 0-100 score for the recommendation row, or None if the
        row cannot be scored (e.g. missing required fields)."""

    def is_eligible(self, row: dict) -> bool:
        """Optional eligibility filter. Default: any row with a current price."""
        return row.get('currentPrice') is not None

    def prepare(self, recs: list[dict]) -> None:
        """Optional hook called once per rebalance before scoring begins.
        Use to compute universe-wide statistics (e.g. mean values for
        Bayesian shrinkage) that individual score() calls need."""
        pass

    def weight(self, row: dict) -> float:
        """Optional conviction weight for position sizing. The simulator
        normalises returned weights across selected candidates so they sum
        to 1.0 of allocatable equity. Default 1.0 → equal weight (preserves
        the historical behavior for strategies that don't override this).

        Return must be > 0; non-positive values are clamped to 1.0 to avoid
        zeroing out a position the strategy already passed score() for."""
        return 1.0
