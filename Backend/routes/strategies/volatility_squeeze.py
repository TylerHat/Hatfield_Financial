import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

vs_bp = Blueprint('volatility_squeeze', __name__)


@vs_bp.route('/api/strategy/volatility-squeeze/<ticker>')
def volatility_squeeze(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        # Extra warmup: 120 days needed for 60-day BB width percentile calc
        fetch_start = user_start - timedelta(days=120)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({
                'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.',
                'signals': []
            }), 404

        # Bollinger Bands (20, 2)
        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['STD20'] = hist['Close'].rolling(20).std()
        hist['Upper'] = hist['MA20'] + 2 * hist['STD20']
        hist['Lower'] = hist['MA20'] - 2 * hist['STD20']
        hist['BB_Width'] = hist['Upper'] - hist['Lower']

        # 60-day 20th percentile of BB_Width (squeeze threshold) and median (expansion threshold)
        hist['BB_Width_p20'] = hist['BB_Width'].rolling(60).quantile(0.20)
        hist['BB_Width_median'] = hist['BB_Width'].rolling(60).quantile(0.50)

        # In squeeze: BB_Width < 60-day 20th percentile
        hist['In_Squeeze'] = hist['BB_Width'] < hist['BB_Width_p20']

        # Trim to user-requested window after indicators are computed
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]

        signals = []

        for i in range(1, len(hist)):
            row = hist.iloc[i]
            prev = hist.iloc[i - 1]

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

            # Squeeze release: was in squeeze, now BB_Width expanded above 60-day median
            if was_in_squeeze and bb_width > bb_median:
                # Direction: price above MA20 → BUY, price below MA20 → SELL
                expansion_ratio = bb_width / bb_p20 if bb_p20 > 0 else 1.0
                score = min(100, int((expansion_ratio - 1) * 100))
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'

                if close > ma20:
                    signals.append({
                        'date': hist.index[i].strftime('%Y-%m-%d'),
                        'price': round(close, 2),
                        'type': 'BUY',
                        'score': score,
                        'conviction': conviction,
                        'reason': (
                            f'Volatility squeeze released — BB width expanded to ${bb_width:.2f} '
                            f'({expansion_ratio:.1f}× squeeze level), price ${close:.2f} '
                            f'above MA20 (${ma20:.2f}) — bullish breakout'
                        ),
                    })
                else:
                    signals.append({
                        'date': hist.index[i].strftime('%Y-%m-%d'),
                        'price': round(close, 2),
                        'type': 'SELL',
                        'score': score,
                        'conviction': conviction,
                        'reason': (
                            f'Volatility squeeze released — BB width expanded to ${bb_width:.2f} '
                            f'({expansion_ratio:.1f}× squeeze level), price ${close:.2f} '
                            f'below MA20 (${ma20:.2f}) — bearish breakdown'
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
