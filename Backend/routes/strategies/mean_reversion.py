import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify
from datetime import datetime, timedelta

mr_bp = Blueprint('mean_reversion', __name__)


@mr_bp.route('/api/strategy/mean-reversion/<ticker>')
def mean_reversion(ticker):
    try:
        end = datetime.today()
        start = end - timedelta(days=182 + 30)  # extra for 20-day trailing high

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

        # 20-day trailing high and drawdown from it
        hist['High20'] = hist['Close'].rolling(20).max()
        hist['Drawdown'] = (hist['Close'] - hist['High20']) / hist['High20']

        # Trim to exact 6-month window
        cutoff = pd.Timestamp(end - timedelta(days=182)).tz_localize('UTC')
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
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(row['Close']), 2),
                    'type': 'BUY',
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
                    'reason': (
                        f'Price recovered to within 3% of 20-day high '
                        f'(${float(row["High20"]):.2f}) — exit mean reversion trade'
                    ),
                })
                in_drawdown = False

        return jsonify({'signals': signals})

    except Exception as e:
        return jsonify({'error': str(e), 'signals': []}), 500
