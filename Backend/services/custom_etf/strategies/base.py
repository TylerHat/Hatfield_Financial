"""Strategy interface for the Custom ETF simulator.

Each strategy declares a config (thresholds, capital, sizing) and a `score`
function that maps a recommendation row → 0-100 score. The simulator engine
in services.custom_etf.simulator is strategy-agnostic and consumes any
EtfStrategy subclass through this interface.

Adding a new ETF: drop a new file in strategies/, subclass EtfStrategy, and
register it in strategies/__init__.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


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
        }


class EtfStrategy(ABC):
    config: StrategyConfig

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
