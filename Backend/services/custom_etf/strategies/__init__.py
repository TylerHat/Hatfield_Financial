"""Strategy registry — the single place to register new Custom ETFs.

────────────────────────────────────────────────────────────────────────
HOWTO add a new ETF
────────────────────────────────────────────────────────────────────────
1. Drop a new file in this directory, e.g. `momentum_top10.py`:

       from .base import EtfStrategy, StrategyConfig

       class MomentumTop10Strategy(EtfStrategy):
           config = StrategyConfig(
               id='momentum-top10',                # URL slug, must be unique
               name='Momentum — Top 10',
               description='Buys top 10 by 1-month return vs SPY.',
               buy_threshold=70.0,
               sell_threshold=65.0,
               max_positions=10,
               starting_capital=100_000.0,
               slippage_bps=5.0,
           )

           def score(self, row):
               # Return a 0-100 score from a recommendations row, or None.
               m = row.get('momentum')
               if m is None:
                   return None
               return max(0, min(100, (m + 20) / 40 * 100))

2. Add the class to the tuple below.

That's it — the simulator, persistence, API endpoints, and frontend
sidebar all key off `config.id` and pick it up automatically. The first
rebalance will create a fresh $100k portfolio for the new strategy.
"""

from .base import EtfStrategy, StrategyConfig
from .buy_score import BuyScoreStrategy

# Register every strategy here.
_REGISTERED = (
    BuyScoreStrategy(),
    # MomentumTop10Strategy(),  # ← add new strategies here
)

STRATEGIES = {s.config.id: s for s in _REGISTERED}


def get_strategy(strategy_id):
    return STRATEGIES.get(strategy_id)


def list_strategies():
    return list(STRATEGIES.values())


__all__ = ['EtfStrategy', 'StrategyConfig', 'STRATEGIES', 'get_strategy', 'list_strategies']
