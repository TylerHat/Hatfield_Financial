import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

stock_data_bp = Blueprint('stock_data', __name__)


@stock_data_bp.route('/api/stock/<ticker>')
def get_stock_data(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=start, end=end)

        if hist.empty:
            return jsonify({'error': f'No data found for ticker "{ticker.upper()}". Check the symbol and try again.'}), 404

        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['MA50'] = hist['Close'].rolling(50).mean()

        def safe_list(series):
            return [None if pd.isna(v) else round(float(v), 2) for v in series]

        data = {
            'dates': hist.index.strftime('%Y-%m-%d').tolist(),
            'close': safe_list(hist['Close']),
            'volume': [int(v) for v in hist['Volume']],
            'ma20': safe_list(hist['MA20']),
            'ma50': safe_list(hist['MA50']),
        }

        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
