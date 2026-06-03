"""
GET /api/recommendations
Batch-fetches S&P 500 stock data with analyst recommendations and technical indicators.
Results are cached in-memory for 20 minutes.  When a Lambda pre-compute is running,
the endpoint reads from S3 first and falls back to local computation.
"""

import gc
import json
import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
from flask import Blueprint, jsonify

from cache import SimpleCache
from data_fetcher import (
    get_ticker_info as cached_get_ticker_info,
    get_many_ohlcv,
    get_spy_1m_return,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
)
from sp500 import get_sp500_tickers
from services.markov import analyze_markov

logger = logging.getLogger(__name__)

recommendations_bp = Blueprint('recommendations', __name__)

_cache = SimpleCache()
_CACHE_KEY = 'sp500_recommendations'
_CACHE_TTL = 1200  # 20 minutes

# Lock to prevent multiple simultaneous fetches
_fetch_lock = threading.Lock()
_fetching = False
# Wall-clock ts when _fetching was set True; used to detect zombie state if
# the worker thread crashes before reaching `finally`. Reset to None when
# _fetching becomes False.
_fetching_started_at = None
# Hard ceiling on how long a fetch may run before we consider _fetching
# stale and reset it. Should comfortably exceed worst-case _fetch_all_data().
_FETCH_MAX_RUNTIME_S = 900  # 15 minutes

# When S3_CACHE_BUCKET is configured we normally defer to Lambda for
# precompute and return 202 if S3 is empty. But if Lambda is failing,
# serving 202 forever is worse than one local fetch. Track the most
# recent successful S3 read; if it's been longer than this threshold,
# fall through to a local fetch instead of serving 202.
_S3_STALE_AFTER_S = 900  # 15 minutes
_last_s3_success_ts = None
_s3_state_lock = threading.Lock()

# Progress tracking for progressive loading
_progress_lock = threading.Lock()
_progress_current = 0
_progress_total = 0
_partial_results = []

# Chunked fetching config
_CHUNK_SIZE = 50
_CHUNK_DELAY = 0.5  # seconds between chunks
_MAX_WORKERS = 8


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
    """Compute RSI from a close price series (Wilder's formula)."""
    delta = close_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))


