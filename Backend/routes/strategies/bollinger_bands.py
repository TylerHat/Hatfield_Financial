import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

bb_bp = Blueprint('bollinger_bands', __name__)


@bb_bp.route('/api/strategy/bollinger-bands/<ticker>')
def bollinger_bands(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        # Fetch extra days before user's start so the 20-day rolling window is populated
        fetch_start = user_start - timedelta(days=40)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['STD20'] = hist['Close'].rolling(20).std()
        hist['Upper'] = hist['MA20'] + 2 * hist['STD20']
        hist['Lower'] = hist['MA20'] - 2 * hist['STD20']

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

            # Price crosses below lower band → oversold → BUY
            if prev['Close'] >= prev['Lower'] and row['Close'] < row['Lower']:
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'BUY',
                    'reason': (
                        f'Price crossed below lower Bollinger Band '
                        f'(${row["Lower"]:.2f}) — oversold condition'
                    ),
                })

            # Price crosses above upper band → overbought → SELL
            elif prev['Close'] <= prev['Upper'] and row['Close'] > row['Upper']:
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'SELL',
                    'reason': (
                        f'Price crossed above upper Bollinger Band '
                        f'(${row["Upper"]:.2f}) — overbought condition'
                    ),
                })

        return jsonify({'signals': signals})

    except Exception as e:
        return jsonify({'error': str(e), 'signals': []}), 500
