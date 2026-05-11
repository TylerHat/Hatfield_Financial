"""Buy Score strategy — port of Frontend/src/components/Recommendations.js
computeBuyScore. Kept structurally identical so that the backend simulator
agrees with the score the user sees in the Recommendations table.

Weights and curves must stay in sync with the JS implementation. If the JS
formula changes, mirror the change here.
"""

from .base import EtfStrategy, StrategyConfig


def _pe_score(pe):
    if pe is None or pe <= 0:
        return 50
    if pe < 10: return 100
    if pe < 15: return 80
    if pe < 20: return 60
    if pe < 30: return 40
    if pe < 50: return 20
    return 5


def _fcf_yield_score(y):
    if y is None: return 50
    if y >= 0.08: return 100
    if y >= 0.06: return 80
    if y >= 0.04: return 60
    if y >= 0.02: return 40
    if y >= 0: return 20
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


def _avg(values):
    v = [x for x in values if x is not None]
    if not v:
        return 50
    return sum(v) / len(v)


def _growth_score(g):
    if g is None:
        return None
    c = max(-0.5, min(0.5, g))
    return (c + 0.5) / 1.0 * 100


def _vol_ratio_score(vr):
    if vr is None: return 50
    if vr < 0.7: return 80
    if vr <= 1.5: return 50
    return 20


_TREND_MAP = {
    'Strong Uptrend': 100, 'Bullish (Mixed)': 75, 'Bullish (Short-term)': 75,
    'N/A': 50, 'Bearish (Mixed)': 30, 'Bearish (Short-term)': 30, 'Strong Downtrend': 0,
}
_MACD_MAP = {
    'BULLISH CROSSOVER': 100, 'BULLISH': 65, 'BEARISH': 35, 'BEARISH CROSSOVER': 0,
}
_REC_MAP = {'strong_buy': 100, 'buy': 75, 'hold': 50, 'sell': 25, 'strong_sell': 0}


def compute_buy_score(row: dict) -> int:
    components = []

    # Valuation 18 %
    valuation = _avg([_pe_score(row.get('forwardPE')), _fcf_yield_score(row.get('fcfYield'))])
    components.append((0.18, valuation))

    # Trend composite 25 %
    trend_val = _TREND_MAP.get(row.get('trendAlignment'), 50)
    macd_val = _MACD_MAP.get(row.get('macdStatus'), 50)
    mom_val = 50
    if row.get('momentum') is not None:
        clamped = max(-20, min(20, row['momentum']))
        mom_val = (clamped + 20) / 40 * 100
    trend_composite = trend_val * 0.5 + mom_val * 0.3 + macd_val * 0.2
    components.append((0.25, trend_composite))

    # Analyst sentiment 12 %
    components.append((0.06, _REC_MAP.get(row.get('recommendationKey'), 50)))
    upside_val = 50
    if row.get('targetUpsidePct') is not None:
        clamped = max(-10, min(30, row['targetUpsidePct']))
        upside_val = (clamped + 10) / 40 * 100
    components.append((0.06, upside_val))

    # Quality 10 %
    quality = _avg([
        _roe_score(row.get('returnOnEquity')),
        _debt_score(row.get('debtToEquity')),
        _gross_margin_score(row.get('grossMargins')),
    ])
    components.append((0.10, quality))

    # Growth 10 %
    eg = _growth_score(row.get('epsGrowth'))
    rg = _growth_score(row.get('revenueGrowth'))
    growth = 50 if eg is None and rg is None else _avg([eg, rg])
    components.append((0.10, growth))

    # 52w position 8 %
    pos52 = row.get('fiftyTwoWeekPosition') if row.get('fiftyTwoWeekPosition') is not None else 50
    components.append((0.08, pos52))

    # Volatility 7 %
    components.append((0.07, _vol_ratio_score(row.get('volRatio'))))

    # RSI (regime-conditioned) 5 %
    rsi_val = 50
    in_strong_trend = row.get('trendAlignment') in ('Strong Uptrend', 'Strong Downtrend')
    if row.get('rsiValue') is not None and not in_strong_trend:
        r = row['rsiValue']
        rsi_val = 100 if r < 30 else 85 if r < 40 else 60 if r < 55 else 40 if r < 70 else 15
    components.append((0.05, rsi_val))

    # Governance 3 %
    gov_val = 50
    if row.get('overallRisk') is not None:
        gov_val = (11 - row['overallRisk']) / 10 * 100
    components.append((0.03, gov_val))

    # Coverage 2 %
    cov_val = 50
    if row.get('numberOfAnalysts') is not None:
        cov_val = min(100, row['numberOfAnalysts'] / 20 * 100)
    components.append((0.02, cov_val))

    return round(sum(w * v for w, v in components))


class BuyScoreStrategy(EtfStrategy):
    config = StrategyConfig(
        id='buy-score-top10',
        name='Buy Score — Top 10 Green',
        description=(
            'Buys the top-ranked stocks with Buy Score ≥ 70 (max 10 holdings), '
            'sells when the score drops to ≤ 65. Equal-weight cash allocation '
            'across new buys; rebalanced when the Recommendations universe '
            'refreshes (24h cooldown).'
        ),
        buy_threshold=70.0,
        sell_threshold=65.0,
        max_positions=10,
        starting_capital=100_000.0,
        slippage_bps=5.0,
    )

    def score(self, row: dict):
        return compute_buy_score(row)
