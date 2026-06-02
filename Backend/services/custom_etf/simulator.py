"""Custom ETF paper-trading simulator.

Strategy-agnostic. Given an EtfStrategy and a fresh recommendations snapshot,
it (a) sells holdings whose score has dropped below the strategy's
sell_threshold or that have left the universe, then (b) buys top-ranked
green stocks (score >= buy_threshold) up to max_positions, sizing each new
buy at 1 / max_positions of total equity (cash + marked holdings), bounded
by available cash so we never overdraft.

State persists in the etf_portfolios / etf_positions / etf_trades /
etf_equity_snapshots tables.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from models import db, EtfPortfolio, EtfPosition, EtfTrade, EtfEquitySnapshot
from .strategies.base import EtfStrategy

logger = logging.getLogger(__name__)


def _closed_trade_stats(portfolio_id: int) -> dict:
    """Walk every trade for the portfolio oldest → newest, maintaining a
    running weighted-average cost basis per ticker, and aggregate realized
    P&L stats from each SELL. Used by both summarize() and serialize_state().
    """
    trades = (EtfTrade.query
              .filter_by(portfolio_id=portfolio_id)
              .order_by(EtfTrade.executed_at.asc()).all())
    cost_basis = {}
    wins = losses = 0
    realized_total = 0.0
    best = None  # {'ticker', 'pnl', 'pnlPct', 'executedAt'}
    worst = None
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
            if cb and cb['avg_cost']:
                pnl = (t.price - cb['avg_cost']) * t.shares
                pnl_pct = (t.price / cb['avg_cost'] - 1) * 100
                realized_total += pnl
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
                trade_summary = {
                    'ticker': t.ticker,
                    'pnl': round(pnl, 2),
                    'pnlPct': round(pnl_pct, 2),
                    'executedAt': t.executed_at.isoformat(),
                }
                if best is None or pnl > best['pnl']:
                    best = trade_summary
                if worst is None or pnl < worst['pnl']:
                    worst = trade_summary
                cb['shares'] = max(0.0, cb['shares'] - t.shares)
                if cb['shares'] <= 1e-9:
                    cost_basis.pop(t.ticker, None)
    total = wins + losses
    return {
        'wins': wins,
        'losses': losses,
        'closedTrades': total,
        'winRatePct': round((wins / total) * 100, 1) if total else None,
        'realizedPnl': round(realized_total, 2),
        'bestTrade': best,
        'worstTrade': worst,
    }


def get_or_create_portfolio(strategy: EtfStrategy) -> EtfPortfolio:
    portfolio = EtfPortfolio.query.filter_by(strategy_id=strategy.config.id).first()
    if portfolio is None:
        portfolio = EtfPortfolio(
            strategy_id=strategy.config.id,
            cash=strategy.config.starting_capital,
            starting_capital=strategy.config.starting_capital,
        )
        db.session.add(portfolio)
        db.session.commit()
        logger.info('Created ETF portfolio for strategy %s ($%.0f)',
                    strategy.config.id, strategy.config.starting_capital)
    return portfolio


def reset_portfolio(strategy: EtfStrategy) -> EtfPortfolio:
    """Wipe all simulator state for the given strategy and start fresh."""
    portfolio = EtfPortfolio.query.filter_by(strategy_id=strategy.config.id).first()
    if portfolio is not None:
        db.session.delete(portfolio)
        db.session.commit()
    return get_or_create_portfolio(strategy)


def _score_universe(strategy: EtfStrategy, recs: list[dict]) -> dict[str, dict]:
    """Compute scores for every recommendation row. Returns {ticker: {...row, score}}."""
    strategy.prepare(recs)
    out = {}
    for row in recs:
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


def rebalance(strategy: EtfStrategy, recs: list[dict], spy_price: float | None = None) -> dict:
    """Run one rebalance pass against the supplied recommendation snapshot.

    Returns a dict summarizing the actions taken. Persists trades, positions,
    portfolio cash, last_rebalance_at, and an equity snapshot.
    """
    cfg = strategy.config
    portfolio = get_or_create_portfolio(strategy)
    universe = _score_universe(strategy, recs)
    slippage = cfg.slippage_bps / 10_000.0  # bps → fraction
    now = datetime.now(timezone.utc)

    actions = {'sells': [], 'buys': [], 'kept': []}

    # ── Phase 1: SELL ─────────────────────────────────────────────────
    # Sell positions whose score has dropped to <= sell_threshold OR that
    # have dropped out of the recommendation universe entirely.
    held = {p.ticker: p for p in portfolio.positions}

    for ticker, pos in list(held.items()):
        row = universe.get(ticker)
        if row is None:
            # Out-of-universe: liquidate at last known cost basis (no fresh quote available)
            sell_price = pos.avg_cost
            reason = 'EXIT_UNIVERSE'
            score = None
        elif row['score'] <= cfg.sell_threshold:
            sell_price = row['currentPrice'] * (1 - slippage)
            reason = 'SCORE_DROP'
            score = row['score']
        else:
            actions['kept'].append({'ticker': ticker, 'score': row['score'], 'shares': pos.shares})
            continue

        proceeds = pos.shares * sell_price
        portfolio.cash += proceeds
        db.session.add(EtfTrade(
            portfolio_id=portfolio.id, ticker=ticker, action='SELL',
            shares=pos.shares, price=round(sell_price, 4), score=score,
            reason=reason, cash_after=portfolio.cash, executed_at=now,
        ))
        actions['sells'].append({
            'ticker': ticker, 'shares': pos.shares, 'price': round(sell_price, 4),
            'proceeds': round(proceeds, 2), 'reason': reason, 'score': score,
        })
        db.session.delete(pos)
        del held[ticker]

    # Mark held positions to current quote so new buys can be sized against
    # *total equity*, not just cash. Falls back to avg_cost when the held
    # ticker has no fresh quote in this snapshot.
    held_value = 0.0
    for ticker, pos in held.items():
        row = universe.get(ticker)
        mark = row['currentPrice'] if row and row.get('currentPrice') else pos.avg_cost
        held_value += pos.shares * mark
    total_equity = portfolio.cash + held_value

    # ── Phase 2: BUY ──────────────────────────────────────────────────
    # Candidates: rows in green (score >= buy_threshold), not currently held,
    # ranked by score desc. Take top (max_positions - len(held)) of them.
    green = [r for r in universe.values()
             if r['score'] >= cfg.buy_threshold and r['ticker'] not in held]
    green.sort(key=lambda r: r['score'], reverse=True)

    buy_slots = max(0, cfg.max_positions - len(held))
    candidates = green[:buy_slots]

    if candidates and portfolio.cash > 0:
        # Weight-normalised sizing. Each strategy can opt into conviction-
        # weighted allocation by overriding weight(); the default is 1.0 →
        # equal weight, identical to the legacy behavior.
        #
        # Allocatable dollars: target one slot-equivalent of total equity per
        # candidate (so opening fewer than max_positions doesn't overload one
        # name), capped by 99% of cash to leave a buffer for slippage.
        raw_weights = [max(strategy.weight(row), 0.0) or 1.0 for row in candidates]
        total_weight = sum(raw_weights) or float(len(candidates))
        target_total = min(
            (total_equity / cfg.max_positions) * len(candidates),
            portfolio.cash * 0.99,
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
            if cost > portfolio.cash:
                # Guard against floating-point drift on the cap above.
                shares = (portfolio.cash * 0.999) / buy_price
                cost = shares * buy_price
                if shares <= 0:
                    continue
            portfolio.cash -= cost
            db.session.add(EtfPosition(
                portfolio_id=portfolio.id, ticker=row['ticker'],
                shares=shares, avg_cost=round(buy_price, 4),
                entry_score=row['score'], entry_at=now,
            ))
            db.session.add(EtfTrade(
                portfolio_id=portfolio.id, ticker=row['ticker'], action='BUY',
                shares=shares, price=round(buy_price, 4), score=row['score'],
                reason='NEW_GREEN', cash_after=portfolio.cash, executed_at=now,
            ))
            actions['buys'].append({
                'ticker': row['ticker'], 'shares': round(shares, 4),
                'price': round(buy_price, 4), 'cost': round(cost, 2),
                'score': row['score'],
            })

    # ── Phase 3: snapshot equity ──────────────────────────────────────
    # Mark held positions to current quote when available, else last cost.
    # Refresh the ORM identity map so newly-added positions are visible.
    db.session.flush()
    db.session.expire(portfolio, ['positions'])
    positions_value = 0.0
    for pos in portfolio.positions:
        row = universe.get(pos.ticker)
        mark = row['currentPrice'] if row and row.get('currentPrice') else pos.avg_cost
        positions_value += pos.shares * mark
    total_value = portfolio.cash + positions_value

    db.session.add(EtfEquitySnapshot(
        portfolio_id=portfolio.id,
        total_value=round(total_value, 2),
        cash=round(portfolio.cash, 2),
        positions_value=round(positions_value, 2),
        spy_price=spy_price,
        recorded_at=now,
    ))

    portfolio.last_rebalance_at = now
    db.session.commit()

    logger.info(
        'Rebalance %s: %d sells, %d buys, %d held → total $%.2f (cash $%.2f)',
        cfg.id, len(actions['sells']), len(actions['buys']),
        len(actions['kept']), total_value, portfolio.cash,
    )

    return {
        'strategyId': cfg.id,
        'rebalancedAt': now.isoformat(),
        'totalValue': round(total_value, 2),
        'cash': round(portfolio.cash, 2),
        'positionsValue': round(positions_value, 2),
        'actions': actions,
        'universeSize': len(universe),
        'greenCount': sum(1 for r in universe.values() if r['score'] >= cfg.buy_threshold),
    }


def summarize(strategy: EtfStrategy, recs_by_ticker: dict[str, dict]) -> dict:
    """Lightweight stats for the multi-ETF comparison sidebar. Avoids
    serializing trade/equity history — just the headline numbers."""
    cfg = strategy.config
    portfolio = get_or_create_portfolio(strategy)

    positions_value = 0.0
    for pos in portfolio.positions:
        row = recs_by_ticker.get(pos.ticker, {})
        mark = row.get('currentPrice') or pos.avg_cost
        positions_value += pos.shares * mark
    total_value = portfolio.cash + positions_value
    total_return_pct = ((total_value / portfolio.starting_capital) - 1) * 100

    snapshots = (EtfEquitySnapshot.query
                 .filter_by(portfolio_id=portfolio.id)
                 .order_by(EtfEquitySnapshot.recorded_at.asc()).all())
    spy_baseline = next((s.spy_price for s in snapshots if s.spy_price), None)
    spy_latest = next((s.spy_price for s in reversed(snapshots) if s.spy_price), None)
    spy_return_pct = None
    vs_spy_pct = None
    if spy_baseline and spy_latest and spy_baseline > 0:
        spy_return_pct = ((spy_latest / spy_baseline) - 1) * 100
        vs_spy_pct = total_return_pct - spy_return_pct

    stats = _closed_trade_stats(portfolio.id)

    return {
        'id': cfg.id,
        'name': cfg.name,
        'description': cfg.description,
        'maxPositions': cfg.max_positions,
        'startingCapital': portfolio.starting_capital,
        'totalValue': round(total_value, 2),
        'cash': round(portfolio.cash, 2),
        'positionsValue': round(positions_value, 2),
        'totalReturnPct': round(total_return_pct, 2),
        'spyReturnPct': round(spy_return_pct, 2) if spy_return_pct is not None else None,
        'vsSpyPct': round(vs_spy_pct, 2) if vs_spy_pct is not None else None,
        'holdingsCount': len(portfolio.positions),
        'lastRebalanceAt': portfolio.last_rebalance_at.isoformat()
            if portfolio.last_rebalance_at else None,
        'wins': stats['wins'],
        'losses': stats['losses'],
        'closedTrades': stats['closedTrades'],
        'winRatePct': stats['winRatePct'],
        'realizedPnl': stats['realizedPnl'],
        'bestTrade': stats['bestTrade'],
        'worstTrade': stats['worstTrade'],
    }


def serialize_state(strategy: EtfStrategy, recs_by_ticker: dict[str, dict]) -> dict:
    """Build the JSON payload returned by GET /api/custom-etf/<id>/state.

    `recs_by_ticker` is the latest recommendations keyed by ticker — used to
    mark positions to current price and surface live scores.
    """
    cfg = strategy.config
    portfolio = get_or_create_portfolio(strategy)
    # Prime any universe-level state the strategy needs to score individual rows.
    strategy.prepare(list(recs_by_ticker.values()))

    holdings = []
    positions_value = 0.0
    for pos in sorted(portfolio.positions, key=lambda p: p.ticker):
        row = recs_by_ticker.get(pos.ticker, {})
        current_price = row.get('currentPrice') or pos.avg_cost
        # Live score not stored on rec rows — strategy computes it on demand.
        try:
            current_score = strategy.score(row) if row else None
        except Exception:
            current_score = None
        market_value = pos.shares * current_price
        positions_value += market_value
        holdings.append({
            'ticker': pos.ticker,
            'name': row.get('name'),
            'shares': round(pos.shares, 4),
            'avgCost': round(pos.avg_cost, 4),
            'currentPrice': round(current_price, 4),
            'marketValue': round(market_value, 2),
            'unrealizedPnl': round(market_value - pos.shares * pos.avg_cost, 2),
            'unrealizedPnlPct': round((current_price / pos.avg_cost - 1) * 100, 2)
                                 if pos.avg_cost else None,
            'entryScore': pos.entry_score,
            'currentScore': current_score,
            'entryAt': pos.entry_at.isoformat() if pos.entry_at else None,
        })

    total_value = portfolio.cash + positions_value
    total_return_pct = ((total_value / portfolio.starting_capital) - 1) * 100

    snapshots = (EtfEquitySnapshot.query
                 .filter_by(portfolio_id=portfolio.id)
                 .order_by(EtfEquitySnapshot.recorded_at.asc()).all())
    spy_baseline = next((s.spy_price for s in snapshots if s.spy_price), None)

    equity_series = []
    for s in snapshots:
        spy_value = None
        if spy_baseline and s.spy_price:
            spy_value = round(portfolio.starting_capital * (s.spy_price / spy_baseline), 2)
        equity_series.append({
            'recordedAt': s.recorded_at.isoformat(),
            'totalValue': s.total_value,
            'cash': s.cash,
            'positionsValue': s.positions_value,
            'spyValue': spy_value,
        })

    # Walk trades oldest → newest to maintain a running avg cost per ticker so
    # we can attach realized P&L to each SELL. Then slice the last 200 and
    # reverse for the desc-ordered UI.
    all_trades = (EtfTrade.query
                  .filter_by(portfolio_id=portfolio.id)
                  .order_by(EtfTrade.executed_at.asc()).all())
    cost_basis = {}  # ticker → {'shares': float, 'avg_cost': float}
    enriched = []
    wins = losses = 0
    realized_total = 0.0
    best_trade = None
    worst_trade = None
    for t in all_trades:
        realized_pnl = None
        realized_pnl_pct = None
        if t.action == 'BUY':
            cb = cost_basis.get(t.ticker, {'shares': 0.0, 'avg_cost': 0.0})
            new_shares = cb['shares'] + t.shares
            if new_shares > 0:
                cb['avg_cost'] = (cb['shares'] * cb['avg_cost'] + t.shares * t.price) / new_shares
            cb['shares'] = new_shares
            cost_basis[t.ticker] = cb
        elif t.action == 'SELL':
            cb = cost_basis.get(t.ticker)
            if cb and cb['avg_cost']:
                realized_pnl = (t.price - cb['avg_cost']) * t.shares
                realized_pnl_pct = (t.price / cb['avg_cost'] - 1) * 100
                realized_total += realized_pnl
                if realized_pnl > 0:
                    wins += 1
                else:
                    losses += 1
                trade_summary = {
                    'ticker': t.ticker,
                    'pnl': round(realized_pnl, 2),
                    'pnlPct': round(realized_pnl_pct, 2),
                    'executedAt': t.executed_at.isoformat(),
                }
                if best_trade is None or realized_pnl_pct > best_trade['pnlPct']:
                    best_trade = trade_summary
                if worst_trade is None or realized_pnl_pct < worst_trade['pnlPct']:
                    worst_trade = trade_summary
                cb['shares'] = max(0.0, cb['shares'] - t.shares)
                if cb['shares'] <= 1e-9:
                    cost_basis.pop(t.ticker, None)
        enriched.append({
            'ticker': t.ticker,
            'action': t.action,
            'shares': round(t.shares, 4),
            'price': t.price,
            'value': round(t.shares * t.price, 2),
            'score': t.score,
            'reason': t.reason,
            'cashAfter': t.cash_after,
            'executedAt': t.executed_at.isoformat(),
            'realizedPnl': round(realized_pnl, 2) if realized_pnl is not None else None,
            'realizedPnlPct': round(realized_pnl_pct, 2) if realized_pnl_pct is not None else None,
        })
    trade_log_limit = 200
    trade_log = list(reversed(enriched[-trade_log_limit:]))
    closed_total = wins + losses
    trade_stats = {
        'wins': wins,
        'losses': losses,
        'closedTrades': closed_total,
        'totalTrades': len(enriched),
        'tradesShown': len(trade_log),
        'winRatePct': round((wins / closed_total) * 100, 1) if closed_total else None,
        'realizedPnl': round(realized_total, 2),
        'bestTrade': best_trade,
        'worstTrade': worst_trade,
    }

    return {
        'strategy': cfg.to_dict(),
        'portfolio': {
            'cash': round(portfolio.cash, 2),
            'positionsValue': round(positions_value, 2),
            'totalValue': round(total_value, 2),
            'startingCapital': portfolio.starting_capital,
            'totalReturnPct': round(total_return_pct, 2),
            'lastRebalanceAt': portfolio.last_rebalance_at.isoformat()
                if portfolio.last_rebalance_at else None,
            'createdAt': portfolio.created_at.isoformat() if portfolio.created_at else None,
        },
        'holdings': holdings,
        'equitySeries': equity_series,
        'trades': trade_log,
        'tradeStats': trade_stats,
    }
