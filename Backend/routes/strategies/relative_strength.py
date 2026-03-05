import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify
from datetime import datetime, timedelta

rs_bp = Blueprint('relative_strength', __name__)


@rs_bp.route('/api/strategy/relative-strength/<ticker>')
def relative_strength(ticker):
    try:
        end = datetime.today()
        start = end - timedelta(days=182 + 20)  # extra for RS rolling window

        stock = yf.Ticker(ticker.upper())
        spy = yf.Ticker('SPY')

        hist = stock.history(start=start, end=end)
        spy_hist = spy.history(start=start, end=end)

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

        # Trim to 6-month window after indicators are computed
        cutoff = pd.Timestamp(end - timedelta(days=182)).tz_localize('UTC')
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
                signals.append({
                    'date': combined.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['stock']), 2),
                    'type': 'BUY',
                    'reason': (
                        f'RS vs SPY crossed above its 10-day average '
                        f'(RS ratio: {row["rs"]:.4f}) — stock gaining momentum vs market'
                    ),
                })

            # RS crosses below its MA → stock losing relative strength → SELL
            elif prev['rs'] >= prev['rs_ma'] and row['rs'] < row['rs_ma']:
                signals.append({
                    'date': combined.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['stock']), 2),
                    'type': 'SELL',
                    'reason': (
                        f'RS vs SPY crossed below its 10-day average '
                        f'(RS ratio: {row["rs"]:.4f}) — stock losing momentum vs market'
                    ),
                })

        return jsonify({'signals': signals})

    except Exception as e:
        return jsonify({'error': str(e), 'signals': []}), 500
