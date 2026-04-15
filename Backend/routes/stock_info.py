import math
import logging
import pandas as pd
from datetime import datetime, date, timedelta
from flask import Blueprint, jsonify, request

from data_fetcher import get_ticker_info, get_spy_period, get_ohlcv, get_earnings_dates as cached_get_earnings_dates, clear_cache, clear_ticker_cache, PRIORITY_HIGH

logger = logging.getLogger(__name__)

stock_info_bp = Blueprint('stock_info', __name__)
logger.info(f'stock_info blueprint created: {stock_info_bp}')


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


@stock_info_bp.route('/api/stock-info/<ticker>', methods=['POST'])
def refresh_stock_info_post(ticker):
    """Handle POST requests to refresh stock data."""
    try:
        ticker = ticker.upper()
        logger.info(f'Refreshing stock data for {ticker}')
        # Clear cached data for this specific ticker
        clear_cache(f'info:{ticker}')
        clear_cache(f'ohlcv:{ticker}')
        clear_cache(f'ohlcv_period:{ticker}')
        clear_cache(f'analyst:{ticker}')
        clear_cache(f'earnings:{ticker}')
        # Clear the cached yf.Ticker object so yfinance fetches fresh data
        # Critical for 24/7 assets like crypto where Ticker.info holds stale data
        clear_ticker_cache(ticker)
        logger.info(f'Cache cleared for {ticker}')
        # Fetch and return fresh data
        return get_stock_info(ticker)
    except Exception as e:
        logger.error(f'Error refreshing {ticker}: {type(e).__name__}: {str(e)}', exc_info=True)
        return jsonify({'error': f'{type(e).__name__}: {str(e)}'}), 500


