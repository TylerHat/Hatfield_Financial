"""One-shot retroactive repair for the Custom ETF over-allocation bug.

Replays every portfolio's trade log under the corrected sizing rule
(per_slot = total_equity / max_positions, bounded by available cash)
and updates shares / cash / equity snapshots in place. Tickers, prices,
trade timestamps, and scores are preserved.

Usage (from Backend/, with venv active):
    python -m scripts.repair_etf_allocations            # dry run, all strategies
    python -m scripts.repair_etf_allocations --apply    # commit changes
    python -m scripts.repair_etf_allocations --strategy <id>
"""

from __future__ import annotations

import argparse
import logging
from itertools import groupby

from app import app
from models import db, EtfPortfolio, EtfPosition, EtfTrade, EtfEquitySnapshot
from services.custom_etf.strategies import STRATEGIES, get_strategy

logger = logging.getLogger('repair_etf_allocations')


def repair_portfolio(strategy, apply_changes: bool) -> dict:
    cfg = strategy.config
    portfolio = EtfPortfolio.query.filter_by(strategy_id=cfg.id).first()
    if portfolio is None:
        return {'strategy': cfg.id, 'skipped': 'no portfolio'}

    cash_before = portfolio.cash
    total_before = cash_before + sum(p.shares * p.avg_cost for p in portfolio.positions)

    state_cash = portfolio.starting_capital
    state_positions: dict[str, dict] = {}
    trades_updated = 0
    snapshots_updated = 0

    trades = (EtfTrade.query
              .filter_by(portfolio_id=portfolio.id)
              .order_by(EtfTrade.executed_at, EtfTrade.id).all())
    snapshots_by_time = {s.recorded_at: s for s in portfolio.snapshots}

    for executed_at, group_iter in groupby(trades, key=lambda t: t.executed_at):
        group = list(group_iter)
        sells = [t for t in group if t.action == 'SELL']
        buys = [t for t in group if t.action == 'BUY']

        for t in sells:
            pos = state_positions.pop(t.ticker, None)
            if pos is None:
                logger.warning('%s @ %s: SELL with no matching position for %s — skipping',
                               cfg.id, executed_at, t.ticker)
                continue
            corrected_shares = pos['shares']
            state_cash += corrected_shares * t.price
            t.shares = corrected_shares
            t.cash_after = state_cash
            trades_updated += 1

        if buys:
            held_value = sum(p['shares'] * p['avg_cost'] for p in state_positions.values())
            total_equity = state_cash + held_value
            valid_buys = [t for t in buys if t.price and t.price > 0]
            if valid_buys and state_cash > 0:
                target_per_slot = total_equity / cfg.max_positions
                cash_cap = (state_cash * 0.99) / len(valid_buys)
                per_slot = min(target_per_slot, cash_cap)
                for t in valid_buys:
                    new_shares = per_slot / t.price
                    if new_shares <= 0:
                        continue
                    state_cash -= new_shares * t.price
                    t.shares = new_shares
                    t.cash_after = state_cash
                    trades_updated += 1
                    state_positions[t.ticker] = {
                        'shares': new_shares,
                        'avg_cost': t.price,
                        'entry_score': t.score,
                        'entry_at': executed_at,
                    }

        snap = snapshots_by_time.get(executed_at)
        if snap is not None:
            positions_value = sum(p['shares'] * p['avg_cost']
                                  for p in state_positions.values())
            snap.cash = round(state_cash, 2)
            snap.positions_value = round(positions_value, 2)
            snap.total_value = round(state_cash + positions_value, 2)
            snapshots_updated += 1

    EtfPosition.query.filter_by(portfolio_id=portfolio.id).delete()
    for ticker, p in state_positions.items():
        db.session.add(EtfPosition(
            portfolio_id=portfolio.id,
            ticker=ticker,
            shares=p['shares'],
            avg_cost=p['avg_cost'],
            entry_score=p['entry_score'],
            entry_at=p['entry_at'],
        ))
    portfolio.cash = state_cash

    db.session.flush()
    cash_after = state_cash
    total_after = state_cash + sum(p['shares'] * p['avg_cost']
                                   for p in state_positions.values())

    if apply_changes:
        db.session.commit()
    else:
        db.session.rollback()

    return {
        'strategy': cfg.id,
        'trades_updated': trades_updated,
        'snapshots_updated': snapshots_updated,
        'positions': len(state_positions),
        'cash_before': round(cash_before, 2),
        'cash_after': round(cash_after, 2),
        'total_before': round(total_before, 2),
        'total_after': round(total_after, 2),
    }


def main():
    parser = argparse.ArgumentParser(description='Repair Custom ETF over-allocation.')
    parser.add_argument('--apply', action='store_true',
                        help='Commit changes (default is dry-run).')
    parser.add_argument('--strategy', type=str, default=None,
                        help='Repair only this strategy id.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')

    if args.strategy:
        strat = get_strategy(args.strategy)
        if strat is None:
            logger.error('Unknown strategy id: %s', args.strategy)
            return
        targets = [strat]
    else:
        targets = list(STRATEGIES.values())

    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'\n=== Custom ETF allocation repair ({mode}) ===\n')

    rows = []
    with app.app_context():
        for strat in targets:
            try:
                rows.append(repair_portfolio(strat, args.apply))
            except Exception:
                db.session.rollback()
                logger.exception('Repair failed for %s', strat.config.id)
                rows.append({'strategy': strat.config.id, 'error': 'see log'})

    header = f"{'strategy':<28} {'trades':>7} {'snaps':>6} {'pos':>4}   {'cash before':>14} {'cash after':>14}   {'total before':>14} {'total after':>14}"
    print(header)
    print('-' * len(header))
    for r in rows:
        if 'error' in r or 'skipped' in r:
            print(f"{r['strategy']:<28} {r.get('error') or r.get('skipped')}")
            continue
        print(f"{r['strategy']:<28} {r['trades_updated']:>7} {r['snapshots_updated']:>6} "
              f"{r['positions']:>4}   ${r['cash_before']:>13,.2f} ${r['cash_after']:>13,.2f}   "
              f"${r['total_before']:>13,.2f} ${r['total_after']:>13,.2f}")
    print()
    if not args.apply:
        print('(dry-run — pass --apply to commit)\n')


if __name__ == '__main__':
    main()
