import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

bb_bp = Blueprint('bollinger_bands', __name__)


def compute_signals(hist_df):
    """Compute Bollinger Band crossover signals from an OHLCV DataFrame."""
    df = hist_df.copy()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['STD20'] = df['Close'].rolling(20).std()
    df['Upper'] = df['MA20'] + 2 * df['STD20']
    df['Lower'] = df['MA20'] - 2 * df['STD20']
    df['VolMA20'] = df['Volume'].rolling(20).mean()

    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row['Upper']) or pd.isna(row['Lower']):
            continue

        band_width = float(row['Upper'] - row['Lower'])

        vol_confirmed = (
            not pd.isna(row['VolMA20'])
            and float(row['VolMA20']) > 0
            and float(row['Volume']) > 1.3 * float(row['VolMA20'])
        )

        if prev['Close'] >= prev['Lower'] and row['Close'] < row['Lower'] and vol_confirmed:
            raw_score = int(abs(float(row['Lower']) - float(row['Close'])) / band_width * 200) if band_width > 0 else 0
            score = min(100, raw_score)
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            vol_ratio = round(float(row['Volume']) / float(row['VolMA20']), 1)
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'BUY',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'Price crossed below lower Bollinger Band (${row["Lower"]:.2f}) '
                    f'on {vol_ratio}\u00d7 avg volume \u2014 volume-confirmed oversold condition'
                ),
            })

        elif prev['Close'] <= prev['Upper'] and row['Close'] > row['Upper'] and vol_confirmed:
            raw_score = int(abs(float(row['Close']) - float(row['Upper'])) / band_width * 200) if band_width > 0 else 0
            score = min(100, raw_score)
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            vol_ratio = round(float(row['Volume']) / float(row['VolMA20']), 1)
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'SELL',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'Price crossed above upper Bollinger Band (${row["Upper"]:.2f}) '
                    f'on {vol_ratio}\u00d7 avg volume \u2014 volume-confirmed overbought condition'
                ),
            })

    return signals


@bb_bp.route('/api/strategy/bollinger-bands/<ticker>')
def bollinger_bands(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=40)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.', 'signals': []}), 404

        all_signals = compute_signals(hist)
        cutoff = user_start.strftime('%Y-%m-%d')
        signals = [s for s in all_signals if s['date'] >= cutoff]

        return jsonify({'signals': signals})

    except Exception as e:
        msg = str(e)
        if 'rate' in msg.lower() or '429' in msg:
            msg = 'Yahoo Finance rate limit reached. Wait a moment and try again.'
        elif 'connection' in msg.lower() or 'timeout' in msg.lower():
            msg = 'Could not reach Yahoo Finance. Check your network connection.'
        return jsonify({'error': msg, 'signals': []}), 500
