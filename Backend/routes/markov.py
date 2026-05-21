import numpy as np
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from data_fetcher import get_ohlcv, PRIORITY_HIGH

markov_bp = Blueprint('markov', __name__)

# Pine-script defaults (theory.pine) — fixed, not user-tunable in this port.
LOOKBACK = 20
BULL_PCT = 5.0
BEAR_PCT = 5.0
STATIONARY_POWER = 50
MIN_HOLD = 4

# Internal regime codes: 0 = Side, 1 = Bull, 2 = Bear (matches Pine spec §3).
REGIME_NAME = {0: 'Side', 1: 'Bull', 2: 'Bear'}
REGIME_FULL = {0: 'Sideways', 1: 'Bull', 2: 'Bear'}

# Display order is Bull / Bear / Side. Display row/col i → internal index.
INT_ORDER = [1, 2, 0]
DISPLAY_LABELS = ['Bull', 'Bear', 'Side']


@markov_bp.route('/api/markov/<ticker>')
def get_markov_analysis(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=365)

        hist = get_ohlcv(ticker, start, end, priority=PRIORITY_HIGH)

        if hist is None or hist.empty:
            return jsonify({'error': f'No data found for ticker "{ticker.upper()}".'}), 404

        if len(hist) <= LOOKBACK:
            return jsonify({
                'error': f'Insufficient history: need at least {LOOKBACK + 1} bars, got {len(hist)}.'
            }), 422

        close = hist['Close'].to_numpy(dtype=float)
        log_ret = np.full(len(close), np.nan)
        log_ret[LOOKBACK:] = np.log(close[LOOKBACK:] / close[:-LOOKBACK])

        # -1 sentinel marks warmup rows where log_ret is NaN.
        regime = np.where(np.isnan(log_ret), -1,
                 np.where(log_ret > BULL_PCT / 100.0, 1,
                 np.where(log_ret < -BEAR_PCT / 100.0, 2, 0))).astype(int)

        # Transition counts on confirmed bars only (all historical rows are confirmed).
        counts = np.zeros((3, 3), dtype=int)
        valid = regime[regime != -1]
        if len(valid) >= 2:
            for prev, curr in zip(valid[:-1], valid[1:]):
                counts[prev, curr] += 1

        # Row-normalise; uniform 1/3 fallback when a regime never appears (matches Pine).
        row_sums = counts.sum(axis=1, keepdims=True)
        with np.errstate(divide='ignore', invalid='ignore'):
            P_internal = np.where(row_sums > 0, counts / np.maximum(row_sums, 1), 1.0 / 3.0)

        # Stationary: M = P^STATIONARY_POWER; any row of M is the stationary vector.
        M = np.linalg.matrix_power(P_internal, STATIONARY_POWER)
        stat_internal = M[0]   # [side, bull, bear]

        # Remap internal → display (Bull / Bear / Side) for the response.
        P_display = P_internal[np.ix_(INT_ORDER, INT_ORDER)]

        # Debounced flip list (Pine's min_regime_hold). A new regime must hold for
        # MIN_HOLD consecutive confirmed bars before it gets a flip entry. Each
        # durable change is emitted exactly once.
        flips = []
        last_labelled = None
        dates = hist.index
        for i in range(MIN_HOLD - 1, len(regime)):
            r = regime[i]
            if r == -1:
                continue
            window = regime[i - MIN_HOLD + 1: i + 1]
            if np.all(window == r) and r != last_labelled:
                if last_labelled is not None:
                    flip_idx = i - (MIN_HOLD - 1)
                    flips.append({
                        'date': dates[flip_idx].strftime('%Y-%m-%d'),
                        'from': REGIME_FULL[int(last_labelled)],
                        'to': REGIME_FULL[int(r)],
                    })
                last_labelled = int(r)

        current = int(regime[-1])
        current_name = REGIME_FULL[current] if current != -1 else 'Unknown'

        # N-step forecast from today's regime. P^n[current, :] is the probability
        # distribution over regimes n bars ahead given we're in `current` today.
        # Reuses P_internal — same Markov assumption as the stationary calc.
        FORECAST_HORIZONS = [1, 3, 5, 10]
        forecast = {}
        if current != -1:
            for n in FORECAST_HORIZONS:
                Pn = np.linalg.matrix_power(P_internal, n)
                row = Pn[current]   # [side, bull, bear] in internal order
                forecast[f'{n}d'] = {
                    'bull': round(float(row[1]), 4),
                    'bear': round(float(row[2]), 4),
                    'side': round(float(row[0]), 4),
                }

        response = {
            'current_regime': current_name,
            'transition_matrix': {
                'rows': DISPLAY_LABELS,
                'cols': DISPLAY_LABELS,
                'values': [[round(float(v), 4) for v in row] for row in P_display],
            },
            'stationary': {
                'bull': round(float(stat_internal[1]), 4),
                'bear': round(float(stat_internal[2]), 4),
                'side': round(float(stat_internal[0]), 4),
            },
            'forecast': forecast,
            'transitions': flips,
            'params': {
                'lookback': LOOKBACK,
                'bull_pct': BULL_PCT,
                'bear_pct': BEAR_PCT,
                'stationary_power': STATIONARY_POWER,
                'min_hold': MIN_HOLD,
            },
            'bars_analyzed': int((regime != -1).sum()),
            'date_range': {
                'start': dates[0].strftime('%Y-%m-%d'),
                'end': dates[-1].strftime('%Y-%m-%d'),
            },
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
