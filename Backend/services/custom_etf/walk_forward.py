"""Generic walk-forward backtest engine for Custom ETF strategies.

Replays a strategy over history using the SAME decision code the live
simulator runs (services.custom_etf.rebalance_core) against rows rebuilt
point-in-time from price history (services.row_features). Built in HFA-069
to replace the Markov-only backtest, whose hand-rolled rules (rank by raw
bull_5d, force-sell anything outside the day's top 10) had drifted from the
deployed strategy and reported performance the live sleeve couldn't have.

Guarantees:
  - Refuses strategies with `historical_backtest_safe = False` — their
    inputs (.info fundamentals, analyst consensus) exist only as a "today"
    snapshot, so a backtest would leak hindsight (see strategies/base.py).
  - No lookahead: every feature at bar *i* is a trailing computation, the
    Markov transition matrix at a rebalance uses only transitions through
    that bar, and rows are built from data at-or-before the rebalance date.
  - Daily equity marks between rebalances, so max drawdown reflects what a
    holder actually experienced (the old engine marked weekly).
  - Stale-data guards: tickers whose last bar is older than
    MAX_STALE_TRADING_DAYS drop out of the universe (held names force-exit
    at their last close), and NaN closes are dropped up front.

Known, documented limitations (surfaced via result['caveats']):
  - Survivorship bias for the S&P 500 universe (today's constituents).
  - Same-bar execution: decisions use the rebalance day's close and fills
    happen at that close ± slippage.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data_fetcher import get_many_ohlcv, get_spy_period, PRIORITY_MEDIUM
from sp500 import get_sp500_tickers
from services import row_features as rf
from services.markov import classify_regimes, LOOKBACK, REGIME_FULL
from .rebalance_core import run_rebalance_pass
from .backtest_jobs import set_progress, set_done

logger = logging.getLogger(__name__)

# Universe hygiene
MAX_STALE_TRADING_DAYS = 10   # last bar older than this → out of the universe
MIN_BARS = LOOKBACK + 30      # ticker needs at least this much history at all
MIN_MARKOV_TRANSITIONS = 10   # below this the transition matrix is pure noise

# yfinance fetch window: the longest UI option (3y) plus warmup for the
# slowest features (MA200 / 52-week / Markov matrix seasoning).
_BACKTEST_FETCH_PERIOD = '5y'

# Feature-frame columns copied onto each synthesized row, keyed exactly like
# live recommendation rows so strategies can't tell the difference.
_ROW_COLUMNS = (
    'momentum', 'momentum6m', 'momentum6mAbs', 'realizedVol',
    'trendAlignment', 'macdStatus', 'fiftyTwoWeekPosition', 'rsiValue',
    'volRatio',
)


def _row_normalise(counts):
    row_sums = counts.sum(axis=1, keepdims=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(row_sums > 0, counts / np.maximum(row_sums, 1), 1.0 / 3.0)


def _generate_rebalance_dates(start, end, cadence, trading_days_index):
    """Rebalance dates aligned to actual trading days. Weekly = the first
    trading day of each ISO (year, week) — ISO year avoids splitting the
    New-Year week across two keys."""
    in_window = trading_days_index[(trading_days_index >= start) & (trading_days_index <= end)]
    if len(in_window) == 0:
        return []
    if cadence == 'daily':
        return list(in_window)
    seen_weeks = set()
    out = []
    for d in in_window:
        iso = d.isocalendar()
        wk = (iso[0], iso[1])
        if wk in seen_weeks:
            continue
        seen_weeks.add(wk)
        out.append(d)
    return out


def _naive_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.tz_localize(None) if idx.tz is not None else idx


def _clean_value(v):
    """numpy/NaN → JSON-friendly python value (None for NaN)."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    v = float(v)
    return None if (np.isnan(v) or np.isinf(v)) else v


