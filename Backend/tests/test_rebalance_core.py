"""rebalance_core semantics tests — the decision math shared by the live
simulator and the walk-forward backtest engine (HFA-069)."""

import pytest

from services.custom_etf.rebalance_core import run_rebalance_pass, score_universe
from services.custom_etf.strategies.base import EtfStrategy, StrategyConfig


class FakeStrategy(EtfStrategy):
    """Scores come straight off the row; optional per-ticker weights."""
    config = StrategyConfig(
        id='fake', name='Fake', description='',
        buy_threshold=70.0, sell_threshold=60.0,
        max_positions=4, starting_capital=100_000.0, slippage_bps=100.0,  # 1% for visible math
    )

    def __init__(self, weights=None):
        self._weights = weights or {}

    def score(self, row):
        return row.get('fakeScore')

    def weight(self, row):
        return self._weights.get(row.get('ticker'), 1.0)


def _row(ticker, price, score):
    return {'ticker': ticker, 'currentPrice': price, 'fakeScore': score}


SLIP = 0.01  # 100 bps


def test_sell_score_drop_and_exit_universe():
    strat = FakeStrategy()
    rows = [_row('KEEP', 100.0, 80), _row('DROP', 50.0, 55)]
    positions = {
        'KEEP': {'shares': 10.0, 'avg_cost': 90.0},
        'DROP': {'shares': 20.0, 'avg_cost': 60.0},
        'GONE': {'shares': 5.0, 'avg_cost': 40.0},
    }
    res = run_rebalance_pass(strat, rows, positions, cash=0.0,
                             resolve_missing_price=lambda t: 44.0)

    by_ticker = {s['ticker']: s for s in res['sells']}
    assert by_ticker['DROP']['reason'] == 'SCORE_DROP'
    assert by_ticker['DROP']['price'] == pytest.approx(50.0 * (1 - SLIP))
    assert by_ticker['GONE']['reason'] == 'EXIT_UNIVERSE'
    assert by_ticker['GONE']['price'] == pytest.approx(44.0 * (1 - SLIP))
    assert [k['ticker'] for k in res['kept']] == ['KEEP']
    # Original book must not be mutated.
    assert set(positions) == {'KEEP', 'DROP', 'GONE'}


def test_exit_universe_without_resolver_books_at_cost():
    strat = FakeStrategy()
    res = run_rebalance_pass(strat, [], {'GONE': {'shares': 5.0, 'avg_cost': 40.0}}, cash=0.0)
    (sell,) = res['sells']
    assert sell['price'] == pytest.approx(40.0)   # avg_cost, no slippage
    assert sell['proceeds'] == pytest.approx(200.0)


def test_equal_weight_buy_sizing_against_total_equity():
    strat = FakeStrategy()
    rows = [_row('A', 100.0, 90), _row('B', 200.0, 85)]
    res = run_rebalance_pass(strat, rows, {}, cash=100_000.0)

    assert [b['ticker'] for b in res['buys']] == ['A', 'B']  # score desc
    # target = min(equity/4 * 2, 99% cash) = 50k → 25k per name
    for b in res['buys']:
        assert b['cost'] == pytest.approx(25_000.0, rel=1e-9)
    assert res['cash'] == pytest.approx(50_000.0, rel=1e-9)
    # Buy fills at price * (1 + slippage).
    assert res['buys'][0]['price'] == pytest.approx(100.0 * (1 + SLIP))
    assert res['positions']['A']['entry_score'] == 90


def test_conviction_weights_split_the_same_budget():
    strat = FakeStrategy(weights={'A': 3.0, 'B': 1.0})
    rows = [_row('A', 100.0, 90), _row('B', 200.0, 85)]
    res = run_rebalance_pass(strat, rows, {}, cash=100_000.0)
    buys = {b['ticker']: b for b in res['buys']}
    assert buys['A']['cost'] == pytest.approx(37_500.0, rel=1e-9)  # 75% of 50k
    assert buys['B']['cost'] == pytest.approx(12_500.0, rel=1e-9)  # 25% of 50k


def test_buy_slots_respect_max_positions_and_held_names():
    strat = FakeStrategy()
    rows = [_row(t, 10.0, 90 - i) for i, t in enumerate(['A', 'B', 'C', 'D', 'E'])]
    positions = {'H1': {'shares': 1.0, 'avg_cost': 5.0}}
    rows.append(_row('H1', 10.0, 80))  # held, keeps
    res = run_rebalance_pass(strat, rows, positions, cash=10_000.0)
    assert len(res['buys']) == 3            # 4 max − 1 held
    assert {b['ticker'] for b in res['buys']} == {'A', 'B', 'C'}
    assert 'H1' in res['positions']


def test_cash_never_goes_negative():
    strat = FakeStrategy()
    rows = [_row('A', 100.0, 90)]
    res = run_rebalance_pass(strat, rows, {}, cash=50.0)
    assert res['cash'] >= 0.0
    if res['buys']:
        assert res['buys'][0]['cost'] <= 50.0


def test_threshold_boundaries():
    """Buy requires score >= threshold; sell requires score <= threshold."""
    strat = FakeStrategy()
    rows = [_row('EDGE', 10.0, 70)]  # exactly at buy bar
    res = run_rebalance_pass(strat, rows, {}, cash=1_000.0)
    assert [b['ticker'] for b in res['buys']] == ['EDGE']

    rows = [_row('EDGE', 10.0, 60)]  # exactly at sell bar
    res = run_rebalance_pass(strat, rows, {'EDGE': {'shares': 1.0, 'avg_cost': 9.0}}, cash=0.0)
    assert res['sells'] and res['sells'][0]['reason'] == 'SCORE_DROP'


def test_score_universe_skips_ineligible_and_unscorable():
    class Picky(FakeStrategy):
        def is_eligible(self, row):
            return row.get('ok', True)

    rows = [_row('A', 10.0, 80), {**_row('B', 10.0, 80), 'ok': False},
            _row('C', 10.0, None)]
    uni = score_universe(Picky(), rows)
    assert set(uni) == {'A'}
