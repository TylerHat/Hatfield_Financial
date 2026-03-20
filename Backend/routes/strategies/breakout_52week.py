import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

bk_bp = Blueprint('breakout_52week', __name__)


def compute_signals(hist_df):
    """Compute 52-week breakout/breakdown signals from an OHLCV DataFrame."""
    df = hist_df.copy()
    df['High52'] = df['Close'].shift(1).rolling(252).max()
    df['Low52'] = df['Close'].shift(1).rolling(252).min()
    df['VolMA20'] = df['Volume'].rolling(20).mean()

    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row['High52']) or pd.isna(row['Low52']) or pd.isna(row['VolMA20']):
            continue

        close = float(row['Close'])
        prev_close = float(prev['Close'])
        high52 = float(row['High52'])
        low52 = float(row['Low52'])
        vol = float(row['Volume'])
        vol_ma = float(row['VolMA20'])

        vol_ratio = vol / vol_ma if vol_ma > 0 else 0
        vol_confirmed = vol_ratio >= 1.2

        if close > high52 and prev_close <= float(prev['High52']) if not pd.isna(prev['High52']) else False:
            if vol_confirmed:
                breakout_pct = (close - high52) / high52 * 100 if high52 > 0 else 0
                score = min(100, int(breakout_pct * 20 + (vol_ratio - 1.2) * 30))
                score = max(10, score)
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': df.index[i].strftime('%Y-%m-%d'),
                    'price': round(close, 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'52-week high breakout at ${close:.2f} (above ${high52:.2f}) '
                        f'on {vol_ratio:.1f}\u00d7 average volume \u2014 momentum breakout confirmed'
                    ),
                })

        elif close < low52 and prev_close >= float(prev['Low52']) if not pd.isna(prev['Low52']) else False:
            if vol_confirmed:
                breakdown_pct = (low52 - close) / low52 * 100 if low52 > 0 else 0
                score = min(100, int(breakdown_pct * 20 + (vol_ratio - 1.2) * 30))
                score = max(10, score)
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': df.index[i].strftime('%Y-%m-%d'),
                    'price': round(close, 2),
                    'type': 'SELL',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'52-week low breakdown at ${close:.2f} (below ${low52:.2f}) '
                        f'on {vol_ratio:.1f}\u00d7 average volume \u2014 bearish breakdown confirmed'
                    ),
                })

    return signals


@bk_bp.route('/api/strategy/52-week-breakout/<ticker>')
def breakout_52week(ticker):
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
