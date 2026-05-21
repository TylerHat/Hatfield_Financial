"""Comprehensive repair of EtfEquitySnapshot rows.

Replays each portfolio's trade log chronologically to recompute cash AND
positions_value at every snapshot moment, marking held positions at the
actual yfinance close on each snapshot's date. Falls back to position
avg_cost for tickers with no yfinance data.

Supersedes the snapshot mutations from:
  - scripts/repair_etf_allocations.py  (left non-trade-bearing snaps with stale cash)
  - scripts/restore_snapshot_marks.py  (computed positions_value but kept stale cash)

Doesn't touch EtfTrade, EtfPosition, or EtfPortfolio.cash — those are correct.

Usage (from Backend/, or inside the ECS container):
    python -m scripts.fix_etf_snapshots               # dry-run, all strategies
    python -m scripts.fix_etf_snapshots --apply
    python -m scripts.fix_etf_snapshots --strategy <id>
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from app import app
from models import db, EtfPortfolio, EtfEquitySnapshot, EtfTrade
from services.custom_etf.strategies import STRATEGIES, get_strategy
from data_fetcher import get_many_ohlcv, PRIORITY_MEDIUM

logger = logging.getLogger('fix_etf_snapshots')


def _close_for(target: date, closes: dict[date, float]) -> float | None:
    for delta in range(0, 8):
        d = target - timedelta(days=delta)
        if d in closes:
            return closes[d]
    return None


def _bulk_fetch_closes(tickers: list[str]) -> dict[str, dict[date, float]]:
    if not tickers:
        return {}
    print(f'Fetching daily closes for {len(tickers)} unique tickers via get_many_ohlcv...')
    bulk = get_many_ohlcv(sorted(tickers), period='1y', priority=PRIORITY_MEDIUM)
    out: dict[str, dict[date, float]] = {}
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
            out[ticker] = closes
    missing = sorted(set(tickers) - set(out.keys()))
    if missing:
        print(f'WARNING: no yfinance data for {len(missing)} tickers: {missing}')
    print(f'Loaded prices for {len(out)} tickers.\n')
    return out


def fix_portfolio(strategy, ticker_closes: dict[str, dict[date, float]],
                  apply_changes: bool) -> dict:
    cfg = strategy.config
    portfolio = EtfPortfolio.query.filter_by(strategy_id=cfg.id).first()
    if portfolio is None:
        return {'strategy': cfg.id, 'skipped': 'no portfolio'}

    trades = (EtfTrade.query.filter_by(portfolio_id=portfolio.id)
              .order_by(EtfTrade.executed_at, EtfTrade.id).all())
    snaps = (EtfEquitySnapshot.query.filter_by(portfolio_id=portfolio.id)
             .order_by(EtfEquitySnapshot.recorded_at).all())

    if not snaps:
        return {'strategy': cfg.id, 'skipped': 'no snapshots'}

    state_cash = portfolio.starting_capital
    state_positions: dict[str, dict] = {}
    trade_idx = 0
    updated = 0
    fallback_uses = 0
    min_total = float('inf')
    max_total = float('-inf')

    for snap in snaps:
        while trade_idx < len(trades) and trades[trade_idx].executed_at <= snap.recorded_at:
            t = trades[trade_idx]
            if t.action == 'SELL':
                state_positions.pop(t.ticker, None)
                state_cash += t.shares * t.price
            elif t.action == 'BUY':
                state_cash -= t.shares * t.price
                state_positions[t.ticker] = {'shares': t.shares, 'avg_cost': t.price}
            trade_idx += 1

        positions_value = 0.0
        for ticker, pos in state_positions.items():
            closes = ticker_closes.get(ticker)
            mark = _close_for(snap.recorded_at.date(), closes) if closes else None
            if mark is None:
                mark = pos['avg_cost']
                fallback_uses += 1
            positions_value += pos['shares'] * mark

        new_cash = round(state_cash, 2)
        new_pv = round(positions_value, 2)
        new_total = round(new_cash + new_pv, 2)
        min_total = min(min_total, new_total)
        max_total = max(max_total, new_total)

        if (snap.cash != new_cash or snap.positions_value != new_pv
                or snap.total_value != new_total):
            snap.cash = new_cash
            snap.positions_value = new_pv
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
        'fallback_uses': fallback_uses,
        'min_total': round(min_total, 2),
        'max_total': round(max_total, 2),
    }


def main():
    parser = argparse.ArgumentParser(description='Rebuild EtfEquitySnapshot rows from trade log + yfinance closes.')
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
    print(f'\n=== Fix EtfEquitySnapshot rows ({mode}) ===\n')

    with app.app_context():
        all_tickers: set[str] = set()
        for strat in targets:
            portfolio = EtfPortfolio.query.filter_by(strategy_id=strat.config.id).first()
            if portfolio is None:
                continue
            for t in EtfTrade.query.filter_by(portfolio_id=portfolio.id).all():
                all_tickers.add(t.ticker)

        ticker_closes = _bulk_fetch_closes(sorted(all_tickers))

        rows = []
        for strat in targets:
            try:
                rows.append(fix_portfolio(strat, ticker_closes, args.apply))
            except Exception:
                db.session.rollback()
                logger.exception('Fix failed for %s', strat.config.id)
                rows.append({'strategy': strat.config.id, 'error': 'see log'})

    header = (f"{'strategy':<28} {'snaps':>6} {'updated':>8} {'fallbacks':>10}   "
              f"{'min total':>14} {'max total':>14}")
    print(header)
    print('-' * len(header))
    for r in rows:
        if 'error' in r or 'skipped' in r:
            print(f"{r['strategy']:<28} {r.get('error') or r.get('skipped')}")
            continue
        print(f"{r['strategy']:<28} {r['snapshots']:>6} {r['updated']:>8} "
              f"{r['fallback_uses']:>10}   ${r['min_total']:>12,.2f} ${r['max_total']:>12,.2f}")
    print()
    if not args.apply:
        print('(dry-run — pass --apply to commit)\n')


if __name__ == '__main__':
    main()
