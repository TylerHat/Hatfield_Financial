"""Backfill the markov-regime Custom ETF portfolio with daily simulated
history for 2026-05-12 .. 2026-05-21, so its equity curve starts on May 12
like the other five strategies.

Why: the Markov Regime strategy was committed on 2026-05-21 and only began
accumulating snapshots in the live DB on 2026-05-22 (when the daily Lambda
first saw it). The other five strategies have history back to 2026-05-12.
This script reconstructs the missing eight trading days using only data that
was available as of each rebalance date (no look-ahead) and inserts BUY/SELL
trades + equity snapshots into the live tables. Existing May 22+ rows are
NEVER touched.

The simulation logic is reused verbatim from `_walk_forward_markov` in
`services.custom_etf.markov_portfolio_backtest` — same scoring, eligibility,
conviction weighting, slippage, and SPY fetch as the live MarkovRegimeStrategy.

Usage (from Backend/, with venv active):
    python -m scripts.backfill_markov_history              # dry-run
    python -m scripts.backfill_markov_history --apply      # commit

Safety:
- Refuses to run if any EtfTrade or EtfEquitySnapshot for the markov-regime
  portfolio already has a timestamp before 2026-05-22 (idempotency).
- Does NOT modify EtfPortfolio.cash / starting_capital / last_rebalance_at
  or any EtfPosition row. May 22+ live state is preserved.
- Dry-run by default; --apply required to commit.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, time, timezone

import pandas as pd

from app import app
from models import db, EtfPortfolio, EtfTrade, EtfEquitySnapshot
from services.custom_etf.markov_portfolio_backtest import _walk_forward_markov

logger = logging.getLogger('backfill_markov_history')

STRATEGY_ID = 'markov-regime'
START_DATE = pd.Timestamp('2026-05-12')
END_DATE = pd.Timestamp('2026-05-21')
CADENCE = 'daily'
# `period` controls how far back yfinance fetches OHLC. Markov needs ~1.5
# years of warmup before the matrix can fire, so 2y comfortably covers the
# May 2026 window.
PERIOD = '2y'

# Hard cutoff that defines "before backfill" vs "live data we must not touch".
LIVE_CUTOFF = datetime(2026, 5, 22, tzinfo=timezone.utc)

# Time-of-day for backdated rows. 13:30 UTC = 9:30 AM ET (EDT), matching the
# nominal Lambda fire time for daily rebalances.
REBALANCE_TIME_UTC = time(13, 30, 0, tzinfo=timezone.utc)


def _date_to_utc_dt(date_str: str) -> datetime:
    """Parse 'YYYY-MM-DD' and attach the rebalance time-of-day in UTC."""
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    return datetime.combine(d, REBALANCE_TIME_UTC)


def main():
    parser = argparse.ArgumentParser(
        description='Backfill markov-regime ETF history for 2026-05-12 .. 2026-05-21.'
    )
    parser.add_argument('--apply', action='store_true',
                        help='Commit changes (default is dry-run).')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'\n=== Markov history backfill ({mode}) ===\n')
    print(f'Window: {START_DATE.date()} .. {END_DATE.date()}  cadence={CADENCE}\n')

    with app.app_context():
        pf = EtfPortfolio.query.filter_by(strategy_id=STRATEGY_ID).first()
        if pf is None:
            print(f'ERROR: no EtfPortfolio row for strategy_id={STRATEGY_ID!r}. Aborting.')
            return 1

        print(f'Portfolio id={pf.id}  cash=${pf.cash:,.2f}  starting_capital=${pf.starting_capital:,.2f}')
        print(f'  last_rebalance_at={pf.last_rebalance_at}')

        # Idempotency check — refuse to double-backfill.
        existing_pre = (EtfTrade.query
                        .filter(EtfTrade.portfolio_id == pf.id,
                                EtfTrade.executed_at < LIVE_CUTOFF.replace(tzinfo=None))
                        .count())
        existing_snaps_pre = (EtfEquitySnapshot.query
                              .filter(EtfEquitySnapshot.portfolio_id == pf.id,
                                      EtfEquitySnapshot.recorded_at < LIVE_CUTOFF.replace(tzinfo=None))
                              .count())
        if existing_pre or existing_snaps_pre:
            print(f'ERROR: portfolio already has {existing_pre} pre-{LIVE_CUTOFF.date()} '
                  f'trades and {existing_snaps_pre} pre-cutoff snapshots — refusing to '
                  f'double-backfill. Roll back the previous backfill first.')
            return 1

        # Count what we must preserve.
        live_trades = (EtfTrade.query
                       .filter(EtfTrade.portfolio_id == pf.id,
                               EtfTrade.executed_at >= LIVE_CUTOFF.replace(tzinfo=None))
                       .count())
        live_snaps = (EtfEquitySnapshot.query
                      .filter(EtfEquitySnapshot.portfolio_id == pf.id,
                              EtfEquitySnapshot.recorded_at >= LIVE_CUTOFF.replace(tzinfo=None))
                      .count())
        print(f'  live trades (>= {LIVE_CUTOFF.date()}): {live_trades}  (will be left untouched)')
        print(f'  live snapshots (>= {LIVE_CUTOFF.date()}): {live_snaps}  (will be left untouched)\n')

        # Run the walk-forward simulation in memory.
        print('Running walk-forward simulation (this fetches S&P 500 OHLC and may take a few minutes)...\n')
        result = _walk_forward_markov(
            start_date=START_DATE,
            end_date=END_DATE,
            cadence=CADENCE,
            period=PERIOD,
            progress_cb=lambda pct, msg: logger.info(f'  [{pct:5.1f}%] {msg}'),
        )

        trades = result['trades']
        equity_curve = result['equityCurve']
        summary = result['summary']

        print(f'\nSimulation complete in {result["elapsedSeconds"]}s.')
        print(f'  rebalances={summary["rebalances"]}  '
              f'trades={summary["numTrades"]} closed + {len(trades) - summary["numTrades"]} open-side  '
              f'finalValue=${summary["finalValue"]:,.2f}  '
              f'totalReturn={summary["totalReturn"]:+.2f}%')
        print(f'  open_positions at end: {summary["openPositions"]}')

        # ── Build EtfTrade rows ──────────────────────────────────────────
        trade_rows = []
        for t in trades:
            executed_at = _date_to_utc_dt(t['date'])
            if executed_at >= LIVE_CUTOFF:
                # Should never trigger because END_DATE < LIVE_CUTOFF, but
                # defend against off-by-one if the script is reused later.
                continue
            if t['action'] == 'BUY':
                row = EtfTrade(
                    portfolio_id=pf.id,
                    ticker=t['ticker'],
                    action='BUY',
                    shares=t['shares'],
                    price=t['price'],
                    score=t.get('score'),
                    reason='NEW_GREEN',
                    cash_after=t.get('cash_after', 0.0),
                    executed_at=executed_at,
                )
            else:  # SELL
                row = EtfTrade(
                    portfolio_id=pf.id,
                    ticker=t['ticker'],
                    action='SELL',
                    shares=t['shares'],
                    price=t['price'],
                    score=None,
                    reason='SCORE_DROP',
                    cash_after=t.get('cash_after', 0.0),
                    executed_at=executed_at,
                )
            trade_rows.append(row)

        # ── Build EtfEquitySnapshot rows ─────────────────────────────────
        snap_rows = []
        for pt in equity_curve:
            recorded_at = _date_to_utc_dt(pt['date'])
            if recorded_at >= LIVE_CUTOFF:
                continue
            snap_rows.append(EtfEquitySnapshot(
                portfolio_id=pf.id,
                total_value=pt['value'],
                cash=pt['cash'],
                positions_value=pt['positionsValue'],
                spy_price=pt.get('spy_close'),
                recorded_at=recorded_at,
            ))

        # ── Preview ──────────────────────────────────────────────────────
        print(f'\nPrepared {len(trade_rows)} EtfTrade rows + {len(snap_rows)} EtfEquitySnapshot rows.')

        # Per-day breakdown
        by_day = {}
        for r in trade_rows:
            d = r.executed_at.date()
            slot = by_day.setdefault(d, {'BUY': 0, 'SELL': 0})
            slot[r.action] += 1
        snap_by_day = {s.recorded_at.date(): s for s in snap_rows}

        print(f'\n{"date":>12}  {"buys":>6}  {"sells":>6}  {"NAV":>12}  {"cash":>12}  {"positions":>12}  {"spy":>8}')
        print('-' * 90)
        for d in sorted(by_day.keys() | snap_by_day.keys()):
            row = by_day.get(d, {'BUY': 0, 'SELL': 0})
            s = snap_by_day.get(d)
            nav = f'${s.total_value:>10,.2f}' if s else '   (no snap)'
            cash = f'${s.cash:>10,.2f}' if s else ''
            posv = f'${s.positions_value:>10,.2f}' if s else ''
            spy = f'${s.spy_price:>6.2f}' if s and s.spy_price is not None else ''
            print(f'{str(d):>12}  {row["BUY"]:>6}  {row["SELL"]:>6}  {nav}  {cash}  {posv}  {spy}')

        # Persist
        if args.apply:
            for r in trade_rows:
                db.session.add(r)
            for s in snap_rows:
                db.session.add(s)
            db.session.commit()
            print(f'\nCommitted: {len(trade_rows)} trades + {len(snap_rows)} snapshots inserted.\n')
        else:
            print('\n(dry-run — pass --apply to commit. No DB writes happened.)\n')

        return 0


if __name__ == '__main__':
    raise SystemExit(main())