def _get_ticker_info(ticker, priority=PRIORITY_LOW):
    """Fetch info dict for a single ticker via the throttled/cached data_fetcher.
    Returns (ticker, info) or (ticker, None)."""
    try:
        info = cached_get_ticker_info(ticker, priority=priority)
        if not info or (info.get('regularMarketPrice') is None and info.get('currentPrice') is None):
            logger.debug('No price data for %s — skipping', ticker)
            return (ticker, None)
        return (ticker, info)
    except Exception as e:
        logger.debug('Info fetch failed for %s: %s', ticker, e)
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
    """Build a single stock record from info dict and history DataFrame.

    ``info`` may be None — price data is extracted from ``hist_df`` in that
    case, and analyst recommendation / company name default to N/A / ticker.
    """
    try:
        close = hist_df['Close']
        if len(close) < 50:
            return None

        if info:
            current_price = _safe_float(info.get('currentPrice') or info.get('regularMarketPrice'))
            if current_price is None:
                current_price = _safe_float(close.iloc[-1])
            prev_close = _safe_float(info.get('previousClose') or info.get('regularMarketPreviousClose'))
            if prev_close is None and len(close) >= 2:
                prev_close = _safe_float(close.iloc[-2])
            rec_key = info.get('recommendationKey', '')
            if rec_key:
                rec_key = rec_key.lower().replace(' ', '_')
            rec_display = rec_key.replace('_', ' ').title() if rec_key else 'N/A'
            name = info.get('longName') or info.get('shortName') or ticker
            target_mean = _safe_float(info.get('targetMeanPrice'))
            overall_risk = info.get('overallRisk')
            if overall_risk is not None:
                try:
                    overall_risk = int(overall_risk)
                except (ValueError, TypeError):
                    overall_risk = None
            raw_n = info.get('numberOfAnalystOpinions') or info.get('numberOfAnalystRatings')
            n_analysts = None
            if raw_n is not None:
                try:
                    n_analysts = int(raw_n)
                except (ValueError, TypeError):
                    pass
            raw_eg = info.get('earningsGrowth')
            eps_growth = _safe_float(raw_eg, decimals=4) if raw_eg is not None else None
            raw_rg = info.get('revenueGrowth')
            revenue_growth = _safe_float(raw_rg, decimals=4) if raw_rg is not None else None
            forward_pe = _safe_float(info.get('forwardPE'))
            if forward_pe is None:
                forward_pe = _safe_float(info.get('trailingPE'))
            roe = _safe_float(info.get('returnOnEquity'), decimals=4)
            debt_to_equity = _safe_float(info.get('debtToEquity'))
            gross_margins = _safe_float(info.get('grossMargins'), decimals=4)
            fcf = info.get('freeCashflow')
            mkt_cap = info.get('marketCap')
            fcf_yield = None
            if fcf is not None and mkt_cap is not None:
                try:
                    if float(mkt_cap) > 0:
                        fcf_yield = round(float(fcf) / float(mkt_cap), 4)
                except (ValueError, TypeError):
                    pass
            fifty_two_high = _safe_float(info.get('fiftyTwoWeekHigh'))
            fifty_two_low = _safe_float(info.get('fiftyTwoWeekLow'))
        else:
            current_price = _safe_float(close.iloc[-1])
            prev_close = _safe_float(close.iloc[-2]) if len(close) >= 2 else None
            rec_key = 'n/a'
            rec_display = 'N/A'
            name = ticker
            target_mean = None
            overall_risk = None
            n_analysts = None
            eps_growth = None
            revenue_growth = None
            forward_pe = None
            roe = None
            debt_to_equity = None
            gross_margins = None
            fcf_yield = None
            fifty_two_high = None
            fifty_two_low = None

        # Day change
        if current_price and prev_close and prev_close > 0:
            day_change = round((current_price - prev_close) / prev_close * 100, 2)
        else:
            day_change = None

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

        # Analyst target upside vs current price
        if target_mean and current_price and current_price > 0:
            target_upside_pct = round((target_mean - current_price) / current_price * 100, 2)
        else:
            target_upside_pct = None

        # 52-week position — fall back to price history if yfinance fields missing
        if fifty_two_high is None and len(close) > 0:
            fifty_two_high = _safe_float(close.tail(252).max())
        if fifty_two_low is None and len(close) > 0:
            fifty_two_low = _safe_float(close.tail(252).min())
        fifty_two_position = None
        if (fifty_two_high is not None and fifty_two_low is not None
                and current_price is not None and fifty_two_high > fifty_two_low):
            fifty_two_position = round(
                (current_price - fifty_two_low) / (fifty_two_high - fifty_two_low) * 100, 2
            )

        # ── Markov regime fields ──────────────────────────────────────────
        # Used by the Markov Regime ETF strategy. Cheap (~50ms / ticker) and
        # uses the same close series we already have in scope.
        markov_regime = None
        markov_bull_3d = None
        markov_bull_5d = None
        markov_bear_5d = None
        try:
            markov = analyze_markov(close.to_numpy(dtype=float))
            if markov is not None:
                markov_regime = markov['current_regime']
                f5 = markov['forecast'].get('5d')
                f3 = markov['forecast'].get('3d')
                if f5:
                    markov_bull_5d = round(f5['bull'], 4)
                    markov_bear_5d = round(f5['bear'], 4)
                if f3:
                    markov_bull_3d = round(f3['bull'], 4)
        except Exception:
            pass

        return {
            'ticker': ticker,
            'name': name,
            'currentPrice': current_price,
            'dayChangePct': day_change,
            'analystRecommendation': rec_display,
            'recommendationKey': rec_key or 'n/a',
            'targetMeanPrice': target_mean,
            'targetUpsidePct': target_upside_pct,
            'priceAction': price_action,
            'macdStatus': macd_status,
            'volatilityStatus': volatility_status,
            'volRatio': vol_ratio,
            'trendAlignment': trend_alignment,
            'momentum': momentum,
            'overallRisk': overall_risk,
            'rsiValue': rsi_val,
            'numberOfAnalysts': n_analysts,
            'epsGrowth': eps_growth,
            'revenueGrowth': revenue_growth,
            'forwardPE': forward_pe,
            'returnOnEquity': roe,
            'debtToEquity': debt_to_equity,
            'grossMargins': gross_margins,
            'fcfYield': fcf_yield,
            'fiftyTwoWeekHigh': fifty_two_high,
            'fiftyTwoWeekLow': fifty_two_low,
            'fiftyTwoWeekPosition': fifty_two_position,
            'markovRegime': markov_regime,
            'markovBull3d': markov_bull_3d,
            'markovBull5d': markov_bull_5d,
            'markovBear5d': markov_bear_5d,
        }
    except Exception as e:
        logger.warning('_build_stock_data failed for ticker: %s', e)
        return None