@stock_info_bp.route('/api/stock-info/<ticker>')
def get_stock_info(ticker):
    try:
        info = get_ticker_info(ticker, priority=PRIORITY_HIGH)
        if not info:
            return jsonify({'error': f'No data for {ticker.upper()}'}), 404

        # Use 1 year of daily data for computed indicators regardless of chart date range
        end_dt = datetime.today()
        start_dt = end_dt - timedelta(days=365)
        hist = get_ohlcv(ticker, start_dt, end_dt, priority=PRIORITY_HIGH)

        if hist is None or hist.empty:
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

        # ── MACD ──────────────────────────────────────────────────────────────
        ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
        ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_sig = macd.ewm(span=9, adjust=False).mean()
        macd_val = round(float(macd.iloc[-1]), 4)
        signal_val = round(float(macd_sig.iloc[-1]), 4)
        prev_macd = float(macd.iloc[-2])
        prev_sig = float(macd_sig.iloc[-2])
        if prev_macd <= prev_sig and macd_val > signal_val:
            macd_status = 'BULLISH CROSSOVER'
        elif prev_macd >= prev_sig and macd_val < signal_val:
            macd_status = 'BEARISH CROSSOVER'
        elif macd_val > signal_val:
            macd_status = 'BULLISH'
        else:
            macd_status = 'BEARISH'
        macd_momentum = 'STRONG MOMENTUM' if abs(macd_val - signal_val) > 0.5 else 'WEAK MOMENTUM'

        # ── Volatility (ATR 14-day) ────────────────────────────────────────────
        high_low = hist['High'] - hist['Low']
        high_pc = (hist['High'] - hist['Close'].shift(1)).abs()
        low_pc = (hist['Low'] - hist['Close'].shift(1)).abs()
        tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        atr_val = float(atr.iloc[-1])
        atr_avg = float(atr.mean())
        # Handle NaN values (can occur with certain assets like crypto)
        if pd.isna(atr_val) or pd.isna(atr_avg) or atr_avg <= 0:
            vol_ratio = None
        else:
            vol_ratio = round(atr_val / atr_avg, 2)
        if vol_ratio is None:
            volatility_status = None
        elif vol_ratio > 1.5:
            volatility_status = 'HIGH Volatility'
        elif vol_ratio < 0.7:
            volatility_status = 'LOW Volatility'
        else:
            volatility_status = 'Normal Volatility'

        # ── Volume ────────────────────────────────────────────────────────────
        avg_volume = float(hist['Volume'].rolling(20).mean().iloc[-1])
        curr_volume = float(hist['Volume'].iloc[-1])
        vol_relative = round(curr_volume / avg_volume * 100) if avg_volume > 0 else 100
        recent_avg = float(hist['Volume'].iloc[-5:].mean())
        volume_trend = '↗ Increasing' if curr_volume > recent_avg else '↘ Decreasing'
        if vol_relative > 150:
            volume_status = 'HIGH Volume'
        elif vol_relative < 50:
            volume_status = 'LOW Volume'
        else:
            volume_status = 'Normal Volume'

        # ── Trend Alignment (MA20 / MA50 / MA200) ────────────────────────────
        ma20 = hist['Close'].rolling(20).mean()
        ma50 = hist['Close'].rolling(50).mean()
        ma200 = hist['Close'].rolling(200).mean()

        trend_alignment = None
        trend_detail = ''
        current_close = float(hist['Close'].iloc[-1])
        if len(hist) >= 200 and not pd.isna(ma200.iloc[-1]):
            m20, m50, m200 = float(ma20.iloc[-1]), float(ma50.iloc[-1]), float(ma200.iloc[-1])
            if current_close > m20 > m50 > m200:
                trend_alignment = 'Strong Uptrend'
                trend_detail = f'Price (${current_close:.2f}) > MA20 (${m20:.2f}) > MA50 (${m50:.2f}) > MA200 (${m200:.2f})'
            elif current_close < m20 < m50 < m200:
                trend_alignment = 'Strong Downtrend'
                trend_detail = f'Price (${current_close:.2f}) < MA20 (${m20:.2f}) < MA50 (${m50:.2f}) < MA200 (${m200:.2f})'
            elif current_close > m200:
                trend_alignment = 'Bullish (Mixed)'
                trend_detail = f'Price above MA200 but MAs not fully aligned — mixed signals'
            else:
                trend_alignment = 'Bearish (Mixed)'
                trend_detail = f'Price below MA200 — overall trend is bearish despite mixed MA alignment'
        elif len(hist) >= 50 and not pd.isna(ma50.iloc[-1]):
            m20, m50 = float(ma20.iloc[-1]), float(ma50.iloc[-1])
            if current_close > m20 > m50:
                trend_alignment = 'Bullish (Short-term)'
                trend_detail = f'Price > MA20 > MA50 (MA200 not available — less than 200 days of data)'
            else:
                trend_alignment = 'Bearish (Short-term)'
                trend_detail = f'Short-term trend weak: MA20/MA50 not aligned bullishly'

        # ── Earnings Proximity ───────────────────────────────────────────────
        earnings_date_str = None
        try:
            ed_df = cached_get_earnings_dates(ticker, limit=4, priority=PRIORITY_HIGH)
            if ed_df is not None and not ed_df.empty:
                today_ts = pd.Timestamp(date.today())
                if ed_df.index.tz is not None:
                    today_ts = today_ts.tz_localize(ed_df.index.tz)
                future = ed_df[ed_df.index >= today_ts]
                if not future.empty:
                    earnings_date_str = future.index[-1].strftime('%Y-%m-%d')
                else:
                    earnings_date_str = ed_df.index[0].strftime('%Y-%m-%d')
        except Exception:
            pass

        earnings_proximity = None
        earnings_proximity_days = None
        earnings_warning = False
        if earnings_date_str:
            try:
                earn_dt = datetime.strptime(earnings_date_str, '%Y-%m-%d').date()
                today = date.today()
                days_until = (earn_dt - today).days
                earnings_proximity_days = days_until
                if days_until < 0:
                    earnings_proximity = f'Reported {abs(days_until)} days ago'
                elif days_until == 0:
                    earnings_proximity = 'Earnings TODAY'
                    earnings_warning = True
                elif days_until <= 14:
                    earnings_proximity = f'{days_until} days away'
                    earnings_warning = True
                else:
                    earnings_proximity = f'{days_until} days away'
            except Exception:
                pass

        # ── Relative Strength vs SPY ─────────────────────────────────────────
        rel_strength_data = {}
        try:
            spy_hist = get_spy_period('3mo', priority=PRIORITY_HIGH)
            if spy_hist is not None and not spy_hist.empty and len(hist) >= 63 and len(spy_hist) >= 63:
                stock_1m = (float(hist['Close'].iloc[-1]) / float(hist['Close'].iloc[-22]) - 1) * 100
                spy_1m = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-22]) - 1) * 100
                stock_3m = (float(hist['Close'].iloc[-1]) / float(hist['Close'].iloc[-63]) - 1) * 100
                spy_3m = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-63]) - 1) * 100
                rel_strength_data = {
                    'relStrength1M': round(stock_1m - spy_1m, 2),
                    'relStrength3M': round(stock_3m - spy_3m, 2),
                    'stock1MReturn': round(stock_1m, 2),
                    'spy1MReturn': round(spy_1m, 2),
                    'stock3MReturn': round(stock_3m, 2),
                    'spy3MReturn': round(spy_3m, 2),
                }
        except Exception:
            pass

        # ── Dividend Health ──────────────────────────────────────────────────
        # Computed after safe_float is defined, added to response below

        # ── Helpers ───────────────────────────────────────────────────────────
        def safe_float(key, decimals=2):
            val = info.get(key)
            if val is None or val == 'N/A':
                return None
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return None
                return round(f, decimals)
            except Exception:
                return None

        def fmt_large(val):
            if val is None:
                return None
            sign = '-' if val < 0 else ''
            v = abs(val)
            if v >= 1e12:
                return f'{sign}${v / 1e12:.2f}T'
            if v >= 1e9:
                return f'{sign}${v / 1e9:.2f}B'
            if v >= 1e6:
                return f'{sign}${v / 1e6:.2f}M'
            return f'{sign}${v:,.0f}'

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

        # ── Day change (open → current price) ────────────────────────────────
        price = safe_float('currentPrice') or safe_float('regularMarketPrice')
        open_price = float(hist['Open'].iloc[-1]) if not hist.empty else None
        day_change_pct = None
        if price and open_price and open_price > 0:
            day_change_pct = round(((price - open_price) / open_price) * 100, 2)

        # ── 52-week range position ────────────────────────────────────────────
        hi52 = safe_float('fiftyTwoWeekHigh')
        lo52 = safe_float('fiftyTwoWeekLow')

        pct_from_high, pct_from_low, pos_in_range = None, None, None
        if hi52 and lo52 and price and hi52 != lo52:
            pct_from_high = round(((price - hi52) / hi52) * 100, 1)
            pct_from_low = round(((price - lo52) / lo52) * 100, 1)
            pos_in_range = round(((price - lo52) / (hi52 - lo52)) * 100, 0)

        # ── Analyst rec ───────────────────────────────────────────────────────
        rec_key = info.get('recommendationKey') or ''
        analyst_rec = rec_key.replace('_', ' ').title() if rec_key else 'N/A'

        # ── Forward P/E (with fallback computation) ─────────────────────────
        forward_pe = safe_float('forwardPE')
        if forward_pe is None and price:
            forward_eps = safe_float('forwardEps')
            if forward_eps and forward_eps > 0:
                forward_pe = round(price / forward_eps, 2)

        # ── PEG Ratio (with fallback computation) ───────────────────────────
        peg = safe_float('pegRatio')
        if peg is None and pe is not None and pe > 0:
            earnings_growth = safe_float('earningsGrowth', 4)
            if earnings_growth is not None and earnings_growth > 0:
                growth_pct = earnings_growth * 100
                peg = round(pe / growth_pct, 2)

        response = {
            'ticker': ticker.upper(),
            'name': info.get('longName') or info.get('shortName', ticker.upper()),
            'sector': info.get('sector') or 'N/A',
            'industry': info.get('industry') or 'N/A',
            'currentPrice': price,
            'dayChange': day_change_pct,
            'marketCap': fmt_large(info.get('marketCap')),
            'trailingPE': pe,
            'forwardPE': forward_pe,
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
            'macdValue': macd_val,
            'macdSignalValue': signal_val,
            'macdStatus': macd_status,
            'macdMomentum': macd_momentum,
            'volatilityStatus': volatility_status,
            'atrRatio': vol_ratio,
            'volumeStatus': volume_status,
            'volumeRelative': vol_relative,
            'volumeTrend': volume_trend,
            # New key metrics
            'evToEbitda': safe_float('enterpriseToEbitda'),
            'pegRatio': peg,
            'dividendRate': safe_float('dividendRate'),
            'fiftyDayAverage': safe_float('fiftyDayAverage'),
            'twoHundredDayAverage': safe_float('twoHundredDayAverage'),
            # Trend alignment
            'trendAlignment': trend_alignment,
            'trendDetail': trend_detail,
            # Earnings proximity
            'earningsDate': earnings_date_str,
            'earningsProximity': earnings_proximity,
            'earningsProximityDays': earnings_proximity_days,
            'earningsWarning': earnings_warning,
        }

        # ── Ex-dividend date ─────────────────────────────────────────────────
        ex_div_raw = info.get('exDividendDate')
        if ex_div_raw:
            try:
                if isinstance(ex_div_raw, (int, float)):
                    response['exDividendDate'] = datetime.fromtimestamp(ex_div_raw).strftime('%Y-%m-%d')
                else:
                    response['exDividendDate'] = str(ex_div_raw)
            except Exception:
                pass

        # ── Relative strength vs SPY ─────────────────────────────────────────
        response.update(rel_strength_data)

        # ── Dividend Health ──────────────────────────────────────────────────
        payout_ratio = safe_float('payoutRatio', 4)
        if payout_ratio is None:
            div_rate = safe_float('dividendRate')
            eps = safe_float('trailingEps')
            if div_rate is not None and eps is not None and eps > 0:
                payout_ratio = round(div_rate / eps, 4)
        div_health = None
        div_health_detail = ''
        if payout_ratio is not None:
            payout_pct = payout_ratio * 100
            if payout_pct <= 0:
                div_health = 'No Dividend'
                div_health_detail = 'Company does not pay a dividend or payout ratio is zero'
            elif payout_pct < 40:
                div_health = 'Very Healthy'
                div_health_detail = f'Payout ratio of {payout_pct:.0f}% — well-covered, room for growth'
            elif payout_pct < 60:
                div_health = 'Healthy'
                div_health_detail = f'Payout ratio of {payout_pct:.0f}% — comfortably covered by earnings'
            elif payout_pct < 80:
                div_health = 'Moderate'
                div_health_detail = f'Payout ratio of {payout_pct:.0f}% — less room for increases'
            elif payout_pct < 100:
                div_health = 'Stretched'
                div_health_detail = f'Payout ratio of {payout_pct:.0f}% — dividend consuming most earnings'
            else:
                div_health = 'Unsustainable'
                div_health_detail = f'Payout ratio of {payout_pct:.0f}% — exceeds earnings, may be cut'
        elif info.get('dividendRate') and float(info.get('dividendRate', 0)) > 0:
            div_health = 'Unknown'
            div_health_detail = 'Dividend is paid but payout ratio data not available'

        if payout_ratio is not None:
            response['payoutRatio'] = payout_ratio
        if div_health:
            response['dividendHealth'] = div_health
            response['dividendHealthDetail'] = div_health_detail

        # ── Fundamentals expansion ────────────────────────────────────────────
        # Growth
        v = safe_float('revenueGrowth', 4)
        if v is not None:
            response['revenueGrowth'] = v
        v = safe_float('earningsGrowth', 4)
        if v is not None:
            response['earningsGrowth'] = v

        # Profitability
        v = safe_float('grossMargins', 4)
        if v is not None:
            response['grossMargins'] = v
        v = safe_float('operatingMargins', 4)
        if v is not None:
            response['operatingMargins'] = v
        v = safe_float('profitMargins', 4)
        if v is not None:
            response['profitMargins'] = v
        v = safe_float('returnOnEquity', 4)
        if v is not None:
            response['returnOnEquity'] = v
        v = safe_float('returnOnAssets', 4)
        if v is not None:
            response['returnOnAssets'] = v

        # Financial health
        v = safe_float('debtToEquity')
        if v is not None:
            response['debtToEquity'] = v
        v = safe_float('currentRatio')
        if v is not None:
            response['currentRatio'] = v
        fcf_raw = info.get('freeCashflow')
        if fcf_raw is not None:
            try:
                response['freeCashflow'] = fmt_large(float(fcf_raw))
            except Exception:
                pass
        v = safe_float('revenuePerShare')
        if v is not None:
            response['revenuePerShare'] = v
        v = safe_float('shortPercentOfFloat', 4)
        if v is not None:
            response['shortPercentOfFloat'] = v

        # New fundamentals
        v = safe_float('quickRatio')
        if v is not None:
            response['quickRatio'] = v
        raw = info.get('totalCash')
        if raw is not None:
            try:
                response['totalCash'] = fmt_large(float(raw))
            except Exception:
                pass
        raw = info.get('totalDebt')
        if raw is not None:
            try:
                response['totalDebt'] = fmt_large(float(raw))
            except Exception:
                pass
        raw = info.get('operatingCashflow')
        if raw is not None:
            try:
                response['operatingCashflow'] = fmt_large(float(raw))
            except Exception:
                pass
        raw = info.get('ebitda')
        if raw is not None:
            try:
                response['ebitda'] = fmt_large(float(raw))
            except Exception:
                pass
        raw = info.get('totalRevenue')
        if raw is not None:
            try:
                response['revenueTTM'] = fmt_large(float(raw))
            except Exception:
                pass
        v = safe_float('heldPercentInsiders', 4)
        if v is not None:
            response['insiderPctHeld'] = v
        v = safe_float('heldPercentInstitutions', 4)
        if v is not None:
            response['institutionalPctHeld'] = v

        logger.info(f'Successfully returned stock data for {ticker}')
        return jsonify(response)

    except Exception as e:
        error_msg = str(e).lower()
        # Check for rate limit errors
        if '429' in error_msg or 'rate' in error_msg or 'too many' in error_msg:
            logger.warning(f'Rate limited for {ticker}: {str(e)}')
            return jsonify({'error': 'Rate limited by data provider. Please try again in a moment.'}), 429
        logger.error(f'Error with {ticker}: {type(e).__name__}: {str(e)}', exc_info=True)
        return jsonify({'error': f'{type(e).__name__}: {str(e)}'}), 500
