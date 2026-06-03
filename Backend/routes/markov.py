from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from data_fetcher import get_ohlcv, PRIORITY_HIGH
from services.markov import (
    analyze_markov,
    DISPLAY_LABELS,
    LOOKBACK,
    BULL_PCT,
    BEAR_PCT,
    STATIONARY_POWER,
    MIN_HOLD,
)

markov_bp = Blueprint('markov', __name__)


@markov_bp.route('/api/markov/<ticker>')
def get_markov_analysis(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        # 730d default (≈2 years of trading) gives the 3×3 transition matrix
        # ~500 valid bars after the LOOKBACK warmup — enough for stable
        # row-normalised probabilities. 365d alone was too noisy for the
        # display matrix on lower-volatility names.
        start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=730)

        hist = get_ohlcv(ticker, start, end, priority=PRIORITY_HIGH)

        if hist is None or hist.empty:
            return jsonify({'error': f'No data found for ticker "{ticker.upper()}".'}), 404

        if len(hist) <= LOOKBACK:
            return jsonify({
                'error': f'Insufficient history: need at least {LOOKBACK + 1} bars, got {len(hist)}.'
            }), 422

        result = analyze_markov(hist['Close'].to_numpy(dtype=float), dates=hist.index)
        if result is None:
            return jsonify({'error': 'Markov analysis failed — no valid bars.'}), 422

        return jsonify({
            'current_regime': result['current_regime'],
            'transition_matrix': {
                'rows': DISPLAY_LABELS,
                'cols': DISPLAY_LABELS,
                'values': [[round(v, 4) for v in row] for row in result['transition_matrix_display']],
            },
            'stationary': {k: round(v, 4) for k, v in result['stationary'].items()},
            'forecast': {
                horizon: {k: round(v, 4) for k, v in row.items()}
                for horizon, row in result['forecast'].items()
            },
            'transitions': result['transitions'],
            'params': {
                'lookback': LOOKBACK,
                'bull_pct': BULL_PCT,
                'bear_pct': BEAR_PCT,
                'stationary_power': STATIONARY_POWER,
                'min_hold': MIN_HOLD,
            },
            'bars_analyzed': result['bars_analyzed'],
            'transitions_observed': result['transitions_observed'],
            'low_confidence': result['low_confidence'],
            'date_range': {
                'start': hist.index[0].strftime('%Y-%m-%d'),
                'end': hist.index[-1].strftime('%Y-%m-%d'),
            },
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
