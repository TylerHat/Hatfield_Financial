import pandas as pd
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from data_fetcher import get_ohlcv, get_ticker_info, get_earnings_dates, clear_cache, clear_ticker_cache, PRIORITY_HIGH

stock_data_bp = Blueprint('stock_data', __name__)


@stock_data_bp.route('/api/stock/<ticker>')
def get_stock_data(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)

        hist = get_ohlcv(ticker, start, end, priority=PRIORITY_HIGH)

        if hist is None or hist.empty:
            return jsonify({'error': f'No data found for ticker "{ticker.upper()}". Check the symbol and try again.'}), 404

        # 52-week high/low from ticker info (cached)
        info = get_ticker_info(ticker, priority=PRIORITY_HIGH) or {}
        fifty_two_week_high = info.get('fiftyTwoWeekHigh')
        fifty_two_week_low = info.get('fiftyTwoWeekLow')

        # Earnings dates — past and upcoming (cached)
        earnings_dates_list = []
        cal = get_earnings_dates(ticker, priority=PRIORITY_HIGH)
        if cal is not None and not cal.empty:
            earnings_dates_list = [d.strftime('%Y-%m-%d') for d in cal.index]

        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['MA50'] = hist['Close'].rolling(50).mean()

        # Bollinger Bands (20-period, 2 std dev)
        hist['BB_Upper'] = hist['MA20'] + 2 * hist['Close'].rolling(20).std()
        hist['BB_Lower'] = hist['MA20'] - 2 * hist['Close'].rolling(20).std()

        # Volume moving average (20-day)
        hist['Vol_MA20'] = hist['Volume'].rolling(20).mean()

        # RSI (14) — Wilder's exponential smoothing
        delta = hist['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float('nan'))
        hist['RSI'] = 100 - (100 / (1 + rs))

        # ATR (14) — Average True Range
        high_low = hist['High'] - hist['Low']
        high_prev_close = (hist['High'] - hist['Close'].shift(1)).abs()
        low_prev_close = (hist['Low'] - hist['Close'].shift(1)).abs()
        true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        hist['ATR'] = true_range.ewm(alpha=1 / 14, adjust=False).mean()

        # Stochastic Oscillator (9, 3, 3)
        stoch_period = 9
        low_min = hist['Low'].rolling(stoch_period).min()
        high_max = hist['High'].rolling(stoch_period).max()
        hist['Stoch_K'] = 100 * (hist['Close'] - low_min) / (high_max - low_min).replace(0, float('nan'))
        hist['Stoch_D'] = hist['Stoch_K'].rolling(3).mean()

        # On-Balance Volume (OBV) + 20-day signal line
        obv_direction = hist['Close'].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        hist['OBV'] = (obv_direction * hist['Volume']).cumsum()
        hist['OBV_Signal'] = hist['OBV'].rolling(20).mean()

        ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
        ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal

        def safe_list(series):
            return [None if pd.isna(v) else round(float(v), 4) for v in series]

        data = {
            'dates': hist.index.strftime('%Y-%m-%d').tolist(),
            'close': [None if pd.isna(v) else round(float(v), 2) for v in hist['Close']],
            'volume': [int(v) for v in hist['Volume']],
            'ma20': safe_list(hist['MA20']),
            'ma50': safe_list(hist['MA50']),
            'macd': safe_list(macd_line),
            'macd_signal': safe_list(macd_signal),
            'macd_hist': safe_list(macd_hist),
            'rsi': safe_list(hist['RSI']),
            'bb_upper': safe_list(hist['BB_Upper']),
            'bb_lower': safe_list(hist['BB_Lower']),
            'vol_ma20': safe_list(hist['Vol_MA20']),
            'atr': safe_list(hist['ATR']),
            'stoch_k': safe_list(hist['Stoch_K']),
            'stoch_d': safe_list(hist['Stoch_D']),
            'obv': [None if pd.isna(v) else int(v) for v in hist['OBV']],
            'obv_signal': safe_list(hist['OBV_Signal']),
            'fifty_two_week_high': round(float(fifty_two_week_high), 2) if fifty_two_week_high else None,
            'fifty_two_week_low': round(float(fifty_two_week_low), 2) if fifty_two_week_low else None,
            'earnings_dates': earnings_dates_list,
        }

        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@stock_data_bp.route('/api/stock/<ticker>', methods=['POST'])
def refresh_stock_data(ticker):
    """Handle POST requests to refresh stock chart data."""
    try:
        ticker = ticker.upper()
        # Clear cached OHLCV data for this ticker
        clear_cache(f'ohlcv:{ticker}')
        clear_cache(f'ohlcv_period:{ticker}')
        # Clear the cached yf.Ticker object for fresh data
        clear_ticker_cache(ticker)

        # Fetch fresh data
        end_str = request.args.get('end')
        start_str = request.args.get('start')
        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)

        return get_stock_data(ticker)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
