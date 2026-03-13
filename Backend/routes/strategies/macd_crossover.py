import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

macd_bp = Blueprint('macd_crossover', __name__)


@macd_bp.route('/api/strategy/macd-crossover/<ticker>')
def macd_crossover(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        # Extra warmup so the 26-period EMA and 9-period signal are stable
        fetch_start = user_start - timedelta(days=90)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.', 'signals': []}), 404

        # MACD (12, 26, 9)
        ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
        ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
        hist['MACD'] = ema12 - ema26
        hist['Signal'] = hist['MACD'].ewm(span=9, adjust=False).mean()
        hist['Hist'] = hist['MACD'] - hist['Signal']

        # Score: strength of crossover relative to recent histogram range
        recent_hist_range = hist['Hist'].abs().rolling(30).mean()
        hist['NormHist'] = hist['Hist'].abs() / recent_hist_range.replace(0, float('nan'))

        # Trim to the user-requested window after indicators are computed
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]

        signals = []

        for i in range(1, len(hist)):
            row = hist.iloc[i]
            prev = hist.iloc[i - 1]

            if pd.isna(row['MACD']) or pd.isna(row['Signal']) or pd.isna(prev['MACD']) or pd.isna(prev['Signal']):
                continue

            norm = float(row['NormHist']) if not pd.isna(row['NormHist']) else 0.5
            score = min(100, int(norm * 60))
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'

            # MACD crosses above Signal line → bullish momentum → BUY
            if prev['MACD'] <= prev['Signal'] and row['MACD'] > row['Signal']:
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'MACD ({row["MACD"]:.4f}) crossed above Signal ({row["Signal"]:.4f}) '
                        f'— bullish momentum shift'
                    ),
                })

            # MACD crosses below Signal line → bearish momentum → SELL
            elif prev['MACD'] >= prev['Signal'] and row['MACD'] < row['Signal']:
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'SELL',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'MACD ({row["MACD"]:.4f}) crossed below Signal ({row["Signal"]:.4f}) '
                        f'— bearish momentum shift'
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
