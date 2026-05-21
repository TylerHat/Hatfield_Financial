"""Restore EtfEquitySnapshot.positions_value / total_value by re-marking
historical positions at the actual yfinance close on each snapshot's date.

Context: the earlier allocation-repair script (scripts/repair_etf_allocations.py)
overwrote snap.positions_value using positions' avg_cost as the mark, which
collapsed historical equity curves to ~$100k flatlines on dates that had
rebalance trades. This script restores the real market-value history by:

1. Replaying the trade log to know which positions (ticker → corrected shares)
   are held at each snapshot moment.
2. Bulk-fetching daily closes for every relevant ticker from yfinance.
3. Recomputing positions_value as sum(shares × close_on_snapshot_date) per
   snapshot, with weekend/holiday fallback to the most recent prior close.
4. Setting total_value = cash + positions_value. Leaves cash untouched.

Usage (from Backend/, or inside the ECS container):
    python -m scripts.restore_snapshot_marks                 # dry-run, all strategies
    python -m scripts.restore_snapshot_marks --apply
    python -m scripts.restore_snapshot_marks --strategy <id>
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from app import app
from models import db, EtfPortfolio, EtfEquitySnapshot, EtfTrade
from services.custom_etf.strategies import STRATEGIES, get_strategy
from data_fetcher import get_many_ohlcv, PRIORITY_MEDIUM

logger = logging.getLogger('restore_snapshot_marks')


def _replay_holdings(portfolio: EtfPortfolio) -> dict[int, dict[str, float]]:
    """Walk the trade log chronologically; return {snapshot_id → {ticker: shares}}
    capturing what the portfolio held at the moment of each snapshot."""
    trades = (EtfTrade.query.filter_by(portfolio_id=portfolio.id)
              .order_by(EtfTrade.executed_at, EtfTrade.id).all())
    snapshots = (EtfEquitySnapshot.query.filter_by(portfolio_id=portfolio.id)
                 .order_by(EtfEquitySnapshot.recorded_at).all())

    held: dict[str, float] = {}
    snap_iter = iter(snapshots)
    next_snap = next(snap_iter, None)
    result: dict[int, dict[str, float]] = {}

    for t in trades:
        while next_snap is not None and next_snap.recorded_at < t.executed_at:
            result[next_snap.id] = dict(held)
            next_snap = next(snap_iter, None)
        if t.action == 'BUY':
            held[t.ticker] = t.shares
        elif t.action == 'SELL':
            held.pop(t.ticker, None)

    while next_snap is not None:
        result[next_snap.id] = dict(held)
        next_snap = next(snap_iter, None)
    return result


def _close_for(target: date, closes: dict[date, float]) -> float | None:
    for delta in range(0, 8):
        d = target - timedelta(days=delta)
        if d in closes:
            return closes[d]
    return None


def restore_portfolio(strategy, ticker_closes: dict[str, dict[date, float]],
                      apply_changes: bool) -> dict:
    cfg = strategy.config
    portfolio = EtfPortfolio.query.filter_by(strategy_id=cfg.id).first()
    if portfolio is None:
        return {'strategy': cfg.id, 'skipped': 'no portfolio'}

    holdings_at = _replay_holdings(portfolio)
    snaps = (EtfEquitySnapshot.query.filter_by(portfolio_id=portfolio.id)
             .order_by(EtfEquitySnapshot.recorded_at).all())

    updated = 0
    skipped = 0
    total_before = 0.0
    total_after = 0.0
    for snap in snaps:
        held = holdings_at.get(snap.id, {})
        positions_value = 0.0
        missing = False
        for ticker, shares in held.items():
            closes = ticker_closes.get(ticker)
            if not closes:
                missing = True
                break
            price = _close_for(snap.recorded_at.date(), closes)
            if price is None:
                missing = True
                break
            positions_value += shares * price
        if missing:
            skipped += 1
            continue
        new_total = round(snap.cash + positions_value, 2)
        total_before += snap.total_value
        total_after += new_total
        if snap.positions_value != round(positions_value, 2) or snap.total_value != new_total:
            snap.positions_value = round(positions_value, 2)
            snap.total_value = new_total
            updated += 1

    if apply_changes:
        db.session.commit()
    else:
        db.session.rollback()

    return {
        'strategy': cfg.id,
        'snapshots': len(snaps),
        'updated': updated,
        'snaps_skipped': skipped,
        'total_before_sum': round(total_before, 2),
        'total_after_sum': round(total_after, 2),
    }


def main():
    parser = argparse.ArgumentParser(description='Re-mark historical snapshot equity values.')
    parser.add_argument('--apply', action='store_true', help='Commit changes (default dry-run).')
    parser.add_argument('--strategy', default=None, help='Limit to one strategy id.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if args.strategy:
        strat = get_strategy(args.strategy)
        if strat is None:
            logger.error('Unknown strategy id: %s', args.strategy)
            return
        targets = [strat]
    else:
        targets = list(STRATEGIES.values())

    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'\n=== Restore historical snapshot marks ({mode}) ===\n')

    with app.app_context():
        all_tickers: set[str] = set()
        for strat in targets:
            portfolio = EtfPortfolio.query.filter_by(strategy_id=strat.config.id).first()
            if portfolio is None:
                continue
            for t in EtfTrade.query.filter_by(portfolio_id=portfolio.id).all():
                all_tickers.add(t.ticker)

        if not all_tickers:
            print('No tickers found — nothing to do.')
            return

        print(f'Fetching daily closes for {len(all_tickers)} unique tickers via get_many_ohlcv...')
        bulk = get_many_ohlcv(sorted(all_tickers), period='1y', priority=PRIORITY_MEDIUM)
        ticker_closes: dict[str, dict[date, float]] = {}
        for ticker, df in (bulk or {}).items():
            if df is None or df.empty or 'Close' not in df.columns:
                continue
            closes: dict[date, float] = {}
            for ts, val in df['Close'].items():
                if val is None or (val != val):  # NaN check
                    continue
                d = ts.date() if hasattr(ts, 'date') else ts
                closes[d] = float(val)
            if closes:
                ticker_closes[ticker] = closes

        missing_tickers = sorted(all_tickers - set(ticker_closes.keys()))
        if missing_tickers:
            print(f'WARNING: no price data for {len(missing_tickers)} tickers: {missing_tickers}')
        print(f'Loaded prices for {len(ticker_closes)} tickers.\n')

        rows = []
        for strat in targets:
            try:
                rows.append(restore_portfolio(strat, ticker_closes, args.apply))
            except Exception:
                db.session.rollback()
                logger.exception('Restore failed for %s', strat.config.id)
                rows.append({'strategy': strat.config.id, 'error': 'see log'})

    header = f"{'strategy':<28} {'snaps':>6} {'updated':>8} {'skipped':>8}   {'sum total before':>18} {'sum total after':>18}"
    print(header)
    print('-' * len(header))
    for r in rows:
        if 'error' in r or 'skipped' in r:
            print(f"{r['strategy']:<28} {r.get('error') or r.get('skipped')}")
            continue
        print(f"{r['strategy']:<28} {r['snapshots']:>6} {r['updated']:>8} {r['snaps_skipped']:>8}   "
              f"${r['total_before_sum']:>16,.2f} ${r['total_after_sum']:>16,.2f}")
    print()
    if not args.apply:
        print('(dry-run — pass --apply to commit)\n')


if __name__ == '__main__':
    main()
