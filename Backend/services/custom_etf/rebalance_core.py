"""Pure rebalance decision core — shared by the live simulator and the
walk-forward backtest engine.

Extracted from simulator.rebalance() in HFA-069. The review found the old
Markov backtest re-implementing the rebalance rules with different
semantics (rank field, forced top-N churn) than the live simulator, so its
results didn't describe the deployed strategy. With the decision math in
one place, a backtest IS the live strategy replayed over history:

    simulator.rebalance()      — DB wrapper: ORM positions in, trades/
                                 snapshots persisted out.
    walk_forward engine        — replays this pass at each historical
                                 rebalance date with synthesized rows.

Everything here is pure: no Flask, no ORM, no yfinance. The one external
touchpoint — pricing a held ticker that vanished from the universe — is
injected via `resolve_missing_price` so the live path can quote yfinance
while the backtest path reads its price arrays.

Semantics (unchanged from the pre-extraction simulator):
  1. SELL any held name scoring <= sell_threshold (SCORE_DROP) or absent
     from the scored universe (EXIT_UNIVERSE — includes rows that turned
     ineligible; see OPTIMIZATION_FINDINGS.md HFA-069 H3 for the labeling
     follow-up).
  2. Mark survivors to the snapshot price and size new buys against TOTAL
     equity: one max_positions-th of equity per open slot, capped at 99%
     of cash, split across candidates by strategy.weight() (default 1.0 =
     equal weight).
  3. BUY top-scoring eligible names (score >= buy_threshold, not already
     held) until max_positions is reached.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def score_universe(strategy, rows: list[dict]) -> dict[str, dict]:
    """Compute scores for every row. Returns {ticker: {...row, score}}.
    Rows that are ineligible, unscorable, or raise are excluded."""
    strategy.prepare(rows)
    out = {}
    for row in rows:
        ticker = row.get('ticker')
        if not ticker or not strategy.is_eligible(row):
            continue
        try:
            s = strategy.score(row)
        except Exception as e:
            logger.debug('score() failed for %s: %s', ticker, e)
            continue
        if s is None:
            continue
        out[ticker] = {**row, 'score': s}
    return out


def run_rebalance_pass(strategy, rows: list[dict], positions: dict[str, dict],
                       cash: float, resolve_missing_price=None) -> dict:
    """Run one full rebalance decision pass.

    Parameters
    ----------
    strategy : EtfStrategy
    rows : list[dict]
        Recommendation-style rows (live snapshot or backtest-synthesized).
    positions : dict[str, dict]
        Current holdings: {ticker: {'shares': float, 'avg_cost': float}}.
        Not mutated — the final book is returned.
    cash : float
    resolve_missing_price : callable(ticker) -> float | None, optional
        Price source for held tickers absent from the scored universe.
        When it returns None (or is omitted) the sale books at avg_cost —
        zero P&L, logged as a warning.

    Returns
    -------
    dict with keys:
        universe        {ticker: scored row}
        sells           [{ticker, shares, price, proceeds, reason, score,
                          avg_cost, cash_after}]   (price includes slippage)
        buys            [{ticker, shares, price, cost, score, weight,
                          cash_after}]              (price includes slippage)
        kept            [{ticker, score, shares}]
        cash            final cash
        positions       final book {ticker: {shares, avg_cost[, entry_score]}}
        positions_value final book marked to snapshot prices (or avg_cost)
        total_value     cash + positions_value
    """
    cfg = strategy.config
    slippage = cfg.slippage_bps / 10_000.0  # bps → fraction
    universe = score_universe(strategy, rows)

    positions = {t: dict(p) for t, p in positions.items()}
    sells, buys, kept = [], [], []

    # ── Phase 1: SELL ─────────────────────────────────────────────────
    for ticker, pos in list(positions.items()):
        row = universe.get(ticker)
        if row is None:
            fresh = resolve_missing_price(ticker) if resolve_missing_price else None
            if fresh is not None and fresh > 0:
                sell_price = fresh * (1 - slippage)
            else:
                logger.warning(
                    'EXIT_UNIVERSE %s: no fresh quote — recording sale at avg_cost (P&L will read $0)',
                    ticker,
                )
                sell_price = pos['avg_cost']
            reason = 'EXIT_UNIVERSE'
            score = None
        elif row['score'] <= cfg.sell_threshold:
            sell_price = row['currentPrice'] * (1 - slippage)
            reason = 'SCORE_DROP'
            score = row['score']
        else:
            kept.append({'ticker': ticker, 'score': row['score'], 'shares': pos['shares']})
            continue

        proceeds = pos['shares'] * sell_price
        cash += proceeds
        sells.append({
            'ticker': ticker, 'shares': pos['shares'], 'price': sell_price,
            'proceeds': proceeds, 'reason': reason, 'score': score,
            'avg_cost': pos['avg_cost'], 'cash_after': cash,
        })
        del positions[ticker]

    # Mark held positions to the snapshot quote so new buys are sized
    # against *total equity*, not just cash. avg_cost fallback when the
    # held ticker has no fresh quote in this snapshot.
    held_value = 0.0
    for ticker, pos in positions.items():
        row = universe.get(ticker)
        mark = row['currentPrice'] if row and row.get('currentPrice') else pos['avg_cost']
        held_value += pos['shares'] * mark
    total_equity = cash + held_value

    # ── Phase 2: BUY ──────────────────────────────────────────────────
    green = [r for r in universe.values()
             if r['score'] >= cfg.buy_threshold and r['ticker'] not in positions]
    green.sort(key=lambda r: r['score'], reverse=True)

    buy_slots = max(0, cfg.max_positions - len(positions))
    candidates = green[:buy_slots]

    if candidates and cash > 0:
        # Weight-normalised sizing. Strategies opt into conviction-weighted
        # allocation by overriding weight(); default 1.0 → equal weight.
        # weight() <= 0 falls back to baseline 1.0 (never zero out a name
        # score() already approved) and logs, so a buggy weight() doesn't
        # silently masquerade as equal-weight conviction.
        raw_weights = []
        for row in candidates:
            raw_w = strategy.weight(row)
            clamped = max(raw_w, 0.0)
            if clamped <= 0:
                logger.warning(
                    'strategy %s returned non-positive weight (%.4f) for %s — '
                    'clamping to baseline 1.0; check the weight() implementation '
                    'if this is unexpected',
                    cfg.id, raw_w, row.get('ticker'),
                )
                clamped = 1.0
            raw_weights.append(clamped)
        total_weight = sum(raw_weights) or float(len(candidates))
        # One slot-equivalent of total equity per candidate (so opening
        # fewer than max_positions doesn't overload one name), capped by
        # 99% of cash to leave a buffer for slippage.
        target_total = min(
            (total_equity / cfg.max_positions) * len(candidates),
            cash * 0.99,
        )
        for row, w in zip(candidates, raw_weights):
            quote = row['currentPrice']
            if quote is None or quote <= 0:
                continue
            buy_price = quote * (1 + slippage)
            per_position = target_total * (w / total_weight)
            shares = per_position / buy_price
            if shares <= 0:
                continue
            cost = shares * buy_price
            if cost > cash:
                # Guard against floating-point drift on the cap above.
                shares = (cash * 0.999) / buy_price
                cost = shares * buy_price
                if shares <= 0:
                    continue
            cash -= cost
            positions[row['ticker']] = {
                'shares': shares, 'avg_cost': buy_price,
                'entry_score': row['score'],
            }
            buys.append({
                'ticker': row['ticker'], 'shares': shares, 'price': buy_price,
                'cost': cost, 'score': row['score'], 'weight': w,
                'cash_after': cash,
            })

    # ── Phase 3: mark the final book ──────────────────────────────────
    positions_value = 0.0
    for ticker, pos in positions.items():
        row = universe.get(ticker)
        mark = row['currentPrice'] if row and row.get('currentPrice') else pos['avg_cost']
        positions_value += pos['shares'] * mark

    return {
        'universe': universe,
        'sells': sells,
        'buys': buys,
        'kept': kept,
        'cash': cash,
        'positions': positions,
        'positions_value': positions_value,
        'total_value': cash + positions_value,
    }
