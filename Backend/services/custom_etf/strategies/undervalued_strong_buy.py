"""Undervalued Strong Buy — Top 10 strategy.

Pairs with `analyst-conviction-top10`: same strong_buy + coverage filter, but
the ranking is a multi-factor blend that weights valuation alongside analyst
upside, with a quality guard to filter the worst value traps.

Eligibility (strong_buy universe + value-trap guard)
    - recommendationKey == 'strong_buy'
    - numberOfAnalysts >= 3
    - targetUpsidePct is not None
    - forwardPE or fcfYield available (so valuation isn't pure fallback)
    - returnOnEquity >= 0
    - debtToEquity is None or < 200

Ranking (0-100)
    score = 0.50 * valuation + 0.40 * shrunk_upside + 0.10 * quality

Components reuse the established helpers:
    valuation        — buy_score._pe_score + _fcf_yield_score, averaged
    shrunk_upside    — analyst_conviction Bayesian shrinkage (k=10),
                       linear-scaled from [-10%, +50%] → [0, 100]
    quality          — buy_score._roe_score + _debt_score + _gross_margin_score,
                       averaged

The strong_buy mean upside (mu) is recomputed each rebalance in prepare().
"""

from .base import EtfStrategy, StrategyConfig
from .buy_score import (
    _pe_score, _fcf_yield_score,
    _roe_score, _debt_score, _gross_margin_score,
    _avg,
)


PRIOR_STRENGTH_K = 10.0
MIN_ANALYSTS = 3
UPSIDE_FLOOR_PCT = -10.0
UPSIDE_CEIL_PCT = 50.0
MAX_DEBT_TO_EQUITY = 200.0

W_VALUATION = 0.50
W_UPSIDE = 0.40
W_QUALITY = 0.10


def _row_qualifies(row: dict) -> bool:
    if row.get('recommendationKey') != 'strong_buy':
        return False
    n = row.get('numberOfAnalysts')
    if n is None or n < MIN_ANALYSTS:
        return False
    if row.get('targetUpsidePct') is None:
        return False
    # Need at least one valuation input — otherwise the valuation component
    # collapses to the 50-fallback and we're really just ranking on upside.
    if row.get('forwardPE') is None and row.get('fcfYield') is None:
        return False
    # Value-trap guard: drop names with negative ROE or extreme leverage.
    roe = row.get('returnOnEquity')
    if roe is not None and roe < 0:
        return False
    de = row.get('debtToEquity')
    if de is not None and de >= MAX_DEBT_TO_EQUITY:
        return False
    return True


def _shrunk_upside(stock_upside: float, n: int, mu: float, k: float = PRIOR_STRENGTH_K) -> float:
    return (n * stock_upside + k * mu) / (n + k)


def _upside_to_score(shrunk_upside: float) -> float:
    clamped = max(UPSIDE_FLOOR_PCT, min(UPSIDE_CEIL_PCT, shrunk_upside))
    return (clamped - UPSIDE_FLOOR_PCT) / (UPSIDE_CEIL_PCT - UPSIDE_FLOOR_PCT) * 100


class UndervaluedStrongBuyStrategy(EtfStrategy):
    # Same forward-looking analyst inputs as analyst_conviction —
    # backtest leaks hindsight. See base.EtfStrategy.historical_backtest_safe.
    historical_backtest_safe = False

    config = StrategyConfig(
        id='undervalued-strong-buy-top10',
        name='Undervalued Strong Buy — Top 10',
        description=(
            "Buys the top 10 strong_buy-rated names ranked by a valuation-led "
            "blend: 50% valuation (forwardPE + FCF yield), 40% Bayesian-shrunk "
            "analyst upside, 10% quality (ROE, debt, gross margin). Requires "
            "≥3 analysts, positive ROE, and debt/equity < 200. Buy ≥ 65, "
            "sell ≤ 55."
        ),
        buy_threshold=65.0,
        sell_threshold=55.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def __init__(self):
        self._mu: float | None = None

    def prepare(self, recs: list[dict]) -> None:
        upsides = [r['targetUpsidePct'] for r in recs if _row_qualifies(r)]
        self._mu = sum(upsides) / len(upsides) if upsides else None

    def is_eligible(self, row: dict) -> bool:
        if row.get('currentPrice') is None:
            return False
        return _row_qualifies(row)

    def score(self, row: dict):
        if not _row_qualifies(row):
            return None
        if self._mu is None:
            return None

        valuation = _avg([
            _pe_score(row.get('forwardPE')),
            _fcf_yield_score(row.get('fcfYield')),
        ])

        shrunk = _shrunk_upside(
            row['targetUpsidePct'], row['numberOfAnalysts'], self._mu,
        )
        upside = _upside_to_score(shrunk)

        quality = _avg([
            _roe_score(row.get('returnOnEquity')),
            _debt_score(row.get('debtToEquity')),
            _gross_margin_score(row.get('grossMargins')),
        ])

        return round(
            W_VALUATION * valuation
            + W_UPSIDE * upside
            + W_QUALITY * quality
        )
