"""
GET /api/recommendations
Batch-fetches S&P 500 stock data with analyst recommendations and technical indicators.
Results are cached in-memory for 30 minutes.
"""

import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify

from cache import SimpleCache
from sp500 import get_sp500_tickers

recommendations_bp = Blueprint('recommendations', __name__)

_cache = SimpleCache()
_CACHE_KEY = 'sp500_recommendations'
_CACHE_TTL = 1800  # 30 minutes

# Lock to prevent multiple simultaneous fetches
_fetch_lock = threading.Lock()
_fetching = False


def _safe_float(val, decimals=2):
    """Safely convert a value to a rounded float, returning None on failure."""
    if val is None or val == 'N/A':
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, decimals)
    except Exception:
        return None


def _compute_rsi(close_series, period=14):
    """Compute RSI from a close price series."""
    delta = close_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _get_ticker_info(ticker):
    """Fetch info dict for a single ticker. Returns (ticker, info) or (ticker, None)."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or info.get('regularMarketPrice') is None and info.get('currentPrice') is None:
            return (ticker, None)
        return (ticker, info)
    except Exception:
        return (ticker, None)


def _compute_price_action(rsi_val, consol_range):
    """Derive price action label from RSI and consolidation range."""
    if rsi_val is not None and rsi_val >= 70:
        return 'Overbought'
    if rsi_val is not None and rsi_val <= 30:
        return 'Oversold'
    if consol_range is not None and consol_range < 5.0:
        return 'Consolidating'
    if rsi_val is not None and 40 <= rsi_val <= 60:
        return 'Neutral'
    return 'Trending'


def _build_stock_data(ticker, info, hist_df, spy_1m_return):
    """Build a single stock record from info dict and history DataFrame."""
    try:
        close = hist_df['Close']
        if len(close) < 50:
            return None

        current_price = _safe_float(info.get('currentPrice') or info.get('regularMarketPrice'))
        if current_price is None:
            current_price = _safe_float(close.iloc[-1])

        # Day change
        prev_close = _safe_float(info.get('previousClose') or info.get('regularMarketPreviousClose'))
        if current_price and prev_close and prev_close > 0:
            day_change = round((current_price - prev_close) / prev_close * 100, 2)
        else:
            day_change = None

        # Analyst recommendation
        rec_key = info.get('recommendationKey', '')
        if rec_key:
            rec_key = rec_key.lower().replace(' ', '_')
        rec_display = rec_key.replace('_', ' ').title() if rec_key else 'N/A'

        # Name
        name = info.get('longName') or info.get('shortName') or ticker

        # ── MACD ──────────────────────────────────────────────────────────
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_sig = macd.ewm(span=9, adjust=False).mean()

        macd_val = float(macd.iloc[-1])
        signal_val = float(macd_sig.iloc[-1])
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

        # ── Volatility (ATR) ──────────────────────────────────────────────
        high_low = hist_df['High'] - hist_df['Low']
        high_pc = (hist_df['High'] - close.shift(1)).abs()
        low_pc = (hist_df['Low'] - close.shift(1)).abs()
        tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        atr_val = float(atr.iloc[-1])
        atr_avg = float(atr.mean())
        vol_ratio = round(atr_val / atr_avg, 2) if atr_avg > 0 else 1.0

        if vol_ratio > 1.5:
            volatility_status = 'HIGH Volatility'
        elif vol_ratio < 0.7:
            volatility_status = 'LOW Volatility'
        else:
            volatility_status = 'Normal Volatility'

        # ── Trend Alignment ───────────────────────────────────────────────
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        current_close = float(close.iloc[-1])
        trend_alignment = 'N/A'

        if len(close) >= 200 and not pd.isna(ma200.iloc[-1]):
            m20, m50, m200 = float(ma20.iloc[-1]), float(ma50.iloc[-1]), float(ma200.iloc[-1])
            if current_close > m20 > m50 > m200:
                trend_alignment = 'Strong Uptrend'
            elif current_close < m20 < m50 < m200:
                trend_alignment = 'Strong Downtrend'
            elif current_close > m200:
                trend_alignment = 'Bullish (Mixed)'
            else:
                trend_alignment = 'Bearish (Mixed)'
        elif len(close) >= 50 and not pd.isna(ma50.iloc[-1]):
            m20, m50 = float(ma20.iloc[-1]), float(ma50.iloc[-1])
            if current_close > m20 > m50:
                trend_alignment = 'Bullish (Short-term)'
            else:
                trend_alignment = 'Bearish (Short-term)'

        # ── Momentum (1M return vs SPY) ───────────────────────────────────
        momentum = None
        if len(close) >= 22:
            stock_1m = (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100
            if spy_1m_return is not None:
                momentum = round(stock_1m - spy_1m_return, 2)
            else:
                momentum = round(stock_1m, 2)

        # ── Price Action ──────────────────────────────────────────────────
        rsi_series = _compute_rsi(close)
        rsi_val = None
        if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]):
            rsi_val = round(float(rsi_series.iloc[-1]), 1)

        # Consolidation range
        consol_range = None
        if len(close) >= 20:
            recent = close.iloc[-20:]
            consol_range = round((recent.max() - recent.min()) / recent.mean() * 100, 2)

        price_action = _compute_price_action(rsi_val, consol_range)

        return {
            'ticker': ticker,
            'name': name,
            'currentPrice': current_price,
            'dayChangePct': day_change,
            'analystRecommendation': rec_display,
            'recommendationKey': rec_key or 'n/a',
            'priceAction': price_action,
            'macdStatus': macd_status,
            'volatilityStatus': volatility_status,
            'trendAlignment': trend_alignment,
            'momentum': momentum,
        }
    except Exception:
        return None


def _fetch_all_data():
    """Fetch S&P 500 data: batch history via yf.download + individual info via threads."""
    global _fetching
    tickers = get_sp500_tickers()

    # ── Step 1: Batch download historical data (includes SPY) ─────────
    all_tickers = tickers + ['SPY']
    try:
        raw = yf.download(all_tickers, period='1y', group_by='ticker', threads=True, progress=False)
    except Exception:
        return [], 0, len(tickers)

    # ── Step 2: Compute SPY 1-month return ────────────────────────────
    spy_1m_return = None
    try:
        spy_close = raw['SPY']['Close'].dropna()
        if len(spy_close) >= 22:
            spy_1m_return = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-22]) - 1) * 100
    except Exception:
        pass

    # ── Step 3: Fetch info dicts concurrently ─────────────────────────
    info_map = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(_get_ticker_info, t): t for t in tickers}
        for future in as_completed(futures):
            try:
                t, info = future.result(timeout=10)
                if info:
                    info_map[t] = info
            except Exception:
                pass

    # ── Step 4: Build stock records ───────────────────────────────────
    stocks = []
    failed = 0
    for t in tickers:
        info = info_map.get(t)
        if not info:
            failed += 1
            continue

        try:
            hist_df = raw[t].dropna(how='all')
            if hist_df.empty or len(hist_df) < 50:
                failed += 1
                continue
        except Exception:
            failed += 1
            continue

        record = _build_stock_data(t, info, hist_df, spy_1m_return)
        if record:
            stocks.append(record)
        else:
            failed += 1

    return stocks, failed, len(tickers)


def prewarm_cache():
    """Pre-warm the recommendations cache in a background thread.
    Called from app.py on server start so the first user doesn't wait 60s."""
    global _fetching

    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached:
        return  # already warm

    with _fetch_lock:
        cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
        if cached:
            return
        _fetching = True

    try:
        stocks, failed, total = _fetch_all_data()
        result = {
            'stocks': stocks,
            'lastUpdated': datetime.utcnow().isoformat() + 'Z',
            'count': len(stocks),
            'failedCount': failed,
            'totalTickers': total,
        }
        _cache.set(_CACHE_KEY, result)
    except Exception:
        pass
    finally:
        _fetching = False


@recommendations_bp.route('/api/recommendations')
def get_recommendations():
    global _fetching

    # Check cache first
    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached:
        return jsonify(cached)

    # Prevent multiple simultaneous fetches
    if _fetching:
        return jsonify({
            'status': 'loading',
            'message': 'S&P 500 data is currently being fetched. Please try again in a moment.',
        }), 202

    try:
        with _fetch_lock:
            # Double-check cache after acquiring lock
            cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
            if cached:
                return jsonify(cached)

            _fetching = True

        stocks, failed, total = _fetch_all_data()

        result = {
            'stocks': stocks,
            'lastUpdated': datetime.utcnow().isoformat() + 'Z',
            'count': len(stocks),
            'failedCount': failed,
            'totalTickers': total,
        }
        _cache.set(_CACHE_KEY, result)
        return jsonify(result)

    except Exception as e:
        return jsonify({
            'error': f'Failed to fetch recommendations: {str(e)}',
            'stocks': [],
        }), 500

    finally:
        _fetching = False