def _prepare_ticker(hist: pd.DataFrame, spy_close: pd.Series | None) -> dict | None:
    """Per-ticker precomputation: cleaned closes, vectorized feature arrays,
    Markov regimes + cumulative transition counts."""
    hist = hist[hist['Close'].notna()]
    if len(hist) <= MIN_BARS:
        return None
    hist = hist.copy()
    hist.index = _naive_index(hist.index)

    frame = rf.compute_feature_frame(hist, spy_close)
    close = hist['Close'].to_numpy(dtype=float)
    regime = classify_regimes(close)
    n = len(regime)

    # Per-bar transition events cumulated along axis 0: cum_counts[k+1]
    # holds every transition observable through bar k. int16 caps at 32k —
    # far above the ~1250 bars a 5y fetch produces.
    events = np.zeros((n + 1, 3, 3), dtype=np.int16)
    for j in range(1, n):
        prev_r = regime[j - 1]
        curr_r = regime[j]
        if prev_r != -1 and curr_r != -1:
            events[j + 1, prev_r, curr_r] = 1
    cum_counts = np.cumsum(events, axis=0, dtype=np.int16)

    return {
        'dates': hist.index,
        'close': close,
        'features': {col: frame[col].to_numpy() for col in _ROW_COLUMNS},
        'regime': regime,
        'cum_counts': cum_counts,
    }


def _bar_index_at(data: dict, when: pd.Timestamp) -> int:
    """Index of the latest bar at or before `when`, or -1."""
    return int(data['dates'].searchsorted(when, side='right')) - 1


def _build_row(ticker: str, data: dict, idx: int) -> dict:
    """Synthesize the recommendation-style row this ticker would have
    carried at bar `idx` — price features plus Markov forecast fields."""
    row = {'ticker': ticker, 'currentPrice': float(data['close'][idx])}
    for col in _ROW_COLUMNS:
        row[col] = _clean_value(data['features'][col][idx])

    row['markovRegime'] = None
    row['markovBull3d'] = None
    row['markovBull5d'] = None
    row['markovBear5d'] = None
    r = int(data['regime'][idx])
    if r != -1:
        counts = data['cum_counts'][idx + 1]
        if counts.sum() >= MIN_MARKOV_TRANSITIONS:
            P = _row_normalise(counts)
            P3 = np.linalg.matrix_power(P, 3)
            P5 = P3 @ P @ P
            # Internal regime order is [Side, Bull, Bear].
            row['markovRegime'] = REGIME_FULL[r]
            row['markovBull3d'] = float(P3[r, 1])
            row['markovBull5d'] = float(P5[r, 1])
            row['markovBear5d'] = float(P5[r, 2])
    return row


