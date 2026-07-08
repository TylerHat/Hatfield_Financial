"""Walk-forward engine tests on fully synthetic data (no network):
refusal of lookahead-unsafe strategies, daily equity marking, stale-ticker
force-exit, and the no-lookahead decision property (HFA-069)."""

import numpy as np
import pandas as pd
import pytest

from services.custom_etf import walk_forward as wf
from services.custom_etf.strategies.buy_score import BuyScoreStrategy
from services.custom_etf.strategies.fifty_two_week_high import FiftyTwoWeekHighStrategy

N_BARS = 600
END = pd.Timestamp('2026-06-30')
DATES = pd.bdate_range(end=END, periods=N_BARS)


def _hist_from_close(close: np.ndarray, dates=DATES) -> pd.DataFrame:
    s = pd.Series(close, index=dates[:len(close)])
    return pd.DataFrame({'Open': s, 'High': s * 1.01, 'Low': s * 0.99,
                         'Close': s, 'Volume': 1_000_000.0}, index=s.index)


def _drift_path(drift, vol=0.01, seed=0, n=N_BARS):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))


@pytest.fixture()
def synthetic_market(monkeypatch):
    """28 tickers: UPxx trending up (bought), FLAT/DOWN (never bought),
    STALE trends up but its data ends halfway (must be force-exited)."""
    universe = {}
    for i in range(25):
        universe[f'UP{i:02d}'] = _hist_from_close(_drift_path(0.0008 + i * 0.00004, seed=i))
    universe['FLAT'] = _hist_from_close(_drift_path(0.0, seed=100))
    universe['DOWN'] = _hist_from_close(_drift_path(-0.002, seed=101))
    universe['STALE'] = _hist_from_close(_drift_path(0.003, vol=0.004, seed=102)[:N_BARS - 130])

    spy = _hist_from_close(_drift_path(0.0004, vol=0.006, seed=200))

    monkeypatch.setattr(wf, 'get_sp500_tickers', lambda: list(universe))
    monkeypatch.setattr(wf, 'get_many_ohlcv',
                        lambda tickers, period=None, priority=None, **kw:
                        {t: universe[t] for t in tickers if t in universe})
    monkeypatch.setattr(wf, 'get_spy_period', lambda period, priority=None: spy)
    return universe


def _run(start, end, cadence='weekly'):
    return wf.run_walk_forward(FiftyTwoWeekHighStrategy(), start, end, cadence)


def test_refuses_backtest_unsafe_strategy(synthetic_market):
    with pytest.raises(ValueError, match='not historical-backtest-safe'):
        wf.run_walk_forward(BuyScoreStrategy(), END - pd.DateOffset(years=1), END, 'weekly')


def test_walk_forward_basics(synthetic_market):
    start = END - pd.DateOffset(years=1)
    result = _run(start, END)
    s = result['summary']

    # Daily equity marks: ~261 business days, far more points than rebalances.
    assert len(result['equityCurve']) > 200
    assert s['rebalances'] < 60
    assert len(result['equityCurve']) > s['rebalances'] * 3

    # Every mark is a finite number and the curve starts near capital.
    values = [p['value'] for p in result['equityCurve']]
    assert all(np.isfinite(v) for v in values)
    assert values[0] == pytest.approx(100_000, rel=0.05)

    # SPY benchmark is populated and anchored at starting capital.
    assert result['equityCurve'][0]['spyValue'] == pytest.approx(100_000, abs=1)

    # Uptrending names get bought; FLAT and DOWN never do.
    bought = {t['ticker'] for t in result['trades'] if t['action'] == 'BUY'}
    assert bought and all(t.startswith(('UP', 'STALE')) for t in bought)

    # Live semantics run through the shared core: fills carry slippage and
    # trades carry the live reason codes.
    reasons = {t.get('reason') for t in result['trades'] if t['action'] == 'SELL'}
    assert reasons <= {'SCORE_DROP', 'EXIT_UNIVERSE'}

    # Caveats are structured for the UI.
    assert {c['id'] for c in result['caveats']} == {'survivorship-bias', 'execution-timing'}


def test_stale_ticker_is_force_exited(synthetic_market):
    """STALE's data ends ~130 bars before the window closes: the staleness
    guard must exit it near the cutoff and never hold it to the end."""
    start = END - pd.DateOffset(years=1)
    result = _run(start, END)

    assert all(p['ticker'] != 'STALE' for p in result['openPositions'])
    stale_sells = [t for t in result['trades']
                   if t['ticker'] == 'STALE' and t['action'] == 'SELL']
    if stale_sells:  # it was bought at some point — must exit via the guard
        last_bar = synthetic_market['STALE'].index[-1]
        exit_dates = [pd.Timestamp(t['date']) for t in stale_sells]
        assert max(exit_dates) <= last_bar + pd.Timedelta(days=25)
        assert stale_sells[-1]['reason'] == 'EXIT_UNIVERSE'


def test_no_lookahead_in_decisions(synthetic_market, monkeypatch):
    """Trades through date D must be identical whether or not data after D
    exists — the defining property of a walk-forward backtest."""
    start = END - pd.DateOffset(years=1)
    full = _run(start, END)

    mid = END - pd.DateOffset(months=6)
    truncated_universe = {t: h[h.index <= mid] for t, h in synthetic_market.items()}
    spy_full = wf.get_spy_period('5y')
    monkeypatch.setattr(wf, 'get_many_ohlcv',
                        lambda tickers, period=None, priority=None, **kw:
                        {t: truncated_universe[t] for t in tickers if t in truncated_universe})
    monkeypatch.setattr(wf, 'get_spy_period',
                        lambda period, priority=None: spy_full[spy_full.index <= mid])
    trunc = _run(start, mid)

    def key(trades):
        return [(t['date'], t['ticker'], t['action'], round(t['shares'], 4), t['price'])
                for t in trades if pd.Timestamp(t['date']) <= mid]

    assert key(full['trades']) == key(trunc['trades'])