def _fetch_all_data():
    """Fetch S&P 500 data in memory-efficient batches.

    Downloads OHLCV in chunks of _CHUNK_SIZE tickers, processes each chunk,
    then discards the raw DataFrame before starting the next batch.
    Peak memory is ~50 tickers instead of ~500.
    """
    global _fetching
    tickers = get_sp500_tickers()
    logger.info('Starting S&P 500 fetch for %d tickers', len(tickers))
    t0 = time.time()

    # ── Step 1: SPY 1M return (shared, cached) ────────────────────────
    try:
        spy_1m_return = get_spy_1m_return(priority=PRIORITY_LOW)
        if spy_1m_return is not None:
            logger.info('SPY 1M return: %.2f%%', spy_1m_return)
    except Exception as e:
        logger.warning('Could not fetch/compute SPY return: %s', e)
        spy_1m_return = None

    # ── Step 2: Process tickers in batched download + build cycles ─────
    global _progress_current, _progress_total, _partial_results
    stocks = []
    failed = 0

    with _progress_lock:
        _progress_current = 0
        _progress_total = len(tickers)
        _partial_results = []

    for chunk_start in range(0, len(tickers), _CHUNK_SIZE):
        chunk = tickers[chunk_start:chunk_start + _CHUNK_SIZE]

        # 2a: Download OHLCV for this chunk via the throttled/cached helper.
        # chunk_delay=0 because the outer loop handles pacing at the bottom.
        try:
            chunk_map = get_many_ohlcv(chunk, period='10mo',
                                       chunk_size=_CHUNK_SIZE, chunk_delay=0, priority=PRIORITY_LOW)
        except Exception as e:
            logger.error('get_many_ohlcv failed for chunk %d: %s', chunk_start, e)
            failed += len(chunk)
            continue

        # 2b: Fetch .info concurrently
        # Each future internally enqueues onto YFinanceQueue (single worker,
        # 0.3s rate gate, up to 30s per submit), so a chunk-of-50's tail
        # futures legitimately wait 30+ seconds. The previous 5s timeout
        # abandoned those futures while the queue work still ran — wasted
        # API calls and duplicate fetches on retry. Use a bound that
        # comfortably covers the worst-case (50 × 0.3s queue gate + ~20s
        # call) plus a safety margin.
        info_map = {}
        _FUTURE_TIMEOUT = 60
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {executor.submit(_get_ticker_info, t): t for t in chunk}
            for future in as_completed(futures):
                try:
                    t, info = future.result(timeout=_FUTURE_TIMEOUT)
                    if info:
                        info_map[t] = info
                except Exception as e:
                    logger.debug('Future result error: %s', e)

        # 2c: Build stock records (info may be None — that's OK)
        for t in chunk:
            hist_df = chunk_map.get(t)
            if hist_df is None or hist_df.empty or len(hist_df) < 50:
                logger.debug('%s: insufficient history — skipping', t)
                failed += 1
                continue

            record = _build_stock_data(t, info_map.get(t), hist_df, spy_1m_return)
            if record:
                stocks.append(record)
            else:
                failed += 1

        # 2d: Free batch memory before next iteration
        del chunk_map
        gc.collect()

        # 2e: Update progress for progressive loading
        with _progress_lock:
            _progress_current = min(chunk_start + _CHUNK_SIZE, len(tickers))
            _partial_results = list(stocks)

        logger.info('Chunk %d-%d done — %d stocks so far',
                     chunk_start, chunk_start + len(chunk), len(stocks))

        # Small delay between chunks to avoid rate limit bursts
        if chunk_start + _CHUNK_SIZE < len(tickers):
            time.sleep(_CHUNK_DELAY)

    logger.info('Fetch completed in %.1fs — %d stocks, %d failed out of %d',
                time.time() - t0, len(stocks), failed, len(tickers))
    return stocks, failed, len(tickers)


