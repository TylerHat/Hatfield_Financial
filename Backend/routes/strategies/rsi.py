import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

rsi_bp = Blueprint('rsi', __name__)


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI using exponential smoothing (alpha = 1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))


def compute_signals(hist_df):
    """Compute RSI crossover signals from an OHLCV DataFrame."""
    df = hist_df.copy()
    df['RSI'] = _compute_rsi(df['Close'])

    signals = []
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row['RSI']) or pd.isna(prev['RSI']):
            continue

        rsi = float(row['RSI'])
        prev_rsi = float(prev['RSI'])

        # RSI crosses below 30 → enters oversold → BUY
        if prev_rsi >= 30 and rsi < 30:
            score = min(100, int((30 - rsi) / 30 * 100))
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'BUY',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'RSI entered oversold territory at {rsi:.1f} '
                    f'(crossed below 30) — potential reversal upward'
                ),
            })

        # RSI crosses above 70 → enters overbought → SELL
        elif prev_rsi <= 70 and rsi > 70:
            score = min(100, int((rsi - 70) / 30 * 100))
            conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
            signals.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'price': round(float(row['Close']), 2),
                'type': 'SELL',
                'score': score,
                'conviction': conviction,
                'reason': (
                    f'RSI entered overbought territory at {rsi:.1f} '
                    f'(crossed above 70) — potential reversal downward'
                ),
            })

    return signals


@rsi_bp.route('/api/strategy/rsi/<ticker>')
def rsi_strategy(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=60)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.', 'signals': []}), 404

        # Trim to user window after computing signals on full warmup data
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
