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
from datetime import datetime, timedelta, timezone

from models import db, EtfPortfolio, EtfPosition, EtfTrade, EtfEquitySnapshot
from .strategies.base import EtfStrategy
from .rebalance_core import run_rebalance_pass
import data_fetcher

logger = logging.getLogger(__name__)


def _utc_iso(dt):
    # SQLite strips tzinfo from DateTime columns, so values come back naive
    # even though every write site stores datetime.now(timezone.utc). Without
    # an offset suffix, browsers parse the ISO string as local time and
    # rebalance times render in the wrong timezone (e.g. 13:30 instead of
    # 9:30 AM ET). Relabel naive datetimes as UTC before serializing.
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _fetch_exit_price(ticker: str) -> float | None:
    """Best-effort current price for a ticker that's dropped out of the
    recommendations universe. Tries .info first (currentPrice / regularMarket-
    Price — freshest quote, often already cached) and falls back to the most
    recent OHLCV close. Returns None if both fail (e.g. delisted).

    Used by EXIT_UNIVERSE sells so we don't book a fake $0 P&L by selling at
    cost basis when the ticker actually moved between buy and exit.
    """
    try:
        info = data_fetcher.get_ticker_info(ticker, priority=data_fetcher.PRIORITY_LOW)
        if info:
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            if price and price > 0:
                return float(price)
    except Exception as exc:
        logger.debug('EXIT_UNIVERSE %s: get_ticker_info failed: %s', ticker, exc)

    try:
        end = datetime.now(timezone.utc)
        hist = data_fetcher.get_ohlcv(ticker, end - timedelta(days=14), end,
                                      priority=data_fetcher.PRIORITY_LOW)
        if hist is not None and not hist.empty and 'Close' in hist.columns:
            close = hist['Close'].dropna()
            if not close.empty:
                last_close = float(close.iloc[-1])
                if last_close > 0:
                    return last_close
    except Exception as exc:
        logger.debug('EXIT_UNIVERSE %s: get_ohlcv failed: %s', ticker, exc)

    return None


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
                    'executedAt': _utc_iso(t.executed_at),
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


def rebalance(strategy: EtfStrategy, recs: list[dict], spy_price: float | None = None) -> dict:
    """Run one rebalance pass against the supplied recommendation snapshot.

    The decision math (sell / mark / buy / weight-normalised sizing) lives
    in rebalance_core.run_rebalance_pass, shared verbatim with the
    walk-forward backtest engine so backtests replay exactly this logic.
    This wrapper adapts ORM state in and persists trades, positions,
    portfolio cash, last_rebalance_at, and an equity snapshot out.
    """
    cfg = strategy.config
    portfolio = get_or_create_portfolio(strategy)
    now = datetime.now(timezone.utc)

    orm_positions = {p.ticker: p for p in portfolio.positions}
    book = {t: {'shares': p.shares, 'avg_cost': p.avg_cost}
            for t, p in orm_positions.items()}

    result = run_rebalance_pass(
        strategy, recs, book, portfolio.cash,
        resolve_missing_price=_fetch_exit_price,
    )

    actions = {'sells': [], 'buys': [], 'kept': result['kept']}

    for s in result['sells']:
        db.session.add(EtfTrade(
            portfolio_id=portfolio.id, ticker=s['ticker'], action='SELL',
            shares=s['shares'], price=round(s['price'], 4), score=s['score'],
            reason=s['reason'], cash_after=s['cash_after'], executed_at=now,
        ))
        pos = orm_positions.get(s['ticker'])
        if pos is not None:
            db.session.delete(pos)
        actions['sells'].append({
            'ticker': s['ticker'], 'shares': s['shares'], 'price': round(s['price'], 4),
            'proceeds': round(s['proceeds'], 2), 'reason': s['reason'], 'score': s['score'],
        })

    for b in result['buys']:
        db.session.add(EtfPosition(
            portfolio_id=portfolio.id, ticker=b['ticker'],
            shares=b['shares'], avg_cost=round(b['price'], 4),
            entry_score=b['score'], entry_at=now,
        ))
        db.session.add(EtfTrade(
            portfolio_id=portfolio.id, ticker=b['ticker'], action='BUY',
            shares=b['shares'], price=round(b['price'], 4), score=b['score'],
            reason='NEW_GREEN', cash_after=b['cash_after'], executed_at=now,
        ))
        actions['buys'].append({
            'ticker': b['ticker'], 'shares': round(b['shares'], 4),
            'price': round(b['price'], 4), 'cost': round(b['cost'], 2),
            'score': b['score'],
        })

    portfolio.cash = result['cash']

    db.session.add(EtfEquitySnapshot(
        portfolio_id=portfolio.id,
        total_value=round(result['total_value'], 2),
        cash=round(result['cash'], 2),
        positions_value=round(result['positions_value'], 2),
        spy_price=spy_price,
        recorded_at=now,
    ))

    portfolio.last_rebalance_at = now
    db.session.commit()

    logger.info(
        'Rebalance %s: %d sells, %d buys, %d held → total $%.2f (cash $%.2f)',
        cfg.id, len(actions['sells']), len(actions['buys']),
        len(actions['kept']), result['total_value'], portfolio.cash,
    )

    universe = result['universe']
    return {
        'strategyId': cfg.id,
        'rebalancedAt': _utc_iso(now),
        'totalValue': round(result['total_value'], 2),
        'cash': round(result['cash'], 2),
        'positionsValue': round(result['positions_value'], 2),
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
        'historicalBacktestSafe': strategy.historical_backtest_safe,
        'customUniverse': list(cfg.custom_universe) if cfg.custom_universe else None,
        'startingCapital': portfolio.starting_capital,
        'totalValue': round(total_value, 2),
        'cash': round(portfolio.cash, 2),
        'positionsValue': round(positions_value, 2),
        'totalReturnPct': round(total_return_pct, 2),
        'spyReturnPct': round(spy_return_pct, 2) if spy_return_pct is not None else None,
        'vsSpyPct': round(vs_spy_pct, 2) if vs_spy_pct is not None else None,
        'holdingsCount': len(portfolio.positions),
        'lastRebalanceAt': _utc_iso(portfolio.last_rebalance_at),
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
            'entryAt': _utc_iso(pos.entry_at),
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
            'recordedAt': _utc_iso(s.recorded_at),
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
                    'executedAt': _utc_iso(t.executed_at),
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
            'executedAt': _utc_iso(t.executed_at),
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
            'lastRebalanceAt': _utc_iso(portfolio.last_rebalance_at),
            'createdAt': _utc_iso(portfolio.created_at),
        },
        'holdings': holdings,
        'equitySeries': equity_series,
        'trades': trade_log,
        'tradeStats': trade_stats,
    }
