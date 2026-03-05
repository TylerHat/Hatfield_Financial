import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify
from datetime import datetime, timedelta

bb_bp = Blueprint('bollinger_bands', __name__)


@bb_bp.route('/api/strategy/bollinger-bands/<ticker>')
def bollinger_bands(ticker):
    try:
        end = datetime.today()
        # Extra lookback so rolling window is populated by the time 6-month window starts
        start = end - timedelta(days=182 + 40)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['STD20'] = hist['Close'].rolling(20).std()
        hist['Upper'] = hist['MA20'] + 2 * hist['STD20']
        hist['Lower'] = hist['MA20'] - 2 * hist['STD20']

        # Trim to exact 6-month window after bands are computed
        cutoff = pd.Timestamp(end - timedelta(days=182)).tz_localize('UTC')
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
