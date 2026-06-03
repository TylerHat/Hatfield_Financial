"""Backfill EtfTrade.price for buggy EXIT_UNIVERSE sells.

Before commit 048eb654 the simulator marked EXIT_UNIVERSE sells at the
position's avg_cost when no fresh quote was available, which made the
trade history show a fake $0 P&L on those rows. This script walks every
portfolio's trade log, re-derives the avg_cost at the moment of each
EXIT_UNIVERSE sell, and — for the rows where the stored price still
matches avg_cost (the bug signature) — overwrites `price` with the
actual market close on `executed_at`, with the strategy's slippage
applied (mirroring what the fixed simulator does now).

We deliberately do NOT touch:
  * cash_after on historical rows (would not match portfolio.cash anyway)
  * portfolio.cash (changing it would retroactively alter past BUY sizing)
  * EtfEquitySnapshot rows

So the displayed trade-history P&L and the derived realized/win-rate
stats become accurate; the cash columns remain a record of the
simulator-as-it-ran. This is a one-way trade-off — accept it.

Usage (from Backend/, with venv active, or inside the ECS container):
    python -m scripts.backfill_exit_universe_prices              # dry-run
    python -m scripts.backfill_exit_universe_prices --apply      # commit
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone

from app import app
from models import db, EtfPortfolio, EtfTrade
from data_fetcher import get_ohlcv, PRIORITY_LOW
from services.custom_etf.strategies import get_strategy

logger = logging.getLogger('backfill_exit_universe_prices')

# A trade is treated as buggy when stored price is within this absolute
# tolerance of the recomputed avg_cost. avg_cost is stored as a rounded
# float so an exact == compare misses some rows.
PRICE_MATCH_EPS = 0.0001


def _avg_cost_at_each_sell(portfolio_id: int) -> dict[int, float]:
    """Walk this portfolio's trades oldest→newest, maintaining running
    weighted-average cost basis per ticker. Returns {trade_id: avg_cost}
    for every SELL row (so we can compare against the stored price).
    """
    trades = (EtfTrade.query
              .filter_by(portfolio_id=portfolio_id)
              .order_by(EtfTrade.executed_at.asc(), EtfTrade.id.asc()).all())
    cost_basis: dict[str, dict] = {}
    out: dict[int, float] = {}
    for t in trades:
        if t.action == 'BUY':
            cb = cost_basis.get(t.ticker, {'shares': 0.0, 'avg_cost': 0.0})
            new_shares = cb['shares'] + t.shares
            if new_shares > 0:
                cb['avg_cost'] = (cb['shares'] * cb['avg_cost'] + t.shares * t.price) / new_shares
            cb['shares'] = new_shares
            cost_basis[t.ticker] = cb
        elif t.action == 'SELL':
            cb = cost_basis.get(t.ticker)
            if cb:
                out[t.id] = cb['avg_cost']
                cb['shares'] = max(0.0, cb['shares'] - t.shares)
                if cb['shares'] <= 1e-9:
                    cost_basis.pop(t.ticker, None)
    return out


def _fetch_closes(ticker: str, dates: list[date]) -> dict[date, float]:
    """Pull OHLCV for [min..max] with a small buffer and return date→close."""
    start = datetime.combine(min(dates) - timedelta(days=10), dtime.min)
    end = datetime.combine(max(dates) + timedelta(days=2), dtime.min)
    hist = get_ohlcv(ticker, start, end, priority=PRIORITY_LOW)
    if hist is None or hist.empty or 'Close' not in hist.columns:
        return {}
    closes: dict[date, float] = {}
    for ts, row in hist['Close'].dropna().items():
        d = ts.date() if hasattr(ts, 'date') else ts
        closes[d] = float(row)
    return closes


def _close_on_or_before(target: date, closes: dict[date, float]) -> float | None:
    """Return close for `target`, falling back up to 10 days earlier."""
    for delta in range(0, 11):
        d = target - timedelta(days=delta)
        if d in closes:
            return closes[d]
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--apply', action='store_true', help='Commit changes (default is dry-run).')
    parser.add_argument('--limit-samples', type=int, default=15,
                        help='How many proposed updates to print as samples.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'\n=== EXIT_UNIVERSE price backfill ({mode}) ===\n')

    with app.app_context():
        portfolios = EtfPortfolio.query.all()
        if not portfolios:
            print('No portfolios — nothing to do.\n')
            return

        # ── Phase 1: collect buggy candidates across all portfolios ──────
        # candidate = (trade, slippage_fraction)
        candidates: list[tuple[EtfTrade, float]] = []
        skipped_not_buggy = 0

        for pf in portfolios:
            strat = get_strategy(pf.strategy_id)
            if strat is None:
                logger.warning('Portfolio %s: unknown strategy_id %r — assuming 5 bps slippage',
                               pf.id, pf.strategy_id)
                slippage = 5.0 / 10_000.0
            else:
                slippage = strat.config.slippage_bps / 10_000.0

            avg_cost_map = _avg_cost_at_each_sell(pf.id)

            exit_sells = (EtfTrade.query
                          .filter_by(portfolio_id=pf.id, action='SELL', reason='EXIT_UNIVERSE')
                          .order_by(EtfTrade.executed_at.asc()).all())
            for t in exit_sells:
                avg = avg_cost_map.get(t.id)
                if avg is None or avg <= 0:
                    skipped_not_buggy += 1
                    continue
                if abs(t.price - avg) > PRICE_MATCH_EPS:
                    # Already non-buggy (post-fix data, or partial fill at real price)
                    skipped_not_buggy += 1
                    continue
                candidates.append((t, slippage))

        if not candidates:
            print(f'Found 0 buggy EXIT_UNIVERSE sells (checked {skipped_not_buggy} non-matching rows).')
            print('Nothing to backfill.\n')
            return

        print(f'Found {len(candidates)} buggy EXIT_UNIVERSE sells '
              f'({skipped_not_buggy} other EXIT_UNIVERSE rows already look correct).\n')

        # ── Phase 2: per-ticker OHLCV fetch ──────────────────────────────
        by_ticker: dict[str, list[tuple[EtfTrade, float]]] = defaultdict(list)
        for t, sl in candidates:
            by_ticker[t.ticker].append((t, sl))

        print(f'Fetching OHLCV for {len(by_ticker)} unique tickers...')
        closes_by_ticker: dict[str, dict[date, float]] = {}
        fetch_failures: list[str] = []
        for ticker, rows in by_ticker.items():
            dates = [t.executed_at.date() for t, _ in rows]
            closes = _fetch_closes(ticker, dates)
            if not closes:
                fetch_failures.append(ticker)
                continue
            closes_by_ticker[ticker] = closes
        print(f'Loaded closes for {len(closes_by_ticker)} tickers '
              f'({len(fetch_failures)} failed: {", ".join(fetch_failures[:10])}'
              f'{"..." if len(fetch_failures) > 10 else ""}).\n')

        # ── Phase 3: stage updates ───────────────────────────────────────
        updated = 0
        no_close = 0
        samples: list[tuple] = []
        for t, slippage in candidates:
            closes = closes_by_ticker.get(t.ticker)
            if not closes:
                no_close += 1
                continue
            raw_close = _close_on_or_before(t.executed_at.date(), closes)
            if raw_close is None:
                no_close += 1
                continue
            new_price = round(raw_close * (1 - slippage), 4)
            old_price = t.price
            pnl_delta = (new_price - old_price) * t.shares
            t.price = new_price
            updated += 1
            if len(samples) < args.limit_samples:
                samples.append((t.id, t.ticker, t.executed_at.date().isoformat(),
                                round(old_price, 4), round(new_price, 4), round(pnl_delta, 2)))

        # ── Report ───────────────────────────────────────────────────────
        print(f'{"trade_id":>9}  {"ticker":>6}  {"date":>12}  '
              f'{"old_price":>10}  {"new_price":>10}  {"pnl_delta":>10}')
        print('-' * 72)
        for tid, tk, ds, op, np_, pd_ in samples:
            print(f'{tid:>9}  {tk:>6}  {ds:>12}  ${op:>9.4f}  ${np_:>9.4f}  ${pd_:>9.2f}')
        if updated > len(samples):
            print(f'... and {updated - len(samples)} more')
        print()

        print(f'Updated:                {updated}')
        print(f'No close data (skipped): {no_close}')
        print(f'Already correct:         {skipped_not_buggy}')
        print(f'Total EXIT_UNIVERSE rows: {updated + no_close + skipped_not_buggy}')
        print()

        if args.apply:
            db.session.commit()
            print('Committed.\n')
        else:
            db.session.rollback()
            print('(dry-run — pass --apply to commit)\n')


if __name__ == '__main__':
    main()
