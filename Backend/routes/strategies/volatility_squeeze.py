import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

vs_bp = Blueprint('volatility_squeeze', __name__)


def compute_signals(hist_df):
    """Compute volatility squeeze release signals from an OHLCV DataFrame."""
    df = hist_df.copy()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['STD20'] = df['Close'].rolling(20).std()
    df['Upper'] = df['MA20'] + 2 * df['STD20']
    df['Lower'] = df['MA20'] - 2 * df['STD20']
    df['BB_Width'] = df['Upper'] - df['Lower']

    df['BB_Width_p20'] = df['BB_Width'].rolling(60).quantile(0.20)
    df['BB_Width_median'] = df['BB_Width'].rolling(60).quantile(0.50)
    df['In_Squeeze'] = df['BB_Width'] < df['BB_Width_p20']

    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row['BB_Width_p20']) or pd.isna(row['BB_Width_median']) or pd.isna(row['MA20']):
            continue
        if pd.isna(prev['In_Squeeze']):
            continue

        was_in_squeeze = bool(prev['In_Squeeze'])
        bb_width = float(row['BB_Width'])
        bb_median = float(row['BB_Width_median'])
        bb_p20 = float(row['BB_Width_p20'])
        ma20 = float(row['MA20'])
        close = float(row['Close'])

        if was_in_squeeze and bb_width > bb_median:
            expansion_ratio = bb_width / bb_p20 if bb_p20 > 0 else 1.0
            score = min(100, int((expansion_ratio - 1) * 100))
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'

            if close > ma20:
                signals.append({
                    'date': df.index[i].strftime('%Y-%m-%d'),
                    'price': round(close, 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'Volatility squeeze released \u2014 BB width expanded to ${bb_width:.2f} '
                        f'({expansion_ratio:.1f}\u00d7 squeeze level), price ${close:.2f} '
                        f'above MA20 (${ma20:.2f}) \u2014 bullish breakout'
                    ),
                })
            else:
                signals.append({
                    'date': df.index[i].strftime('%Y-%m-%d'),
                    'price': round(close, 2),
                    'type': 'SELL',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'Volatility squeeze released \u2014 BB width expanded to ${bb_width:.2f} '
                        f'({expansion_ratio:.1f}\u00d7 squeeze level), price ${close:.2f} '
                        f'below MA20 (${ma20:.2f}) \u2014 bearish breakdown'
                    ),
                })

    return signals


@vs_bp.route('/api/strategy/volatility-squeeze/<ticker>')
def volatility_squeeze(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=120)

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
