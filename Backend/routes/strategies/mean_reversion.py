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
        # Extra lookback so the 20-day trailing high is populated
        fetch_start = user_start - timedelta(days=30)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

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

            # Drawdown ≥ 10% from 20-day high → BUY (mean reversion expected)
            if not in_drawdown and drawdown_pct <= -0.10:
                score = min(100, int(abs(drawdown_pct) * 500))
                conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': conviction,
                    'reason': (
                        f'Large drawdown of {drawdown_pct:.1%} from 20-day high '
                        f'(${float(row["High20"]):.2f}) — mean reversion entry'
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
        return jsonify({'error': str(e), 'signals': []}), 500
