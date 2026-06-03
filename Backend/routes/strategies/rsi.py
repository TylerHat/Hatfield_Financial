import pandas as pd
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from data_fetcher import get_ohlcv
from services.indicators import compute_rsi as _compute_rsi

rsi_bp = Blueprint('rsi', __name__)


@rsi_bp.route('/api/strategy/rsi/<ticker>')
def rsi_strategy(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)

        # Wilder RSI stabilises after ~3× period bars; 60 is comfortable.
        hist = get_ohlcv(ticker, user_start, end, warmup_days=60)

        if hist is None or hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.', 'signals': []}), 404

        hist['RSI'] = _compute_rsi(hist['Close'])

        # Trim to the user-requested window after RSI is computed
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]

        signals = []

        for i in range(1, len(hist)):
            row = hist.iloc[i]
            prev = hist.iloc[i - 1]

            if pd.isna(row['RSI']) or pd.isna(prev['RSI']):
                continue

            rsi = float(row['RSI'])
            prev_rsi = float(prev['RSI'])

            # RSI crosses below 30 → enters oversold → BUY
            if prev_rsi >= 30 and rsi < 30:
                score = min(100, int((30 - rsi) / 30 * 100))
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'RSI entered oversold territory at {rsi:.1f} '
                        f'(crossed below 30) — potential reversal upward'
                    ),
                })

            # RSI crosses above 70 → enters overbought → SELL
            elif prev_rsi <= 70 and rsi > 70:
                score = min(100, int((rsi - 70) / 30 * 100))
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'SELL',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'RSI entered overbought territory at {rsi:.1f} '
                        f'(crossed above 70) — potential reversal downward'
                    ),
                })

        return jsonify({'signals': signals})

    except Exception as e:
        msg = str(e)
        if 'rate' in msg.lower() or '429' in msg:
            msg = 'Yahoo Finance rate limit reached. Wait a moment and try again.'
        elif 'connection' in msg.lower() or 'timeout' in msg.lower():
            msg = 'Could not reach Yahoo Finance. Check your network connection.'
        return jsonify({'error': msg, 'signals': []}), 500
