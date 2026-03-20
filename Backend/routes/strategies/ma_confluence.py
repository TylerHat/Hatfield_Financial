import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

mac_bp = Blueprint('ma_confluence', __name__)


def compute_signals(hist_df):
    """Compute MA confluence alignment signals from an OHLCV DataFrame."""
    df = hist_df.copy()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()

    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if any(pd.isna(row[col]) for col in ['MA20', 'MA50', 'MA200']):
            continue
        if any(pd.isna(prev[col]) for col in ['MA20', 'MA50', 'MA200']):
            continue

        close = float(row['Close'])
        ma20 = float(row['MA20'])
        ma50 = float(row['MA50'])
        ma200 = float(row['MA200'])
        prev_close_val = float(prev['Close'])
        prev_ma20_val = float(prev['MA20'])
        prev_ma50_val = float(prev['MA50'])
        prev_ma200_val = float(prev['MA200'])

        bullish_now = close > ma20 and ma20 > ma50 and ma50 > ma200
        bullish_prev = prev_close_val > prev_ma20_val and prev_ma20_val > prev_ma50_val and prev_ma50_val > prev_ma200_val

        bearish_now = close < ma20 and ma20 < ma50 and ma50 < ma200
        bearish_prev = prev_close_val < prev_ma20_val and prev_ma20_val < prev_ma50_val and prev_ma50_val < prev_ma200_val

        if bullish_now and not bullish_prev:
            ma20_50_sep = (ma20 - ma50) / ma50 * 100 if ma50 > 0 else 0
            ma50_200_sep = (ma50 - ma200) / ma200 * 100 if ma200 > 0 else 0
            score = min(100, int((ma20_50_sep + ma50_200_sep) * 10))
            score = max(10, score)
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(close, 2),
                'type': 'BUY',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'MA confluence bullish alignment: price (${close:.2f}) > '
                    f'MA20 (${ma20:.2f}) > MA50 (${ma50:.2f}) > MA200 (${ma200:.2f}) \u2014 '
                    f'all MAs stacked and pointing up'
                ),
            })

        elif bearish_now and not bearish_prev:
            ma20_50_sep = (ma50 - ma20) / ma50 * 100 if ma50 > 0 else 0
            ma50_200_sep = (ma200 - ma50) / ma200 * 100 if ma200 > 0 else 0
            score = min(100, int((ma20_50_sep + ma50_200_sep) * 10))
            score = max(10, score)
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(close, 2),
                'type': 'SELL',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'MA confluence bearish alignment: price (${close:.2f}) < '
                    f'MA20 (${ma20:.2f}) < MA50 (${ma50:.2f}) < MA200 (${ma200:.2f}) \u2014 '
                    f'all MAs stacked and pointing down'
                ),
            })

    return signals


@mac_bp.route('/api/strategy/ma-confluence/<ticker>')
def ma_confluence(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=280)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({
                'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.',
                'signals': []
            }), 404

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