def _read_s3_cache():
    """Try reading pre-computed results from S3. Returns dict or None.

    On a fresh, non-stale hit, records `_last_s3_success_ts` so callers can
    tell how long it's been since Lambda last published a usable snapshot
    (see `_lambda_is_healthy`).
    """
    global _last_s3_success_ts
    bucket = os.environ.get('S3_CACHE_BUCKET')
    if not bucket:
        return None
    try:
        import boto3
        s3 = boto3.client('s3')
        resp = s3.get_object(Bucket=bucket, Key='recommendations/latest.json')
        last_modified = resp['LastModified']
        age_seconds = (datetime.now(timezone.utc) - last_modified).total_seconds()
        if age_seconds > 1500:  # 25 min — stale beyond TTL + buffer
            logger.info('S3 cache is %.0fs old — stale, skipping', age_seconds)
            return None
        data = json.loads(resp['Body'].read())
        logger.info('S3 cache hit — %d stocks, %.0fs old', data.get('count', 0), age_seconds)
        with _s3_state_lock:
            _last_s3_success_ts = time.time()
        return data
    except Exception as e:
        logger.debug('S3 cache read failed: %s', e)
        return None


# Process startup baseline; used as the "last known good" anchor when we've
# never read S3 yet, so a Lambda that has been failing since boot still
# eventually triggers a local fallback.
_process_start_ts = time.time()


def _lambda_should_be_bypassed():
    """True when Lambda is configured but hasn't produced a fresh S3 snapshot
    in `_S3_STALE_AFTER_S` seconds, indicating the precompute is failing and
    we should fall back to a local fetch rather than serve 202 forever.
    """
    if not os.environ.get('S3_CACHE_BUCKET'):
        return False
    with _s3_state_lock:
        anchor = _last_s3_success_ts or _process_start_ts
    return (time.time() - anchor) > _S3_STALE_AFTER_S


def _maybe_reset_zombie_fetch():
    """If _fetching has been True for longer than _FETCH_MAX_RUNTIME_S, the
    background worker thread crashed before reaching its `finally`. Reset the
    flag so subsequent requests can make progress. Caller must hold _fetch_lock.
    """
    global _fetching, _fetching_started_at
    if _fetching and _fetching_started_at is not None:
        runtime = time.time() - _fetching_started_at
        if runtime > _FETCH_MAX_RUNTIME_S:
            logger.warning(
                'Resetting zombie _fetching=True after %.0fs (max %ds) — '
                'background worker likely crashed before clearing flag',
                runtime, _FETCH_MAX_RUNTIME_S,
            )
            _fetching = False
            _fetching_started_at = None


def prewarm_cache():
    """Pre-warm the recommendations cache in a background thread.
    Called from app.py on server start so the first user doesn't wait 60s.
    Checks S3 first (Lambda pre-compute), falls back to local fetch."""
    global _fetching, _fetching_started_at

    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached:
        logger.info('Prewarm skipped — cache already warm (%d stocks)', cached.get('count', 0))
        return

    # Try S3 before doing the heavy local fetch
    s3_data = _read_s3_cache()
    if s3_data:
        _cache.set(_CACHE_KEY, s3_data)
        logger.info('Prewarm from S3 — %d stocks cached', s3_data.get('count', 0))
        return

    # When Lambda is configured AND has produced a fresh snapshot recently,
    # skip the local fetch and wait for the next Lambda cycle. Otherwise
    # fall through — serving 202 forever when Lambda is silently broken is
    # worse than burning one local fetch.
    if os.environ.get('S3_CACHE_BUCKET') and not _lambda_should_be_bypassed():
        logger.info('Prewarm skipped — Lambda is configured but S3 cache not yet available')
        return
    if _lambda_should_be_bypassed():
        logger.warning('Prewarm falling through to local fetch — Lambda appears to be failing (no fresh S3 in %ds)', _S3_STALE_AFTER_S)

    with _fetch_lock:
        cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
        if cached:
            return
        _fetching = True
        _fetching_started_at = time.time()

    logger.info('Prewarm started (local fetch)')
    t0 = time.time()
    try:
        stocks, failed, total = _fetch_all_data()
        result = {
            'stocks': stocks,
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
            'count': len(stocks),
            'failedCount': failed,
            'totalTickers': total,
        }
        _cache.set(_CACHE_KEY, result)
        logger.info('Prewarm complete in %.1fs — %d stocks cached (%d failed)', time.time() - t0, len(stocks), failed)
    except Exception as e:
        logger.error('Prewarm failed: %s', e, exc_info=True)
    finally:
        with _fetch_lock:
            _fetching = False
            _fetching_started_at = None


