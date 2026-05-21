"""Backfill EtfEquitySnapshot.spy_price for snapshots where the SPY fetch
failed at rebalance time. Pulls SPY's actual historical close for each
snapshot's date so the benchmark chart is continuous end-to-end.

Usage (from Backend/, with venv active, or inside the ECS container):
    python -m scripts.backfill_spy_prices              # dry-run
    python -m scripts.backfill_spy_prices --apply      # commit
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from app import app
from models import db, EtfEquitySnapshot
from data_fetcher import get_spy_history, PRIORITY_MEDIUM

logger = logging.getLogger('backfill_spy_prices')


def _build_spy_close_lookup(min_date: date, max_date: date) -> dict[date, float]:
    """Pull SPY's daily close for the inclusive window and return a date→close map."""
    start = (min_date - timedelta(days=7)).isoformat()
    end = (max_date + timedelta(days=2)).isoformat()
    hist = get_spy_history(start, end, priority=PRIORITY_MEDIUM)
    if hist is None or hist.empty:
        raise RuntimeError(f'SPY history fetch returned empty for {start}..{end}')
    closes: dict[date, float] = {}
    for ts, row in hist['Close'].items():
        d = ts.date() if hasattr(ts, 'date') else ts
        closes[d] = float(row)
    return closes


def _close_for(target: date, closes: dict[date, float]) -> float | None:
    """Return SPY close for `target`, falling back up to 7 days earlier
    (covers weekends / market holidays). None if nothing nearby."""
    for delta in range(0, 8):
        d = target - timedelta(days=delta)
        if d in closes:
            return closes[d]
    return None


def main():
    parser = argparse.ArgumentParser(description='Backfill NULL spy_price values on EtfEquitySnapshot rows.')
    parser.add_argument('--apply', action='store_true', help='Commit changes (default is dry-run).')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'\n=== SPY price backfill ({mode}) ===\n')

    with app.app_context():
        rows = (EtfEquitySnapshot.query
                .filter(EtfEquitySnapshot.spy_price.is_(None))
                .order_by(EtfEquitySnapshot.recorded_at).all())

        if not rows:
            print('No snapshots with NULL spy_price — nothing to do.\n')
            return

        min_dt = rows[0].recorded_at
        max_dt = rows[-1].recorded_at
        min_d = min_dt.date()
        max_d = max_dt.date()
        print(f'Found {len(rows)} NULL snapshots across {min_d} .. {max_d}.')
        print('Fetching SPY history...')

        try:
            closes = _build_spy_close_lookup(min_d, max_d)
        except Exception:
            logger.exception('Could not fetch SPY history')
            return

        print(f'Loaded SPY closes for {len(closes)} trading days.\n')

        filled = 0
        skipped = 0
        samples = []
        for snap in rows:
            d = snap.recorded_at.date()
            price = _close_for(d, closes)
            if price is None:
                skipped += 1
                continue
            snap.spy_price = price
            filled += 1
            if len(samples) < 10:
                samples.append((snap.id, d.isoformat(), round(price, 2)))

        print(f'{"snapshot_id":>12}  {"date":>12}  {"spy_close":>12}')
        print('-' * 42)
        for sid, ds, p in samples:
            print(f'{sid:>12}  {ds:>12}  ${p:>10.2f}')
        if filled > len(samples):
            print(f'... and {filled - len(samples)} more')
        print()

        print(f'Filled:  {filled}')
        print(f'Skipped: {skipped}')
        print(f'Total:   {len(rows)}')
        print()

        if args.apply:
            db.session.commit()
            print('Committed.\n')
        else:
            db.session.rollback()
            print('(dry-run — pass --apply to commit)\n')


if __name__ == '__main__':
    main()
