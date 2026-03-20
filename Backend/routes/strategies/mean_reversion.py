import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

mr_bp = Blueprint('mean_reversion', __name__)


def compute_signals(hist_df):
    """Compute mean-reversion signals from an OHLCV DataFrame."""
    df = hist_df.copy()
    df['MA200'] = df['Close'].rolling(200).mean()
    df['High20'] = df['Close'].rolling(20).max()
    df['Drawdown'] = (df['Close'] - df['High20']) / df['High20']

    signals = []
    in_drawdown = False

    for i in range(len(df)):
        row = df.iloc[i]

        if pd.isna(row['Drawdown']):
            continue

        drawdown_pct = float(row['Drawdown'])

        ma200 = row['MA200']
        in_uptrend = not pd.isna(ma200) and float(row['Close']) > float(ma200)

        if not in_drawdown and drawdown_pct <= -0.10 and in_uptrend:
            score = min(100, int(abs(drawdown_pct) * 500))
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'BUY',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'Drawdown of {drawdown_pct:.1%} from 20-day high '
                    f'(${float(row["High20"]):.2f}), price above MA200 '
                    f'(${float(ma200):.2f}) \u2014 trend-confirmed mean reversion entry'
                ),
            })
            in_drawdown = True

        elif in_drawdown and drawdown_pct > -0.03:
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'SELL',
                'score': 55,
                'conviction': 'MEDIUM',
                'reason': (
                    f'Price recovered to within 3% of 20-day high '
                    f'(${float(row["High20"]):.2f}) \u2014 exit mean reversion trade'
                ),
            })
            in_drawdown = False

    return signals


@mr_bp.route('/api/strategy/mean-reversion/<ticker>')
def mean_reversion(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=280)

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
