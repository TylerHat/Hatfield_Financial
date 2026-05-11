"""Low Volatility — Defensive Top 10 strategy.

Defensive factor sleeve: ranks the universe by low realized volatility plus
balance-sheet quality. Captures the low-volatility anomaly (Frazzini–Pedersen
"Betting Against Beta", Baker–Bradley–Wurgler) — historically delivers better
risk-adjusted returns than CAPM predicts, and is uncorrelated to both Buy
Score and Momentum, making it the natural ballast leg of a 3-factor stool.

Score components (0-100 weighted blend):
  - Low vol-ratio          35%   row['volRatio']
  - ROE                    20%   row['returnOnEquity']
  - Low debt               15%   row['debtToEquity']
  - Inverted overall risk  15%   row['overallRisk']
  - Gross margin           15%   row['grossMargins']
"""

from .base import EtfStrategy, StrategyConfig


def _low_vol_score(vr):
    if vr is None:
        return None
    if vr < 0.7: return 100
    if vr < 0.9: return 85
    if vr <= 1.1: return 60
    if vr <= 1.5: return 30
    return 0


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


def compute_low_vol_score(row: dict):
    vol = _low_vol_score(row.get('volRatio'))
    if vol is None:
        return None

    roe = _roe_score(row.get('returnOnEquity'))
    debt = _debt_score(row.get('debtToEquity'))
    risk = _risk_score(row.get('overallRisk'))
    gm = _gross_margin_score(row.get('grossMargins'))

    composite = (
        vol * 0.35
        + roe * 0.20
        + debt * 0.15
        + risk * 0.15
        + gm * 0.15
    )
    return round(composite)


class LowVolDefensiveStrategy(EtfStrategy):
    config = StrategyConfig(
        id='low-vol-defensive',
        name='Low Volatility — Defensive Top 10',
        description=(
            'Buys the top 10 names combining low realized volatility with '
            'balance-sheet quality (high ROE, low debt, durable margins). Buy '
            'at score ≥ 65, sell at ≤ 55. Defensive ballast — captures the '
            'low-vol anomaly; lowest correlation to Buy Score and Momentum.'
        ),
        buy_threshold=65.0,
        sell_threshold=55.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def score(self, row: dict):
        return compute_low_vol_score(row)