def run_walk_forward(
    strategy,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    cadence: str,
    period: str = _BACKTEST_FETCH_PERIOD,
    progress_cb=None,
) -> dict:
    """Walk-forward simulation of `strategy` between two dates.

    Pure simulation — does not touch the job tracker or the live DB.
    Raises ValueError for strategies flagged historical_backtest_safe=False.
    """
    t_start = time.time()
    cadence = cadence if cadence in ('weekly', 'daily') else 'weekly'
    if progress_cb is None:
        progress_cb = lambda pct, msg: None  # noqa: E731 — tiny default sink

    if not strategy.historical_backtest_safe:
        raise ValueError(
            f'Strategy {strategy.config.id} is not historical-backtest-safe: it scores '
            'today-snapshot fields (fundamentals / analyst consensus) that yfinance '
            'cannot serve point-in-time, so a backtest would leak hindsight.'
        )

    # Fresh instance: registered strategies are process-wide singletons and
    # prepare() carries per-universe state — a backtest thread must not
    # clobber the instance live requests are scoring with.
    strategy = strategy.__class__()
    cfg = strategy.config

    if cfg.custom_universe:
        universe = list(cfg.custom_universe)
        progress_cb(2, f'Using fixed {len(universe)}-ticker universe...')
    else:
        progress_cb(2, 'Loading S&P 500 universe...')
        universe = get_sp500_tickers()
        if not universe:
            raise RuntimeError('Could not load S&P 500 ticker list')

    progress_cb(5, f'Fetching {period} of OHLC for {len(universe)} tickers (may take a few minutes on a cold cache)...')
    all_ohlc = get_many_ohlcv(universe, period=period, priority=PRIORITY_MEDIUM)

    progress_cb(28, f'Fetched OHLC for {len(all_ohlc)} tickers — pulling SPY benchmark...')
    spy_dates = None
    spy_closes = None
    spy_close_series = None
    spy_hist = get_spy_period(period, priority=PRIORITY_MEDIUM)
    if spy_hist is not None and not spy_hist.empty:
        spy_close_series = spy_hist['Close'].dropna()
        spy_close_series.index = _naive_index(spy_close_series.index)
        spy_dates = spy_close_series.index
        spy_closes = spy_close_series.to_numpy(dtype=float)
    else:
        logger.warning('SPY history unavailable — momentum will be absolute and the equity curve will omit the benchmark')

    progress_cb(30, 'Pre-computing features and regimes...')
    ticker_data = {}
    bad_tickers = 0
    for i, ticker in enumerate(universe):
        if (i + 1) % 100 == 0:
            progress_cb(30 + (i / max(1, len(universe))) * 15,
                        f'Pre-computed {i + 1}/{len(universe)} tickers')
        hist = all_ohlc.get(ticker)
        if hist is None or hist.empty:
            bad_tickers += 1
            continue
        try:
            data = _prepare_ticker(hist, spy_close_series)
        except Exception as e:
            logger.warning('feature precompute failed for %s: %s', ticker, e)
            bad_tickers += 1
            continue
        if data is None:
            bad_tickers += 1
            continue
        ticker_data[ticker] = data

    logger.info('Backtest preprocessing (%s): %d tickers ready, %d skipped',
                cfg.id, len(ticker_data), bad_tickers)
    if not ticker_data:
        raise RuntimeError('No tickers had usable history for the requested window')

    # Trading-day calendar: SPY when available (it trades every US session),
    # else the ticker with the longest history.
    if spy_dates is not None and len(spy_dates) > 0:
        calendar = spy_dates
    else:
        reference = max(ticker_data, key=lambda t: len(ticker_data[t]['dates']))
        calendar = ticker_data[reference]['dates']

    mark_days = calendar[(calendar >= start_date) & (calendar <= end_date)]
    rebalance_dates = _generate_rebalance_dates(start_date, end_date, cadence, calendar)
    if not rebalance_dates:
        raise RuntimeError('No rebalance dates fall within the requested window')
    rebalance_set = set(rebalance_dates)

    def _calendar_pos(when) -> int:
        return int(calendar.searchsorted(when, side='right')) - 1

    progress_cb(47, f'Walking forward across {len(rebalance_dates)} rebalances ({cadence})...')

    # ── Portfolio state ────────────────────────────────────────────────
    cash = cfg.starting_capital
    book: dict[str, dict] = {}       # ticker → {shares, avg_cost, entry_score}
    entry_meta: dict[str, dict] = {}  # ticker → {date, price} for trade enrichment
    equity_curve = []
    trades = []
    spy_baseline_price = None
    rebalances_done = 0

    for day in mark_days:
        # ── Rebalance on schedule ──────────────────────────────────────
        if day in rebalance_set:
            rebalances_done += 1
            if rebalances_done == 1 or rebalances_done % 5 == 0:
                pct = 47 + (rebalances_done / len(rebalance_dates)) * 50
                progress_cb(pct, f'Rebalance {rebalances_done}/{len(rebalance_dates)} ({day.strftime("%Y-%m-%d")})')

            day_pos = _calendar_pos(day)
            rows = []
            for ticker, data in ticker_data.items():
                idx = _bar_index_at(data, day)
                if idx < 0:
                    continue
                # Staleness guard: last bar must be recent in *trading days*
                # — a halted/delisted name silently marking at an old close
                # poisons sizing and P&L (HFA-069 M2).
                if day_pos - _calendar_pos(data['dates'][idx]) > MAX_STALE_TRADING_DAYS:
                    continue
                rows.append(_build_row(ticker, data, idx))

            def _last_close(ticker, _day=day):
                data = ticker_data.get(ticker)
                if data is None:
                    return None
                idx = _bar_index_at(data, _day)
                return float(data['close'][idx]) if idx >= 0 else None

            res = run_rebalance_pass(strategy, rows, book, cash,
                                     resolve_missing_price=_last_close)
            cash = res['cash']
            book = res['positions']

            date_str = day.strftime('%Y-%m-%d')
            for s in res['sells']:
                meta = entry_meta.pop(s['ticker'], {})
                pnl = (s['price'] - s['avg_cost']) * s['shares']
                pnl_pct = (s['price'] / s['avg_cost'] - 1) * 100 if s['avg_cost'] else 0
                trades.append({
                    'date': date_str,
                    'ticker': s['ticker'],
                    'action': 'SELL',
                    'shares': round(s['shares'], 4),
                    'price': round(s['price'], 2),
                    'value': round(s['proceeds'], 2),
                    'reason': s['reason'],
                    'score': s['score'],
                    'entryDate': meta.get('date'),
                    'entryPrice': round(meta['price'], 2) if meta.get('price') else round(s['avg_cost'], 2),
                    'pnl': round(pnl, 2),
                    'pnlPct': round(pnl_pct, 2),
                    'status': 'CLOSED',
                    'cash_after': round(s['cash_after'], 2),
                })
            for b in res['buys']:
                entry_meta[b['ticker']] = {'date': date_str, 'price': b['price']}
                trades.append({
                    'date': date_str,
                    'ticker': b['ticker'],
                    'action': 'BUY',
                    'shares': round(b['shares'], 4),
                    'price': round(b['price'], 2),
                    'value': round(b['cost'], 2),
                    'score': b['score'],
                    'weight': round(b['weight'], 2),
                    'cash_after': round(b['cash_after'], 2),
                })

        # ── Daily equity mark (every trading day, not just rebalances) ─
        positions_value = 0.0
        for ticker, pos in book.items():
            data = ticker_data.get(ticker)
            if data is not None:
                idx = _bar_index_at(data, day)
                mark = float(data['close'][idx]) if idx >= 0 else pos['avg_cost']
            else:
                mark = pos['avg_cost']
            positions_value += pos['shares'] * mark
        total_value = cash + positions_value

        spy_value = None
        spy_close = None
        if spy_dates is not None and len(spy_dates) > 0:
            sidx = int(spy_dates.searchsorted(day, side='right')) - 1
            if sidx >= 0:
                spy_close = float(spy_closes[sidx])
                if spy_baseline_price is None:
                    spy_baseline_price = spy_close
                if spy_baseline_price > 0:
                    spy_value = round(cfg.starting_capital * (spy_close / spy_baseline_price), 2)

        equity_curve.append({
            'date': day.strftime('%Y-%m-%d'),
            'value': round(total_value, 2),
            'cash': round(cash, 2),
            'positionsValue': round(positions_value, 2),
            'spyValue': spy_value,
            'spy_close': round(spy_close, 4) if spy_close is not None else None,
        })

    progress_cb(97, 'Computing summary statistics...')

    # ── Final mark-to-market for open positions ────────────────────────
    open_positions = []
    final_value = cash
    for ticker, pos in book.items():
        data = ticker_data.get(ticker)
        if data is not None and len(data['close']) > 0:
            mark = float(data['close'][-1])
        else:
            mark = pos['avg_cost']
        market_value = pos['shares'] * mark
        final_value += market_value
        unreal_pnl = market_value - pos['shares'] * pos['avg_cost']
        unreal_pnl_pct = (mark / pos['avg_cost'] - 1) * 100 if pos['avg_cost'] else 0
        open_positions.append({
            'ticker': ticker,
            'shares': round(pos['shares'], 4),
            'avgCost': round(pos['avg_cost'], 2),
            'currentPrice': round(mark, 2),
            'marketValue': round(market_value, 2),
            'unrealizedPnl': round(unreal_pnl, 2),
            'unrealizedPnlPct': round(unreal_pnl_pct, 2),
            'entryDate': entry_meta.get(ticker, {}).get('date'),
        })

    # ── Summary statistics ─────────────────────────────────────────────
    closed = [t for t in trades if t['action'] == 'SELL']
    wins = [t for t in closed if t['pnl'] > 0]
    losses = [t for t in closed if t['pnl'] <= 0]
    num_trades = len(closed)
    win_rate = (len(wins) / num_trades * 100) if num_trades > 0 else 0
    avg_win_pct = sum(t['pnlPct'] for t in wins) / len(wins) if wins else 0
    avg_loss_pct = sum(t['pnlPct'] for t in losses) / len(losses) if losses else 0
    avg_win_dollar = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
    avg_loss_dollar = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
    win_loss_ratio = abs(avg_win_pct / avg_loss_pct) if avg_loss_pct != 0 else None
    profit_factor = (sum(t['pnl'] for t in wins) / abs(sum(t['pnl'] for t in losses))
                     if losses and sum(t['pnl'] for t in losses) != 0 else None)

    total_return = ((final_value / cfg.starting_capital) - 1) * 100

    # Max drawdown — peak-to-trough on the DAILY equity curve.
    peak = cfg.starting_capital
    max_dd = 0.0
    for pt in equity_curve:
        peak = max(peak, pt['value'])
        if peak > 0:
            dd = (pt['value'] - peak) / peak * 100
            max_dd = min(max_dd, dd)

    best_trade = max((t['pnlPct'] for t in closed), default=0)
    worst_trade = min((t['pnlPct'] for t in closed), default=0)

    spy_return = None
    vs_spy = None
    last_spy = next((pt['spyValue'] for pt in reversed(equity_curve) if pt.get('spyValue') is not None), None)
    if last_spy is not None and cfg.starting_capital > 0:
        spy_return = (last_spy / cfg.starting_capital - 1) * 100
        vs_spy = total_return - spy_return

    elapsed = time.time() - t_start
    logger.info('Walk-forward %s done in %.1fs: return=%.1f%%, trades=%d, win_rate=%.1f%%',
                cfg.id, elapsed, total_return, num_trades, win_rate)

    caveats = [
        {
            'id': 'execution-timing',
            'severity': 'note',
            'title': 'Execution-timing note',
            'message': (
                'Decisions and fills both use the rebalance day\'s close '
                '(± slippage). Live rebalances run the morning after the '
                'signal, so backtested fills are mildly optimistic.'
            ),
        },
    ]
    if not cfg.custom_universe:
        caveats.insert(0, {
            'id': 'survivorship-bias',
            'severity': 'note',
            'title': 'Survivorship-bias note',
            'message': (
                "Uses today's S&P 500 constituents. Stocks that were "
                'delisted before today are excluded from older windows, '
                'mildly inflating measured returns over multi-year tests. '
                'Not fixable without a point-in-time membership table.'
            ),
        })

    return {
        'summary': {
            'startingCapital': cfg.starting_capital,
            'finalValue': round(final_value, 2),
            'totalReturn': round(total_return, 2),
            'totalReturnDollar': round(final_value - cfg.starting_capital, 2),
            'numTrades': num_trades,
            'numWins': len(wins),
            'numLosses': len(losses),
            'winRate': round(win_rate, 2),
            'winLossRatio': round(win_loss_ratio, 2) if win_loss_ratio is not None else None,
            'avgWinPct': round(avg_win_pct, 2),
            'avgLossPct': round(avg_loss_pct, 2),
            'avgWinDollar': round(avg_win_dollar, 2),
            'avgLossDollar': round(avg_loss_dollar, 2),
            'profitFactor': round(profit_factor, 2) if profit_factor is not None else None,
            'bestTrade': round(best_trade, 2),
            'worstTrade': round(worst_trade, 2),
            'maxDrawdown': round(max_dd, 2),
            'rebalances': len(rebalance_dates),
            'tickersAnalyzed': len(ticker_data),
            'cashAtEnd': round(cash, 2),
            'openPositions': len(open_positions),
            'spyReturn': round(spy_return, 2) if spy_return is not None else None,
            'vsSpy': round(vs_spy, 2) if vs_spy is not None else None,
        },
        'equityCurve': equity_curve,
        'trades': trades,
        'openPositions': open_positions,
        'caveats': caveats,
        'params': {
            'strategyId': cfg.id,
            'strategyName': cfg.name,
            'cadence': cadence,
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d'),
            'startingCapital': cfg.starting_capital,
            'maxPositions': cfg.max_positions,
            'buyThreshold': cfg.buy_threshold,
            'sellThreshold': cfg.sell_threshold,
            'slippageBps': cfg.slippage_bps,
            'universeSize': len(universe),
        },
        'elapsedSeconds': round(elapsed, 1),
    }


def run_generic_backtest(job_id: str, strategy_id: str, years: int, cadence: str) -> None:
    """Job-tracker wrapper: map the UI's `years` knob to explicit dates,
    run the walk-forward, write progress + result under `job_id`."""
    from .strategies import get_strategy

    strategy = get_strategy(strategy_id)
    if strategy is None:
        raise ValueError(f'Unknown strategy: {strategy_id}')

    cadence = cadence if cadence in ('weekly', 'daily') else 'weekly'
    years = years if years in (1, 3) else 1

    end_date = pd.Timestamp(datetime.now(timezone.utc).date())
    start_date = end_date - pd.DateOffset(years=years)

    def _cb(pct, msg):
        set_progress(job_id, pct, msg)

    result = run_walk_forward(strategy, start_date, end_date, cadence,
                              period=_BACKTEST_FETCH_PERIOD, progress_cb=_cb)
    result['params']['years'] = years
    set_done(job_id, result)
