import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

rs_bp = Blueprint('relative_strength', __name__)


@rs_bp.route('/api/strategy/relative-strength/<ticker>')
def relative_strength(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        # Extra lookback so the 10-day RS moving average is populated
        fetch_start = user_start - timedelta(days=20)

        stock = yf.Ticker(ticker.upper())
        spy = yf.Ticker('SPY')

        hist = stock.history(start=fetch_start, end=end)
        spy_hist = spy.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

        # Align on common dates
        combined = pd.DataFrame({
            'stock': hist['Close'],
            'spy': spy_hist['Close'],
        }).dropna()

        # Relative strength ratio and its 10-day moving average
        combined['rs'] = combined['stock'] / combined['spy']
        combined['rs_ma'] = combined['rs'].rolling(10).mean()

        # Trim to the user-requested window after indicators are computed
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if combined.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        combined = combined[combined.index >= cutoff]

        signals = []

        for i in range(1, len(combined)):
            row = combined.iloc[i]
            prev = combined.iloc[i - 1]

            if pd.isna(row['rs_ma']) or pd.isna(prev['rs_ma']):
                continue

            # RS crosses above its MA → stock gaining relative strength → BUY
            if prev['rs'] <= prev['rs_ma'] and row['rs'] > row['rs_ma']:
                deviation = abs(float(row['rs']) - float(row['rs_ma'])) / float(row['rs_ma']) if float(row['rs_ma']) > 0 else 0
                score = min(100, int(deviation * 2000))
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': combined.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['stock']), 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'RS vs SPY crossed above its 10-day average '
                        f'(RS ratio: {row["rs"]:.4f}) — stock gaining momentum vs market'
                    ),
                })

            # RS crosses below its MA → stock losing relative strength → SELL
            elif prev['rs'] >= prev['rs_ma'] and row['rs'] < row['rs_ma']:
                deviation = abs(float(row['rs']) - float(row['rs_ma'])) / float(row['rs_ma']) if float(row['rs_ma']) > 0 else 0
                score = min(100, int(deviation * 2000))
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': combined.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['stock']), 2),
                    'type': 'SELL',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'RS vs SPY crossed below its 10-day average '
                        f'(RS ratio: {row["rs"]:.4f}) — stock losing momentum vs market'
                    ),
                })

        return jsonify({'signals': signals})

    except Exception as e:
        return jsonify({'error': str(e), 'signals': []}), 500
