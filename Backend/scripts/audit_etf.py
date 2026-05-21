"""Read-only audit of a Custom ETF portfolio. Dumps the latest snapshots
and trades so we can cross-check stored equity values against what the
trade flow + current marks would produce.

Usage:
    python -m scripts.audit_etf                       # default strategy: buy-score-top10
    python -m scripts.audit_etf --strategy <id>
    python -m scripts.audit_etf --snaps 30 --trades 50
"""

from __future__ import annotations

import argparse

from app import app
from models import EtfPortfolio, EtfEquitySnapshot, EtfTrade


def main():
    parser = argparse.ArgumentParser(description='Audit a Custom ETF portfolio (read-only).')
    parser.add_argument('--strategy', default='buy-score-top10')
    parser.add_argument('--snaps', type=int, default=14)
    parser.add_argument('--trades', type=int, default=20)
    args = parser.parse_args()

    with app.app_context():
        p = EtfPortfolio.query.filter_by(strategy_id=args.strategy).first()
        if not p:
            print(f'No portfolio for strategy {args.strategy}')
            return

        cost_basis = sum(pos.shares * pos.avg_cost for pos in p.positions)
        print(f'=== {args.strategy} ===')
        print(f'cash=${p.cash:,.2f}  starting=${p.starting_capital:,.2f}  positions={len(p.positions)}')
        print(f'positions cost basis sum: ${cost_basis:,.2f}')
        print(f'cash + cost basis:        ${p.cash + cost_basis:,.2f}')
        print()

        print('Positions:')
        print(f'  {"ticker":<8} {"shares":>12} {"avg_cost":>10} {"cost_basis":>14}')
        for pos in sorted(p.positions, key=lambda x: x.ticker):
            print(f'  {pos.ticker:<8} {pos.shares:>12.4f} ${pos.avg_cost:>8.2f} ${pos.shares*pos.avg_cost:>12,.2f}')
        print()

        snaps = (EtfEquitySnapshot.query.filter_by(portfolio_id=p.id)
                 .order_by(EtfEquitySnapshot.recorded_at.desc()).limit(args.snaps).all())
        print(f'Last {len(snaps)} snapshots (oldest first):')
        print(f'  {"recorded_at":<22} {"total_value":>14} {"cash":>11} {"positions_value":>16} {"spy_price":>10}')
        for s in reversed(snaps):
            spy = f'${s.spy_price:.2f}' if s.spy_price else 'NULL'
            print(f'  {s.recorded_at.isoformat()[:19]:<22} ${s.total_value:>12,.2f} ${s.cash:>9,.2f} ${s.positions_value:>14,.2f} {spy:>10}')
        print()

        trades = (EtfTrade.query.filter_by(portfolio_id=p.id)
                  .order_by(EtfTrade.executed_at.desc()).limit(args.trades).all())
        print(f'Last {len(trades)} trades (oldest first):')
        print(f'  {"executed_at":<22} {"act":<5} {"ticker":<7} {"shares":>11} {"price":>10} {"cash_after":>13} {"reason":<14}')
        for t in reversed(trades):
            print(f'  {t.executed_at.isoformat()[:19]:<22} {t.action:<5} {t.ticker:<7} {t.shares:>11.4f} ${t.price:>8.2f} ${t.cash_after:>11,.2f} {t.reason or "":<14}')


if __name__ == '__main__':
    main()
