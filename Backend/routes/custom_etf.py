"""Custom ETF routes — admin-only.

GET  /api/custom-etf/strategies              List registered strategies
GET  /api/custom-etf/<id>/state              Portfolio + holdings + trades + equity series
POST /api/custom-etf/<id>/rebalance          Run a rebalance pass against fresh recs
POST /api/custom-etf/<id>/reset              Wipe state and start fresh

Auto-rebalance has a 24h cooldown unless the request body sets {"force": true}.
The frontend triggers /rebalance after Recommendations finishes refreshing;
the cooldown prevents redundant trades when many users view the dashboard.
"""

import hmac
import logging
import os
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request

from auth import admin_required
from services.custom_etf.simulator import (
    rebalance, reset_portfolio, serialize_state, summarize, get_or_create_portfolio,
)
from services.custom_etf.strategies import get_strategy, list_strategies

logger = logging.getLogger(__name__)

custom_etf_bp = Blueprint('custom_etf', __name__, url_prefix='/api/custom-etf')

REBALANCE_COOLDOWN = timedelta(hours=24)


def _load_recommendations():
    """Pull the latest cached recommendations payload. Returns (stocks, spy_price)."""
    from routes.recommendations import _cache, _CACHE_KEY, _CACHE_TTL, _read_s3_cache
    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if not cached:
        s3 = _read_s3_cache()
        if s3:
            cached = s3
    if not cached:
        return None, None

    spy_price = None
    try:
        from data_fetcher import get_spy_period, PRIORITY_LOW
        hist = get_spy_period('5d', priority=PRIORITY_LOW)
        if hist is not None and not hist.empty:
            spy_price = float(hist['Close'].iloc[-1])
    except Exception as e:
        logger.debug('SPY price fetch failed: %s', e)

    return cached.get('stocks', []), spy_price


def _recs_by_ticker(stocks):
    return {s['ticker']: s for s in (stocks or []) if s.get('ticker')}


@custom_etf_bp.route('/strategies', methods=['GET'])
@admin_required
def list_etf_strategies():
    return jsonify({
        'strategies': [s.config.to_dict() for s in list_strategies()],
    })


@custom_etf_bp.route('/summary', methods=['GET'])
@admin_required
def summary_all():
    """Headline stats for every registered strategy — drives the multi-ETF
    comparison sidebar so adding a new strategy automatically shows up."""
    stocks, _ = _load_recommendations()
    by_ticker = _recs_by_ticker(stocks)
    return jsonify({
        'strategies': [summarize(s, by_ticker) for s in list_strategies()],
    })


@custom_etf_bp.route('/<strategy_id>/state', methods=['GET'])
@admin_required
def get_state(strategy_id):
    strategy = get_strategy(strategy_id)
    if strategy is None:
        return jsonify({'error': f'Unknown strategy: {strategy_id}'}), 404

    stocks, _ = _load_recommendations()
    state = serialize_state(strategy, _recs_by_ticker(stocks))
    state['cooldownHours'] = REBALANCE_COOLDOWN.total_seconds() / 3600
    return jsonify(state)


@custom_etf_bp.route('/<strategy_id>/rebalance', methods=['POST'])
@admin_required
def trigger_rebalance(strategy_id):
    strategy = get_strategy(strategy_id)
    if strategy is None:
        return jsonify({'error': f'Unknown strategy: {strategy_id}'}), 404

    body = request.get_json(silent=True) or {}
    force = bool(body.get('force', False))

    portfolio = get_or_create_portfolio(strategy)
    if not force and portfolio.last_rebalance_at is not None:
        # Treat last_rebalance_at as UTC (datetime may be naive on SQLite)
        last = portfolio.last_rebalance_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last
        if elapsed < REBALANCE_COOLDOWN:
            remaining = REBALANCE_COOLDOWN - elapsed
            return jsonify({
                'status': 'cooldown',
                'message': f'Cooldown active — next rebalance in {int(remaining.total_seconds() // 3600)}h '
                           f'{int((remaining.total_seconds() % 3600) // 60)}m',
                'nextEligibleAt': (last + REBALANCE_COOLDOWN).isoformat(),
            }), 200

    stocks, spy_price = _load_recommendations()
    if not stocks:
        return jsonify({
            'status': 'no_data',
            'message': 'Recommendations cache is empty — load /api/recommendations first.',
        }), 503

    try:
        result = rebalance(strategy, stocks, spy_price=spy_price)
        result['status'] = 'ok'
        # Return updated full state so the UI can re-render in one round trip
        result['state'] = serialize_state(strategy, _recs_by_ticker(stocks))
        return jsonify(result)
    except Exception as e:
        logger.error('rebalance failed for %s: %s', strategy_id, e, exc_info=True)
        return jsonify({'error': f'Rebalance failed: {e}'}), 500


@custom_etf_bp.route('/auto-rebalance-all', methods=['POST'])
def auto_rebalance_all():
    """Internal endpoint hit by the daily EventBridge scheduler. Force-rebalances
    every registered strategy. Authenticated via a shared secret in the
    X-Internal-Secret header (env: INTERNAL_API_SECRET) — no JWT involved,
    since the caller is a Lambda, not a logged-in user.
    """
    expected = os.environ.get('INTERNAL_API_SECRET', '')
    provided = request.headers.get('X-Internal-Secret', '')
    if not expected or not hmac.compare_digest(expected, provided):
        return jsonify({'error': 'Unauthorized'}), 401

    stocks, spy_price = _load_recommendations()
    if not stocks:
        logger.warning('Auto-rebalance skipped — recommendations cache empty')
        return jsonify({'status': 'no_data', 'message': 'Recommendations cache empty'}), 503

    results = []
    for strategy in list_strategies():
        try:
            r = rebalance(strategy, stocks, spy_price=spy_price)
            results.append({
                'strategyId': strategy.config.id,
                'totalValue': r['totalValue'],
                'sells': len(r['actions']['sells']),
                'buys': len(r['actions']['buys']),
                'kept': len(r['actions']['kept']),
            })
        except Exception as e:
            logger.error('Auto-rebalance failed for %s: %s', strategy.config.id, e, exc_info=True)
            results.append({'strategyId': strategy.config.id, 'error': str(e)})

    logger.info('Auto-rebalance complete — %d strategies processed', len(results))
    return jsonify({
        'status': 'ok',
        'rebalancedAt': datetime.now(timezone.utc).isoformat(),
        'results': results,
    })


@custom_etf_bp.route('/<strategy_id>/reset', methods=['POST'])
@admin_required
def reset_etf(strategy_id):
    strategy = get_strategy(strategy_id)
    if strategy is None:
        return jsonify({'error': f'Unknown strategy: {strategy_id}'}), 404

    reset_portfolio(strategy)
    stocks, _ = _load_recommendations()
    return jsonify({
        'status': 'reset',
        'state': serialize_state(strategy, _recs_by_ticker(stocks)),
    })
