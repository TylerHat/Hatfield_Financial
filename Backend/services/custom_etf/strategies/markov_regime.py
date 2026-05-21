"""Markov Regime — Conviction-Weighted Bull strategy.

Per-ticker Markov regime classification (Bull / Bear / Sideways) with a 3×3
transition matrix forecast. Buys names with the highest 5-day bull
probability, sized in proportion to conviction. Sells on bear transition or
forecast degradation. Based on Lewis Jackson's Markov hedge-fund framework
(theory.pine).

The score below blends three Markov-derived inputs from the recommendation row
(populated during prewarm by routes/recommendations.py):

  - markovBull5d  — P(Bull in 5 days), weighted 50%
  - markovBull3d  — P(Bull in 3 days), weighted 30%
  - markovRegime  — current regime label, weighted 10% (Bull only)
  - markovBear5d  — penalised at weighting 10% (1 − P(Bear in 5d))

A row missing any markov* field returns None so the simulator skips it.
"""

from .base import EtfStrategy, StrategyConfig


def compute_markov_score(row: dict):
    bull_5d = row.get('markovBull5d')
    bull_3d = row.get('markovBull3d')
    bear_5d = row.get('markovBear5d')
    regime = row.get('markovRegime')

    if bull_5d is None or bull_3d is None or bear_5d is None or regime is None:
        return None

    is_bull = 1.0 if regime == 'Bull' else 0.0
    bear_avoid = 1.0 - bear_5d

    composite = (
        0.50 * bull_5d
        + 0.30 * bull_3d
        + 0.10 * is_bull
        + 0.10 * bear_avoid
    )
    return round(max(0.0, min(1.0, composite)) * 100, 1)


class MarkovRegimeStrategy(EtfStrategy):
    config = StrategyConfig(
        id='markov-regime',
        name='Markov Regime — Conviction-Weighted Bull',
        description=(
            'Per-ticker Markov regime model (Bull/Bear/Sideways) with a 3x3 '
            'transition matrix. Score blends 5-day and 3-day bull-probability '
            'forecasts with bear-avoidance and current-regime confirmation. '
            'Position size scales linearly with bull conviction — a 90% bull '
            'forecast gets ~5x the allocation of a marginal 55% pick. Sells on '
            'bear transition or forecast degradation. Based on Lewis Jackson / '
            'Roan\'s Markov hedge-fund framework.'
        ),
        buy_threshold=65.0,
        sell_threshold=50.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def score(self, row: dict):
        return compute_markov_score(row)

    def is_eligible(self, row: dict) -> bool:
        # Standard liquidity gate + require Markov data to be present.
        if row.get('currentPrice') is None:
            return False
        if row.get('markovBull5d') is None or row.get('markovBear5d') is None:
            return False
        # Hard guard: don't let a Bear-regime stock enter the universe even
        # if the bull forecast happens to nudge above the buy bar — the rule
        # set is "don't catch falling knives." The same guard is enforced
        # again by sell_threshold once held.
        if row.get('markovRegime') == 'Bear':
            return False
        if row.get('markovBear5d') >= 0.35:
            return False
        return True

    def weight(self, row: dict) -> float:
        # Linear lift above 0.50 bull-prob. 50% → weight 1.0, 90% → 5.0.
        # Stocks just above the buy bar get a baseline allocation; high-
        # conviction stocks get up to ~5× more dollars.
        bull_5d = row.get('markovBull5d') or 0.5
        return max(1.0, 1.0 + (bull_5d - 0.5) * 10.0)
