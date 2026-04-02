import pandas as pd
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from data_fetcher import get_ohlcv

bk_bp = Blueprint('breakout_52week', __name__)


@bk_bp.route('/api/strategy/52-week-breakout/<ticker>')
def breakout_52week(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)

        hist = get_ohlcv(ticker, user_start, end)

        if hist is None or hist.empty:
            return jsonify({
                'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.',
                'signals': []
            }), 404

        # Rolling 252-day high and low (52-week)
        # Use shift(1) so today's close doesn't influence today's breakout threshold
        hist['High52'] = hist['Close'].shift(1).rolling(252).max()
        hist['Low52'] = hist['Close'].shift(1).rolling(252).min()

        # 20-day average volume for confirmation
        hist['VolMA20'] = hist['Volume'].rolling(20).mean()

        # Trim to user-requested window after indicators are computed
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]

        signals = []

        for i in range(1, len(hist)):
            row = hist.iloc[i]
            prev = hist.iloc[i - 1]

            if pd.isna(row['High52']) or pd.isna(row['Low52']) or pd.isna(row['VolMA20']):
                continue

            close = float(row['Close'])
            prev_close = float(prev['Close'])
            high52 = float(row['High52'])
            low52 = float(row['Low52'])
            vol = float(row['Volume'])
            vol_ma = float(row['VolMA20'])

            # Volume confirmation: > 1.2× 20-day average
            vol_ratio = vol / vol_ma if vol_ma > 0 else 0
            vol_confirmed = vol_ratio >= 1.2

            # BUY: close breaks above the rolling 52-week high on above-average volume
            if close > high52 and prev_close <= float(prev['High52']) if not pd.isna(prev['High52']) else False:
                if vol_confirmed:
                    breakout_pct = (close - high52) / high52 * 100 if high52 > 0 else 0
                    score = min(100, int(breakout_pct * 20 + (vol_ratio - 1.2) * 30))
                    score = max(10, score)
                    conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                    signals.append({
                        'date': hist.index[i].strftime('%Y-%m-%d'),
                        'price': round(close, 2),
                        'type': 'BUY',
                        'score': score,
                        'conviction': conviction,
                        'reason': (
                            f'52-week high breakout at ${close:.2f} (above ${high52:.2f}) '
                            f'on {vol_ratio:.1f}× average volume — momentum breakout confirmed'
                        ),
                    })

            # SELL: close breaks below the rolling 52-week low on above-average volume
            elif close < low52 and prev_close >= float(prev['Low52']) if not pd.isna(prev['Low52']) else False:
                if vol_confirmed:
                    breakdown_pct = (low52 - close) / low52 * 100 if low52 > 0 else 0
                    score = min(100, int(breakdown_pct * 20 + (vol_ratio - 1.2) * 30))
                    score = max(10, score)
                    conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                    signals.append({
                        'date': hist.index[i].strftime('%Y-%m-%d'),
                        'price': round(close, 2),
                        'type': 'SELL',
                        'score': score,
                        'conviction': conviction,
                        'reason': (
                            f'52-week low breakdown at ${close:.2f} (below ${low52:.2f}) '
                            f'on {vol_ratio:.1f}× average volume — bearish breakdown confirmed'
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
