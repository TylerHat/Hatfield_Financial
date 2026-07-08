"""Custom ETF routes.

Reads are available to any logged-in user (the simulator state is shared
across all viewers). Writes (rebalance, reset) remain admin-only.

GET  /api/custom-etf/strategies              List registered strategies        (login)
GET  /api/custom-etf/<id>/state              Portfolio + holdings + trades     (login)
GET  /api/custom-etf/<id>/rankings           Score every recommendation         (login)
POST /api/custom-etf/<id>/rebalance          Run a rebalance pass               (admin)
POST /api/custom-etf/<id>/reset              Wipe state and start fresh         (admin)

Auto-rebalance has a 24h cooldown unless the request body sets {"force": true}.
The frontend triggers /rebalance after Recommendations finishes refreshing;
the cooldown prevents redundant trades when many users view the dashboard.
"""

import hmac
import logging
import os
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request

from auth import admin_required, login_required
from services.custom_etf.simulator import (
    rebalance, reset_portfolio, serialize_state, summarize, get_or_create_portfolio,
)
from services.custom_etf.strategies import get_strategy, list_strategies
from services.custom_etf import backtest_jobs
from services.custom_etf.walk_forward import run_generic_backtest

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
        from data_fetcher import get_spy_period, get_spy_history, PRIORITY_MEDIUM
        # First try the cached 5d period fetch at MEDIUM priority (LOW was
        # getting starved behind other calls during the daily auto-rebalance).
        hist = get_spy_period('5d', priority=PRIORITY_MEDIUM)
        if hist is None or hist.empty:
            # Fallback: explicit date-range fetch. Different code path, different
            # cache key — more likely to succeed when the period fetch is failing.
            # get_spy_history expects datetime objects (calls .strftime
            # internally); passing isoformat strings used to throw
            # AttributeError silently swallowed by the bare except below,
            # leaving spy_price NULL.
            end = datetime.now(timezone.utc) + timedelta(days=1)
            start = end - timedelta(days=10)
            hist = get_spy_history(start, end, priority=PRIORITY_MEDIUM)
        if hist is not None and not hist.empty:
            spy_price = float(hist['Close'].iloc[-1])
        else:
            logger.warning('SPY price fetch returned empty — snapshot will have NULL spy_price')
    except Exception:
        logger.warning('SPY price fetch failed', exc_info=True)

    return cached.get('stocks', []), spy_price


def _recs_by_ticker(stocks):
    return {s['ticker']: s for s in (stocks or []) if s.get('ticker')}


def _rows_for_strategy(strategy, stocks):
    """The rows a strategy scores: the S&P 500 recommendations snapshot by
    default, or price-feature rows synthesized for the strategy's fixed
    `custom_universe` (e.g. Sector Rotation's 11 SPDR ETFs)."""
    universe = strategy.config.custom_universe
    if universe:
        from services.custom_etf.custom_universe import build_rows_for_universe
        return build_rows_for_universe(universe)
    return stocks or []


@custom_etf_bp.route('/strategies', methods=['GET'])
@login_required
def list_etf_strategies():
    return jsonify({
        'strategies': [
            {**s.config.to_dict(), 'historicalBacktestSafe': s.historical_backtest_safe}
            for s in list_strategies()
        ],
    })


@custom_etf_bp.route('/summary', methods=['GET'])
@login_required
def summary_all():
    """Headline stats for every registered strategy — drives the multi-ETF
    comparison sidebar so adding a new strategy automatically shows up."""
    stocks, _ = _load_recommendations()
    return jsonify({
        'strategies': [
            summarize(s, _recs_by_ticker(_rows_for_strategy(s, stocks)))
            for s in list_strategies()
        ],
    })


@custom_etf_bp.route('/<strategy_id>/state', methods=['GET'])
@login_required
def get_state(strategy_id):
    strategy = get_strategy(strategy_id)
    if strategy is None:
        return jsonify({'error': f'Unknown strategy: {strategy_id}'}), 404

    stocks, _ = _load_recommendations()
    rows = _rows_for_strategy(strategy, stocks)
    state = serialize_state(strategy, _recs_by_ticker(rows))
    state['cooldownHours'] = REBALANCE_COOLDOWN.total_seconds() / 3600
    return jsonify(state)


