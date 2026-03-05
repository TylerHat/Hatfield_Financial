import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify
from datetime import datetime, timedelta

ped_bp = Blueprint('post_earnings_drift', __name__)


@ped_bp.route('/api/strategy/post-earnings-drift/<ticker>')
def post_earnings_drift(ticker):
    try:
        end = datetime.today()
        start = end - timedelta(days=182)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

        # Attempt to retrieve earnings dates
        try:
            earnings = stock.earnings_dates
        except Exception:
            earnings = None

        signals = []

        if earnings is not None and not earnings.empty:
            # Normalize timezone for comparison
            hist_tz = hist.index.tz
            if hist_tz is not None:
                start_ts = pd.Timestamp(start).tz_localize(str(hist_tz))
                end_ts = pd.Timestamp(end).tz_localize(str(hist_tz))
            else:
                start_ts = pd.Timestamp(start)
                end_ts = pd.Timestamp(end)

            # Align earnings timezone to hist
            if earnings.index.tz is not None and hist_tz is None:
                earnings.index = earnings.index.tz_localize(None)
            elif earnings.index.tz is None and hist_tz is not None:
                earnings.index = earnings.index.tz_localize(str(hist_tz))

            earnings_in_range = earnings[
                (earnings.index >= start_ts) & (earnings.index <= end_ts)
            ]

            for earn_date in earnings_in_range.index:
                # Days in hist after the earnings date
                post = hist[hist.index > earn_date]
                pre = hist[hist.index <= earn_date]

                if len(post) < 2 or pre.empty:
                    continue

                pre_close = float(pre.iloc[-1]['Close'])
                day1_close = float(post.iloc[0]['Close'])
                day2_close = float(post.iloc[1]['Close'])
                earn_str = earn_date.strftime('%Y-%m-%d')

                # Upward drift: day1 and day2 both above pre-earnings close
                if day1_close > pre_close and day2_close > day1_close:
                    signals.append({
                        'date': post.index[0].strftime('%Y-%m-%d'),
                        'price': round(day1_close, 2),
                        'type': 'BUY',
                        'reason': (
                            f'Post-earnings upward drift detected '
                            f'(earnings: {earn_str}, +{((day1_close/pre_close)-1)*100:.1f}% day 1)'
                        ),
                    })

                # Downward drift: day1 below pre-earnings close and continuing down
                elif day1_close < pre_close and day2_close < day1_close:
                    signals.append({
                        'date': post.index[0].strftime('%Y-%m-%d'),
                        'price': round(day1_close, 2),
                        'type': 'SELL',
                        'reason': (
                            f'Post-earnings downward drift detected '
                            f'(earnings: {earn_str}, {((day1_close/pre_close)-1)*100:.1f}% day 1)'
                        ),
                    })

        return jsonify({'signals': signals})

    except Exception as e:
        return jsonify({'error': str(e), 'signals': []}), 500