@recommendations_bp.route('/api/recommendations')
def get_recommendations():
    global _fetching, _fetching_started_at

    # 1. Check in-memory cache
    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached:
        logger.info('Cache hit — returning %d stocks', cached.get('count', 0))
        return jsonify(cached)

    # 2. Check S3 (Lambda pre-compute)
    s3_data = _read_s3_cache()
    if s3_data:
        _cache.set(_CACHE_KEY, s3_data)
        return jsonify(s3_data)

    # 3. When Lambda is configured and producing fresh snapshots, defer to
    #    it (return 202; frontend polls). If Lambda hasn't published a
    #    fresh S3 file in _S3_STALE_AFTER_S, treat it as broken and fall
    #    through to a local fetch instead of returning 202 forever.
    if os.environ.get('S3_CACHE_BUCKET') and not _lambda_should_be_bypassed():
        logger.info('Lambda configured but S3 not ready — returning 202')
        return jsonify({
            'status': 'loading',
            'message': 'Recommendations are being computed. Please try again shortly.',
        }), 202
    if _lambda_should_be_bypassed():
        logger.warning('Falling through to local fetch — Lambda appears to be failing (no fresh S3 in %ds)', _S3_STALE_AFTER_S)

    # 4. Prevent multiple simultaneous local fetches. Also reset zombie
    #    _fetching=True if the previous fetch exceeded the max runtime
    #    (background thread likely crashed before clearing the flag).
    with _fetch_lock:
        _maybe_reset_zombie_fetch()
        if _fetching:
            logger.info('Fetch in progress — returning 202')
            return jsonify({
                'status': 'loading',
                'message': 'S&P 500 data is currently being fetched. Please try again in a moment.',
            }), 202

    # 5. Fall back to local computation (no Lambda or Lambda failing)
    logger.info('Cache miss — starting on-demand fetch')
    try:
        with _fetch_lock:
            cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
            if cached:
                logger.info('Cache hit after lock — returning %d stocks', cached.get('count', 0))
                return jsonify(cached)

            _fetching = True
            _fetching_started_at = time.time()

        stocks, failed, total = _fetch_all_data()

        result = {
            'stocks': stocks,
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
            'count': len(stocks),
            'failedCount': failed,
            'totalTickers': total,
        }
        _cache.set(_CACHE_KEY, result)
        logger.info('On-demand fetch complete — %d stocks returned (%d failed)', len(stocks), failed)
        return jsonify(result)

    except Exception as e:
        logger.error('get_recommendations failed: %s', e, exc_info=True)
        return jsonify({
            'error': f'Failed to fetch recommendations: {str(e)}',
            'stocks': [],
        }), 500

    finally:
        with _fetch_lock:
            _fetching = False
            _fetching_started_at = None


@recommendations_bp.route('/api/recommendations/progress')
def get_recommendations_progress():
    """Return partial results and progress while a fetch is in progress."""
    # If cache is warm, return the full result
    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached:
        return jsonify({
            'status': 'complete',
            'stocks': cached.get('stocks', []),
            'progress': cached.get('totalTickers', 0),
            'total': cached.get('totalTickers', 0),
        })

    # If not fetching, nothing to report
    with _fetch_lock:
        if not _fetching:
            return jsonify({
                'status': 'idle',
                'stocks': [],
                'progress': 0,
                'total': 0,
            })

    # Return partial results from in-progress fetch
    with _progress_lock:
        return jsonify({
            'status': 'loading',
            'stocks': list(_partial_results),
            'progress': _progress_current,
            'total': _progress_total,
        })
