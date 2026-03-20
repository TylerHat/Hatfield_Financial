import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

rs_bp = Blueprint('relative_strength', __name__)


def compute_signals(hist_df, spy_close):
    """Compute relative strength signals from stock OHLCV and SPY close series."""
    combined = pd.DataFrame({
        'stock': hist_df['Close'],
        'spy': spy_close,
    }).dropna()

    combined['rs'] = combined['stock'] / combined['spy']
    combined['rs_ma'] = combined['rs'].rolling(10).mean()

    signals = []

    for i in range(1, len(combined)):
        row = combined.iloc[i]
        prev = combined.iloc[i - 1]

        if pd.isna(row['rs_ma']) or pd.isna(prev['rs_ma']):
            continue

        if prev['rs'] <= prev['rs_ma'] and row['rs'] > row['rs_ma']:
            deviation = abs(float(row['rs']) - float(row['rs_ma'])) / float(row['rs_ma']) if float(row['rs_ma']) > 0 else 0
            score = min(100, int(deviation * 2000))
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            signals.append({
                'date': combined.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['stock']), 2),
                'type': 'BUY',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'RS vs SPY crossed above its 10-day average '
                    f'(RS ratio: {row["rs"]:.4f}) \u2014 stock gaining momentum vs market'
                ),
            })

        elif prev['rs'] >= prev['rs_ma'] and row['rs'] < row['rs_ma']:
            deviation = abs(float(row['rs']) - float(row['rs_ma'])) / float(row['rs_ma']) if float(row['rs_ma']) > 0 else 0
            score = min(100, int(deviation * 2000))
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            signals.append({
                'date': combined.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['stock']), 2),
                'type': 'SELL',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'RS vs SPY crossed below its 10-day average '
                    f'(RS ratio: {row["rs"]:.4f}) \u2014 stock losing momentum vs market'
                ),
            })

    return signals


@rs_bp.route('/api/strategy/relative-strength/<ticker>')
def relative_strength(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=20)

        stock = yf.Ticker(ticker.upper())
        spy = yf.Ticker('SPY')

        hist = stock.history(start=fetch_start, end=end)
        spy_hist = spy.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.', 'signals': []}), 404

        all_signals = compute_signals(hist, spy_hist['Close'])
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