@custom_etf_bp.route('/<strategy_id>/rankings', methods=['GET'])
@login_required
def get_rankings(strategy_id):
    """Score every recommendation under the strategy and return a ranked list.

    Powers the Recommendations tab's Custom ETF Strategies dropdown — picking
    a strategy shows the same S&P 500 universe sorted by that strategy's score.
    """
    strategy = get_strategy(strategy_id)
    if strategy is None:
        return jsonify({'error': f'Unknown strategy: {strategy_id}'}), 404

    stocks, _ = _load_recommendations()
    rows = _rows_for_strategy(strategy, stocks)
    if not rows:
        return jsonify({
            'strategyId': strategy.config.id,
            'strategyName': strategy.config.name,
            'rankings': [],
        })

    try:
        strategy.prepare(rows)
    except Exception as e:
        logger.debug('strategy.prepare() failed for %s: %s', strategy_id, e)

    held_tickers = {p.ticker for p in get_or_create_portfolio(strategy).positions}

    scored = []
    for row in rows:
        ticker = row.get('ticker')
        if not ticker:
            continue
        eligible = strategy.is_eligible(row)
        score = None
        if eligible:
            try:
                score = strategy.score(row)
            except Exception as e:
                logger.debug('score() failed for %s on %s: %s', ticker, strategy_id, e)
                score = None
        scored.append({
            'ticker': ticker,
            'score': score,
            'eligible': eligible,
            'held': ticker in held_tickers,
        })

    # Sort: scored rows by score desc, then unscored last (stable by ticker).
    scored.sort(key=lambda r: (r['score'] is None, -(r['score'] or 0), r['ticker']))
    for i, r in enumerate(scored, start=1):
        r['rank'] = i if r['score'] is not None else None

    return jsonify({
        'strategyId': strategy.config.id,
        'strategyName': strategy.config.name,
        'buyThreshold': strategy.config.buy_threshold,
        'sellThreshold': strategy.config.sell_threshold,
        'rankings': scored,
    })


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
    rows = _rows_for_strategy(strategy, stocks)
    if not rows:
        if strategy.config.custom_universe:
            return jsonify({
                'status': 'no_data',
                'message': 'Could not build price rows for the strategy universe — yfinance may be rate-limited.',
            }), 503
        return jsonify({
            'status': 'no_data',
            'message': 'Recommendations cache is empty — load /api/recommendations first.',
        }), 503

    try:
        result = rebalance(strategy, rows, spy_price=spy_price)
        result['status'] = 'ok'
        # Return updated full state so the UI can re-render in one round trip
        result['state'] = serialize_state(strategy, _recs_by_ticker(rows))
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
            rows = _rows_for_strategy(strategy, stocks)
            if not rows:
                results.append({'strategyId': strategy.config.id,
                                'error': 'no rows for strategy universe'})
                continue
            r = rebalance(strategy, rows, spy_price=spy_price)
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
        'state': serialize_state(strategy, _recs_by_ticker(_rows_for_strategy(strategy, stocks))),
    })


# ── Backtest (any historical-backtest-safe strategy) ────────────────────
# The walk-forward engine replays the LIVE rebalance semantics against
# point-in-time price features (services/custom_etf/walk_forward.py).
# Strategies whose inputs are today-snapshot .info / analyst fields are
# refused — a backtest of those would leak hindsight.
# Backtests are long-running (10s–5min depending on cache state). Run as a
# background job; the UI polls /backtest/<job_id> for progress + results.

@custom_etf_bp.route('/<strategy_id>/backtest', methods=['POST'])
@admin_required
def start_backtest(strategy_id):
    strategy = get_strategy(strategy_id)
    if strategy is None:
        return jsonify({'error': f'Unknown strategy: {strategy_id}'}), 404
    if not strategy.historical_backtest_safe:
        return jsonify({
            'error': (
                f'{strategy.config.name} cannot be backtested: it scores '
                'fundamentals / analyst-consensus fields that yfinance only '
                'serves as a today-snapshot, so a historical run would apply '
                "today's data to past dates (hindsight bias)."
            ),
        }), 400

    body = request.get_json(silent=True) or {}
    years = body.get('years', 1)
    cadence = body.get('cadence', 'weekly')

    if years not in (1, 3):
        return jsonify({'error': 'years must be 1 or 3'}), 400
    if cadence not in ('weekly', 'daily'):
        return jsonify({'error': 'cadence must be "weekly" or "daily"'}), 400

    spec = {'strategy': strategy_id, 'years': years, 'cadence': cadence}
    job_id = backtest_jobs.create_job(spec)
    backtest_jobs.run_job_async(job_id, run_generic_backtest, strategy_id, years, cadence)

    return jsonify({'jobId': job_id, 'spec': spec}), 202


@custom_etf_bp.route('/backtest/<job_id>', methods=['GET'])
@admin_required
def get_backtest_status(job_id):
    job = backtest_jobs.get_job(job_id)
    if job is None:
        return jsonify({'error': 'Job not found (may have expired)'}), 404
    return jsonify(job)
