import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

macd_bp = Blueprint('macd_crossover', __name__)


def compute_signals(hist_df):
    """Compute MACD crossover signals from an OHLCV DataFrame."""
    df = hist_df.copy()
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']

    recent_hist_range = df['Hist'].abs().rolling(30).mean()
    df['NormHist'] = df['Hist'].abs() / recent_hist_range.replace(0, float('nan'))

    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row['MACD']) or pd.isna(row['Signal']) or pd.isna(prev['MACD']) or pd.isna(prev['Signal']):
            continue

        norm = float(row['NormHist']) if not pd.isna(row['NormHist']) else 0.5
        score = min(100, int(norm * 60))
        conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'

        if prev['MACD'] <= prev['Signal'] and row['MACD'] > row['Signal']:
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'BUY',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'MACD ({row["MACD"]:.4f}) crossed above Signal ({row["Signal"]:.4f}) '
                    f'\u2014 bullish momentum shift'
                ),
            })

        elif prev['MACD'] >= prev['Signal'] and row['MACD'] < row['Signal']:
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'SELL',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'MACD ({row["MACD"]:.4f}) crossed below Signal ({row["Signal"]:.4f}) '
                    f'\u2014 bearish momentum shift'
                ),
            })

    return signals


@macd_bp.route('/api/strategy/macd-crossover/<ticker>')
def macd_crossover(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=90)

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
