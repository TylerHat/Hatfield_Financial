"""Portfolio-level backtest for the Markov Regime ETF strategy.

Walks forward through history rebalancing a $100k portfolio on the configured
cadence (weekly or daily). At each rebalance date, computes the Markov
forecast for every S&P 500 ticker using only data UP TO that date (no
look-ahead bias), picks the top-10 by 5-day bull probability, sizes positions
by conviction weight, and rolls forward.

Survivorship-bias caveat: uses today's S&P 500 constituents. Stocks that were
delisted before today won't appear in older windows — inflates measured returns
slightly. UI surfaces this disclaimer next to the result.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from data_fetcher import get_many_ohlcv, get_spy_history, PRIORITY_MEDIUM
from sp500 import get_sp500_tickers
from services.markov import classify_regimes, LOOKBACK
from .backtest_jobs import set_progress, set_done

logger = logging.getLogger(__name__)

# Strategy constants — kept in sync with MarkovRegimeStrategy.
STARTING_CAPITAL = 100_000.0
MAX_POSITIONS = 10
SLIPPAGE = 5.0 / 10_000.0   # 5 bps per fill
BULL_5D_MIN_FLOOR = 0.30    # sanity floor — don't pick anything below this even if top 10
BEAR_5D_BUY_CAP = 0.35
MIN_TRANSITIONS = 10        # need this many observed transitions before signals fire

# Map years → yfinance period string. Period needs to cover backtest window
# PLUS ~1.5 years of warmup so the matrix has enough history at bar 0.
_YEARS_TO_PERIOD = {
    1: '5y',
    3: '5y',
}


def _row_normalise(counts):
    row_sums = counts.sum(axis=1, keepdims=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(row_sums > 0, counts / np.maximum(row_sums, 1), 1.0 / 3.0)


def _generate_rebalance_dates(start, end, cadence, trading_days_index):
    """Generate rebalance dates aligned to actual trading days. `trading_days_index`
    is a sorted DatetimeIndex of real trading days (we use the SPY series for this).
    """
    # Trim trading days to the backtest window.
    in_window = trading_days_index[(trading_days_index >= start) & (trading_days_index <= end)]
    if len(in_window) == 0:
        return []

    if cadence == 'daily':
        return list(in_window)

    # Weekly: first trading day each ISO calendar week. Use ISO year too —
    # the last days of December can fall in ISO week 1 of the next year, and
    # mixing calendar-year with ISO-week would split that week across two
    # tuple keys.
    seen_weeks = set()
    out = []
    for d in in_window:
        iso = d.isocalendar()
        wk = (iso[0], iso[1])   # (iso_year, iso_week)
        if wk in seen_weeks:
            continue
        seen_weeks.add(wk)
        out.append(d)
    return out


def run_markov_portfolio_backtest(job_id: str, years: int, cadence: str) -> None:
    """Run a Markov-regime portfolio backtest. Writes progress + final result
    into the job tracker keyed by `job_id`.
    """
    t_start = time.time()
    cadence = cadence if cadence in ('weekly', 'daily') else 'weekly'
    years = years if years in (1, 3) else 1

    end_date = pd.Timestamp(datetime.utcnow().date())
    start_date = end_date - pd.DateOffset(years=years)

    set_progress(job_id, 2, 'Loading S&P 500 universe...')
    universe = get_sp500_tickers()
    if not universe:
        raise RuntimeError('Could not load S&P 500 ticker list')

    period = _YEARS_TO_PERIOD.get(years, '5y')
    set_progress(job_id, 5, f'Fetching {period} of OHLC for {len(universe)} tickers (may take a few minutes on a cold cache)...')

    # Bulk OHLC fetch — uses the per-ticker cache, so reruns are fast.
    all_ohlc = get_many_ohlcv(universe, period=period, priority=PRIORITY_MEDIUM)
    set_progress(job_id, 28, f'Fetched OHLC for {len(all_ohlc)} tickers — pulling SPY benchmark...')

    # SPY benchmark — fetch the full window so we can mark-to-baseline at each
    # rebalance. The history endpoint expects timezone-naive datetimes covering
    # the full backtest range; pad a little so the first rebalance lands inside.
    spy_fetch_start = (start_date - pd.DateOffset(days=10)).to_pydatetime()
    spy_fetch_end = (end_date + pd.DateOffset(days=2)).to_pydatetime()
    spy_hist = get_spy_history(spy_fetch_start, spy_fetch_end, priority=PRIORITY_MEDIUM)
    spy_dates = None
    spy_closes = None
    if spy_hist is not None and not spy_hist.empty:
        spy_idx = spy_hist.index
        if spy_idx.tz is not None:
            spy_idx = spy_idx.tz_localize(None)
        spy_dates = spy_idx
        spy_closes = spy_hist['Close'].to_numpy(dtype=float)
    else:
        logger.warning('SPY history unavailable — equity curve will omit benchmark')

    set_progress(job_id, 30, f'Fetched OHLC for {len(all_ohlc)} tickers — pre-computing regimes...')

    # Pre-compute per-ticker regime arrays + cumulative transition counts.
    # cum_counts[k+1] holds transitions observable through bar k (i.e., using
    # transition k-1 → k for k ≥ 1). Lookup at rebalance time is O(1).
    ticker_data = {}
    bad_tickers = 0
    for i, ticker in enumerate(universe):
        if (i + 1) % 100 == 0:
            set_progress(job_id, 30 + (i / len(universe)) * 15,
                         f'Pre-computed {i+1}/{len(universe)} tickers')

        hist = all_ohlc.get(ticker)
        if hist is None or hist.empty or len(hist) <= LOOKBACK + 30:
            bad_tickers += 1
            continue

        close = hist['Close'].to_numpy(dtype=float)
        regime = classify_regimes(close)
        n = len(regime)

        cum_counts = np.zeros((n + 1, 3, 3), dtype=int)
        for j in range(1, n):
            cum_counts[j + 1] = cum_counts[j]
            prev_r = regime[j - 1]
            curr_r = regime[j]
            if prev_r != -1 and curr_r != -1:
                cum_counts[j + 1, prev_r, curr_r] += 1

        # Make index tz-naive so comparison with start/end pd.Timestamp works.
        idx = hist.index
        if idx.tz is not None:
            idx = idx.tz_localize(None)

        ticker_data[ticker] = {
            'close': close,
            'dates': idx,
            'regime': regime,
            'cum_counts': cum_counts,
        }

    logger.info('Backtest preprocessing: %d tickers ready, %d skipped',
                len(ticker_data), bad_tickers)

    if not ticker_data:
        raise RuntimeError('No tickers had usable history for the requested window')

    # Reference trading-day calendar — use the ticker with the longest history
    # to ensure rebalance dates align to a real trading day for SOMETHING.
    reference_ticker = max(ticker_data, key=lambda t: len(ticker_data[t]['dates']))
    trading_days = ticker_data[reference_ticker]['dates']

    rebalance_dates = _generate_rebalance_dates(start_date, end_date, cadence, trading_days)
    if not rebalance_dates:
        raise RuntimeError('No rebalance dates fall within the requested window')

    set_progress(job_id, 47, f'Walking forward across {len(rebalance_dates)} rebalances ({cadence})...')

    # ── Portfolio state ────────────────────────────────────────────────────
    cash = STARTING_CAPITAL
    positions = {}   # ticker → {shares, avg_cost, entry_date, entry_bull_5d}
    equity_curve = []
    trades = []
    spy_baseline_price = None   # SPY close at the first rebalance — anchors the benchmark line at STARTING_CAPITAL

    for k, rebal_date in enumerate(rebalance_dates):
        if (k + 1) % 5 == 0 or k == 0:
            pct = 47 + (k / len(rebalance_dates)) * 50
            set_progress(job_id, pct,
                         f'Rebalance {k+1}/{len(rebalance_dates)} ({rebal_date.strftime("%Y-%m-%d")})')

        # Score the universe at this rebalance date.
        candidates = []   # list of (ticker, bull_5d, bear_5d, regime, price)
        for ticker, data in ticker_data.items():
            dates = data['dates']
            # Latest bar at or before rebal_date.
            idx = dates.searchsorted(rebal_date, side='right') - 1
            if idx < LOOKBACK + 10:
                continue
            r = int(data['regime'][idx])
            if r == -1:
                continue

            counts = data['cum_counts'][idx + 1]
            if counts.sum() < MIN_TRANSITIONS:
                continue

            P = _row_normalise(counts)
            try:
                P5 = np.linalg.matrix_power(P, 5)
            except Exception:
                continue
            bull_5d = float(P5[r, 1])
            bear_5d = float(P5[r, 2])
            price = float(data['close'][idx])

            # Eligibility gate — mirrors MarkovRegimeStrategy.is_eligible.
            if r == 2 or bear_5d >= BEAR_5D_BUY_CAP:
                continue
            if bull_5d < BULL_5D_MIN_FLOOR:
                continue

            candidates.append((ticker, bull_5d, bear_5d, r, price))

        # Pick top 10 by 5-day bull probability.
        candidates.sort(key=lambda c: c[1], reverse=True)
        top10 = candidates[:MAX_POSITIONS]
        top10_tickers = {c[0] for c in top10}

        # Sell holdings no longer in top 10.
        for ticker in list(positions.keys()):
            if ticker in top10_tickers:
                continue
            pos = positions[ticker]
            data = ticker_data.get(ticker)
            if data is not None:
                idx = data['dates'].searchsorted(rebal_date, side='right') - 1
                sell_price_raw = float(data['close'][idx]) if idx >= 0 else pos['avg_cost']
            else:
                sell_price_raw = pos['avg_cost']
            sell_price = sell_price_raw * (1 - SLIPPAGE)
            proceeds = pos['shares'] * sell_price
            pnl = proceeds - pos['shares'] * pos['avg_cost']
            pnl_pct = (sell_price / pos['avg_cost'] - 1) * 100 if pos['avg_cost'] else 0

            cash += proceeds
            trades.append({
                'date': rebal_date.strftime('%Y-%m-%d'),
                'ticker': ticker,
                'action': 'SELL',
                'shares': round(pos['shares'], 4),
                'price': round(sell_price, 2),
                'value': round(proceeds, 2),
                'entryDate': pos['entry_date'],
                'entryPrice': round(pos['avg_cost'], 2),
                'pnl': round(pnl, 2),
                'pnlPct': round(pnl_pct, 2),
                'status': 'CLOSED',
            })
            del positions[ticker]

        # Mark held positions to current price so new buys can be sized vs.
        # *total equity*, not just cash.
        held_value = 0.0
        for ticker, pos in positions.items():
            data = ticker_data.get(ticker)
            if data is not None:
                idx = data['dates'].searchsorted(rebal_date, side='right') - 1
                mark = float(data['close'][idx]) if idx >= 0 else pos['avg_cost']
            else:
                mark = pos['avg_cost']
            held_value += pos['shares'] * mark
        total_equity = cash + held_value

        # Buy new picks (those in top10 we don't already hold).
        new_picks = [c for c in top10 if c[0] not in positions]

        if new_picks and cash > 0:
            # Weight by conviction — same formula as MarkovRegimeStrategy.weight().
            weights = [max(1.0, 1.0 + (c[1] - 0.5) * 10.0) for c in new_picks]
            total_weight = sum(weights) or float(len(new_picks))
            target_total = min(
                (total_equity / MAX_POSITIONS) * len(new_picks),
                cash * 0.99,
            )

            for (ticker, bull_5d, bear_5d, r, price), w in zip(new_picks, weights):
                buy_price = price * (1 + SLIPPAGE)
                per_position = target_total * (w / total_weight)
                shares = per_position / buy_price
                if shares <= 0:
                    continue
                cost = shares * buy_price
                if cost > cash:
                    shares = (cash * 0.999) / buy_price
                    cost = shares * buy_price
                    if shares <= 0:
                        continue
                cash -= cost
                positions[ticker] = {
                    'shares': shares,
                    'avg_cost': buy_price,
                    'entry_date': rebal_date.strftime('%Y-%m-%d'),
                    'entry_bull_5d': bull_5d,
                }
                trades.append({
                    'date': rebal_date.strftime('%Y-%m-%d'),
                    'ticker': ticker,
                    'action': 'BUY',
                    'shares': round(shares, 4),
                    'price': round(buy_price, 2),
                    'value': round(cost, 2),
                    'score': round(bull_5d * 100, 1),
                    'weight': round(w, 2),
                })

        # Snapshot equity at this rebalance.
        positions_value = 0.0
        for ticker, pos in positions.items():
            data = ticker_data.get(ticker)
            if data is not None:
                idx = data['dates'].searchsorted(rebal_date, side='right') - 1
                mark = float(data['close'][idx]) if idx >= 0 else pos['avg_cost']
            else:
                mark = pos['avg_cost']
            positions_value += pos['shares'] * mark
        total_value = cash + positions_value

        # SPY benchmark — normalise to STARTING_CAPITAL at the first rebalance
        # so both lines share the same y-axis starting point.
        spy_value = None
        if spy_dates is not None and len(spy_dates) > 0:
            sidx = spy_dates.searchsorted(rebal_date, side='right') - 1
            if sidx >= 0:
                spy_close = float(spy_closes[sidx])
                if spy_baseline_price is None:
                    spy_baseline_price = spy_close
                if spy_baseline_price > 0:
                    spy_value = round(STARTING_CAPITAL * (spy_close / spy_baseline_price), 2)

        equity_curve.append({
            'date': rebal_date.strftime('%Y-%m-%d'),
            'value': round(total_value, 2),
            'cash': round(cash, 2),
            'positionsValue': round(positions_value, 2),
            'spyValue': spy_value,
        })

    set_progress(job_id, 97, 'Computing summary statistics...')

    # ── Final mark-to-market for any open positions (unrealized) ──────────
    open_positions = []
    final_value = cash
    for ticker, pos in positions.items():
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
            'entryDate': pos['entry_date'],
        })

    # ── Summary statistics ────────────────────────────────────────────────
    closed = [t for t in trades if t['action'] == 'SELL']
    wins = [t for t in closed if t['pnl'] > 0]
    losses = [t for t in closed if t['pnl'] <= 0]
    num_trades = len(closed)
    win_rate = (len(wins) / num_trades * 100) if num_trades > 0 else 0
    avg_win_pct = sum(t['pnlPct'] for t in wins) / len(wins) if wins else 0
    avg_loss_pct = sum(t['pnlPct'] for t in losses) / len(losses) if losses else 0
    avg_win_dollar = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
    avg_loss_dollar = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
    # Win/loss ratio = abs(avg_win / avg_loss) — measures size of average win
    # vs average loss. >1 means winners are bigger than losers on average.
    win_loss_ratio = abs(avg_win_pct / avg_loss_pct) if avg_loss_pct != 0 else None
    profit_factor = (sum(t['pnl'] for t in wins) / abs(sum(t['pnl'] for t in losses))
                     if losses and sum(t['pnl'] for t in losses) != 0 else None)

    total_return = ((final_value / STARTING_CAPITAL) - 1) * 100

    # Max drawdown — peak-to-trough on equity curve.
    peak = STARTING_CAPITAL
    max_dd = 0.0
    for pt in equity_curve:
        peak = max(peak, pt['value'])
        if peak > 0:
            dd = (pt['value'] - peak) / peak * 100
            max_dd = min(max_dd, dd)

    best_trade = max((t['pnlPct'] for t in closed), default=0)
    worst_trade = min((t['pnlPct'] for t in closed), default=0)

    # SPY benchmark return over the same rebalance window — read the last
    # non-None spyValue off the equity curve.
    spy_return = None
    vs_spy = None
    last_spy = next((pt['spyValue'] for pt in reversed(equity_curve) if pt.get('spyValue') is not None), None)
    if last_spy is not None and STARTING_CAPITAL > 0:
        spy_return = (last_spy / STARTING_CAPITAL - 1) * 100
        vs_spy = total_return - spy_return

    elapsed = time.time() - t_start
    logger.info('Backtest %s done in %.1fs: return=%.1f%%, trades=%d, win_rate=%.1f%%',
                job_id, elapsed, total_return, num_trades, win_rate)

    set_done(job_id, {
        'summary': {
            'startingCapital': STARTING_CAPITAL,
            'finalValue': round(final_value, 2),
            'totalReturn': round(total_return, 2),
            'totalReturnDollar': round(final_value - STARTING_CAPITAL, 2),
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
        'params': {
            'years': years,
            'cadence': cadence,
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d'),
            'startingCapital': STARTING_CAPITAL,
            'maxPositions': MAX_POSITIONS,
            'universeSize': len(universe),
        },
        'elapsedSeconds': round(elapsed, 1),
    })
