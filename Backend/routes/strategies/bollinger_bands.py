import pandas as pd
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from data_fetcher import get_ohlcv

bb_bp = Blueprint('bollinger_bands', __name__)


@bb_bp.route('/api/strategy/bollinger-bands/<ticker>')
def bollinger_bands(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)

        hist = get_ohlcv(ticker, user_start, end)

        if hist is None or hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.', 'signals': []}), 404

        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['STD20'] = hist['Close'].rolling(20).std()
        hist['Upper'] = hist['MA20'] + 2 * hist['STD20']
        hist['Lower'] = hist['MA20'] - 2 * hist['STD20']
        # Volume confirmation: require volume > 1.3× 20-day average to filter weak signals
        hist['VolMA20'] = hist['Volume'].rolling(20).mean()

        # Trim to the user-requested window after bands are computed
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]

        signals = []

        for i in range(1, len(hist)):
            row = hist.iloc[i]
            prev = hist.iloc[i - 1]

            if pd.isna(row['Upper']) or pd.isna(row['Lower']):
                continue

            band_width = float(row['Upper'] - row['Lower'])

            # Volume confirmation: signal requires volume > 1.3× 20-day average
            vol_confirmed = (
                not pd.isna(row['VolMA20'])
                and float(row['VolMA20']) > 0
                and float(row['Volume']) > 1.3 * float(row['VolMA20'])
            )

            # Price crosses below lower band + volume spike → oversold → BUY
            if prev['Close'] >= prev['Lower'] and row['Close'] < row['Lower'] and vol_confirmed:
                raw_score = int(abs(float(row['Lower']) - float(row['Close'])) / band_width * 200) if band_width > 0 else 0
                score = min(100, raw_score)
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                vol_ratio = round(float(row['Volume']) / float(row['VolMA20']), 1)
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'Price crossed below lower Bollinger Band (${row["Lower"]:.2f}) '
                        f'on {vol_ratio}× avg volume — volume-confirmed oversold condition'
                    ),
                })

            # Price crosses above upper band + volume spike → overbought → SELL
            elif prev['Close'] <= prev['Upper'] and row['Close'] > row['Upper'] and vol_confirmed:
                raw_score = int(abs(float(row['Close']) - float(row['Upper'])) / band_width * 200) if band_width > 0 else 0
                score = min(100, raw_score)
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                vol_ratio = round(float(row['Volume']) / float(row['VolMA20']), 1)
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'SELL',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'Price crossed above upper Bollinger Band (${row["Upper"]:.2f}) '
                        f'on {vol_ratio}× avg volume — volume-confirmed overbought condition'
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
