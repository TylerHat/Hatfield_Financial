import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify

stock_info_bp = Blueprint('stock_info', __name__)


def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_consolidation(hist, window=20):
    if len(hist) < window * 2:
        return None, 'Insufficient data', ''

    recent = hist['Close'].iloc[-window:]
    older = hist['Close'].iloc[-window * 2:-window]

    recent_range = (recent.max() - recent.min()) / recent.mean()
    older_range = (older.max() - older.min()) / older.mean()

    if recent_range < 0.05:
        status = 'Strong Consolidation'
        detail = f'Price moving in a tight {recent_range:.1%} range over the last {window} days — potential breakout setup'
    elif recent_range < older_range * 0.7:
        status = 'Consolidating'
        detail = f'Price range narrowed from {older_range:.1%} to {recent_range:.1%} — momentum is compressing'
    elif recent_range > older_range * 1.3:
        status = 'Expanding / Trending'
        detail = f'Price range expanded from {older_range:.1%} to {recent_range:.1%} — active trend underway'
    else:
        status = 'Neutral'
        detail = f'Price range of {recent_range:.1%} is similar to prior {window}-day period'

    return round(recent_range * 100, 2), status, detail


@stock_info_bp.route('/api/stock-info/<ticker>')
def get_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        # Use 1 year of daily data for computed indicators regardless of chart date range
        hist = stock.history(period='1y')

        if hist.empty:
            return jsonify({'error': f'No data for {ticker.upper()}'}), 404

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi_series = compute_rsi(hist['Close'])
        current_rsi = None
        if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]):
            current_rsi = round(float(rsi_series.iloc[-1]), 1)

        if current_rsi is None:
            rsi_signal = 'N/A'
        elif current_rsi >= 70:
            rsi_signal = 'Overbought'
        elif current_rsi <= 30:
            rsi_signal = 'Oversold'
        else:
            rsi_signal = 'Neutral'

        # ── Consolidation ─────────────────────────────────────────────────────
        consol_range, consol_status, consol_detail = compute_consolidation(hist)

        # ── Helpers ───────────────────────────────────────────────────────────
        def safe_float(key, decimals=2):
            val = info.get(key)
            if val is None or val == 'N/A':
                return None
            try:
                return round(float(val), decimals)
            except Exception:
                return None

        def fmt_large(val):
            if val is None:
                return None
            if val >= 1e12:
                return f'${val / 1e12:.2f}T'
            if val >= 1e9:
                return f'${val / 1e9:.2f}B'
            if val >= 1e6:
                return f'${val / 1e6:.2f}M'
            return f'${val:,.0f}'

        # ── Valuation assessment ──────────────────────────────────────────────
        pe = safe_float('trailingPE')
        if pe is None:
            valuation = 'N/A'
            val_detail = 'P/E ratio not available (company may not be profitable)'
        elif pe < 0:
            valuation = 'Not Profitable'
            val_detail = 'Negative earnings — P/E is not meaningful'
        elif pe < 12:
            valuation = 'Potentially Undervalued'
            val_detail = f'P/E of {pe:.1f}x is below the historical market average of ~20x'
        elif pe < 20:
            valuation = 'Fairly Valued'
            val_detail = f'P/E of {pe:.1f}x is in line with the historical market average (~15–20x)'
        elif pe < 30:
            valuation = 'Slightly Overvalued'
            val_detail = f'P/E of {pe:.1f}x is above the market average — may reflect growth expectations'
        else:
            valuation = 'Potentially Overvalued'
            val_detail = f'P/E of {pe:.1f}x is significantly above the market average of ~20x'

        # ── 52-week range position ────────────────────────────────────────────
        hi52 = safe_float('fiftyTwoWeekHigh')
        lo52 = safe_float('fiftyTwoWeekLow')
        price = safe_float('currentPrice') or safe_float('regularMarketPrice')

        pct_from_high, pct_from_low, pos_in_range = None, None, None
        if price and hi52 and lo52 and hi52 != lo52:
            pct_from_high = round(((price - hi52) / hi52) * 100, 1)
            pct_from_low = round(((price - lo52) / lo52) * 100, 1)
            pos_in_range = round(((price - lo52) / (hi52 - lo52)) * 100, 0)

        # ── Analyst rec ───────────────────────────────────────────────────────
        rec_key = info.get('recommendationKey') or ''
        analyst_rec = rec_key.replace('_', ' ').title() if rec_key else 'N/A'

        return jsonify({
            'ticker': ticker.upper(),
            'name': info.get('longName') or info.get('shortName', ticker.upper()),
            'sector': info.get('sector') or 'N/A',
            'industry': info.get('industry') or 'N/A',
            'currentPrice': price,
            'marketCap': fmt_large(info.get('marketCap')),
            'trailingPE': pe,
            'forwardPE': safe_float('forwardPE'),
            'priceToBook': safe_float('priceToBook'),
            'priceToSales': safe_float('priceToSalesTrailingTwelveMonths'),
            'beta': safe_float('beta'),
            'dividendYield': safe_float('dividendYield', 4),
            'eps': safe_float('trailingEps'),
            'fiftyTwoWeekHigh': hi52,
            'fiftyTwoWeekLow': lo52,
            'pctFromHigh': pct_from_high,
            'pctFromLow': pct_from_low,
            'positionInRange': pos_in_range,
            'rsi': current_rsi,
            'rsiSignal': rsi_signal,
            'consolidationStatus': consol_status,
            'consolidationDetail': consol_detail,
            'valuation': valuation,
            'valuationDetail': val_detail,
            'analystRecommendation': analyst_rec,
            'targetMeanPrice': safe_float('targetMeanPrice'),
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
