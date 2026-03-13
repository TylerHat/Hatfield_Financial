import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

mr_bp = Blueprint('mean_reversion', __name__)


@mr_bp.route('/api/strategy/mean-reversion/<ticker>')
def mean_reversion(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        # Extra lookback for MA200 trend filter (200 trading days ≈ 280 calendar days)
        fetch_start = user_start - timedelta(days=280)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}". Verify the ticker symbol and try again.', 'signals': []}), 404

        # 200-day MA trend filter — only buy dips in uptrends
        hist['MA200'] = hist['Close'].rolling(200).mean()
        # 20-day trailing high and drawdown from it
        hist['High20'] = hist['Close'].rolling(20).max()
        hist['Drawdown'] = (hist['Close'] - hist['High20']) / hist['High20']

        # Trim to the user-requested window
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]

        signals = []
        in_drawdown = False

        for i in range(len(hist)):
            row = hist.iloc[i]

            if pd.isna(row['Drawdown']):
                continue

            drawdown_pct = float(row['Drawdown'])

            # MA200 trend filter — skip BUY signals in downtrends
            ma200 = row.get('MA200') if hasattr(row, 'get') else row['MA200']
            in_uptrend = not pd.isna(ma200) and float(row['Close']) > float(ma200)

            # Drawdown ≥ 10% from 20-day high + price above MA200 → BUY
            if not in_drawdown and drawdown_pct <= -0.10 and in_uptrend:
                score = min(100, int(abs(drawdown_pct) * 500))
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'Drawdown of {drawdown_pct:.1%} from 20-day high '
                        f'(${float(row["High20"]):.2f}), price above MA200 '
                        f'(${float(ma200):.2f}) — trend-confirmed mean reversion entry'
                    ),
                })
                in_drawdown = True

            # Recovery to within 3% of 20-day high → SELL / take profit
            elif in_drawdown and drawdown_pct > -0.03:
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'SELL',
                    'score': 55,
                    'conviction': 'MEDIUM',
                    'reason': (
                        f'Price recovered to within 3% of 20-day high '
                        f'(${float(row["High20"]):.2f}) — exit mean reversion trade'
                    ),
                })
                in_drawdown = False

        return jsonify({'signals': signals})

    except Exception as e:
        msg = str(e)
        if 'rate' in msg.lower() or '429' in msg:
            msg = 'Yahoo Finance rate limit reached. Wait a moment and try again.'
        elif 'connection' in msg.lower() or 'timeout' in msg.lower():
            msg = 'Could not reach Yahoo Finance. Check your network connection.'
        return jsonify({'error': msg, 'signals': []}), 500
