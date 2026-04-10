"""
GET /api/upcoming-events
Fetches upcoming corporate events (earnings, ex-dividend, stock splits) for
all S&P 500 tickers within the next 30 days.  Results are pre-cached on
server startup and refreshed every 24 hours.
"""

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify

from cache import SimpleCache
from data_fetcher import (
    get_ticker_info as cached_get_ticker_info,
    _throttle,
    _get_ticker,
)
from sp500 import get_sp500_tickers

logger = logging.getLogger(__name__)

upcoming_events_bp = Blueprint('upcoming_events', __name__)

_cache = SimpleCache()
_CACHE_KEY = 'sp500_upcoming_events'
_CACHE_TTL = 86400  # 24 hours

_fetch_lock = threading.Lock()
_fetching = False

_MAX_WORKERS = 8
_CHUNK_SIZE = 50
_CHUNK_DELAY = 0.5
_LOOKAHEAD_DAYS = 30


def _safe_float(val, decimals=2):
    if val is None or val == 'N/A':
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, decimals)
    except Exception:
        return None


def _parse_date(val):
    """Try to extract a date from various yfinance calendar value formats."""
    if val is None:
        return None
    # Already a datetime
    if isinstance(val, datetime):
        return val.date()
    # pandas Timestamp
    if hasattr(val, 'date'):
        return val.date()
    # List of dates (e.g. earnings can return [date1, date2])
    if isinstance(val, (list, tuple)):
        for item in val:
            d = _parse_date(item)
            if d:
                return d
        return None
    # String date
    if isinstance(val, str):
        for fmt in ('%Y-%m-%d', '%b %d, %Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
    return None


def _fetch_ticker_events(ticker):
    """Fetch upcoming events for a single ticker using yfinance .calendar and .info."""
    events = []
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=_LOOKAHEAD_DAYS)

    try:
        _throttle()
        stock = _get_ticker(ticker)
        cal = None
        try:
            cal = stock.calendar
        except Exception as e:
            logger.debug('%s: calendar fetch failed: %s', ticker, e)

        # Get info for price/analyst data (uses cached data_fetcher)
        info = None
        try:
            info = cached_get_ticker_info(ticker)
        except Exception as e:
            logger.debug('%s: info fetch failed: %s', ticker, e)

        if not info:
            info = {}

        company_name = info.get('longName') or info.get('shortName') or ticker
        current_price = _safe_float(info.get('currentPrice') or info.get('regularMarketPrice'))
        prev_close = _safe_float(info.get('previousClose') or info.get('regularMarketPreviousClose'))
        day_change = None
        if current_price and prev_close and prev_close > 0:
            day_change = round((current_price - prev_close) / prev_close * 100, 2)

        rec_key = info.get('recommendationKey', '')
        if rec_key:
            rec_key = rec_key.lower().replace(' ', '_')
        rec_display = rec_key.replace('_', ' ').title() if rec_key else 'N/A'

        base = {
            'ticker': ticker,
            'companyName': company_name,
            'analystRecommendation': rec_display,
            'recommendationKey': rec_key or 'n/a',
            'currentPrice': current_price,
            'dayChangePct': day_change,
        }

        # Extract events from calendar
        if cal is not None:
            # calendar can be a dict or a DataFrame
            cal_dict = {}
            if isinstance(cal, dict):
                cal_dict = cal
            elif hasattr(cal, 'to_dict'):
                try:
                    # DataFrame: columns are dates or values
                    cal_dict = cal.iloc[:, 0].to_dict() if not cal.empty else {}
                except Exception:
                    try:
                        cal_dict = cal.to_dict()
                    except Exception:
                        pass

            # Earnings Date
            for key in ('Earnings Date', 'earningsDate', 'Earnings Average'):
                if key in cal_dict:
                    ed = _parse_date(cal_dict[key])
                    if ed and today <= ed <= cutoff:
                        days_until = (ed - today).days
                        events.append({
                            **base,
                            'eventType': 'Earnings',
                            'eventDate': ed.isoformat(),
                            'daysUntil': days_until,
                        })
                    break

            # Ex-Dividend Date
            for key in ('Ex-Dividend Date', 'exDividendDate'):
                if key in cal_dict:
                    dd = _parse_date(cal_dict[key])
                    if dd and today <= dd <= cutoff:
                        days_until = (dd - today).days
                        events.append({
                            **base,
                            'eventType': 'Ex-Dividend',
                            'eventDate': dd.isoformat(),
                            'daysUntil': days_until,
                        })
                    break

            # Stock Split (rarely available)
            for key in ('Stock Splits', 'stockSplit', 'Split Date'):
                if key in cal_dict:
                    sd = _parse_date(cal_dict[key])
                    if sd and today <= sd <= cutoff:
                        days_until = (sd - today).days
                        events.append({
                            **base,
                            'eventType': 'Stock Split',
                            'eventDate': sd.isoformat(),
                            'daysUntil': days_until,
                        })
                    break

        # Fallback: check info dict for ex-dividend date if calendar missed it
        if not any(e['eventType'] == 'Ex-Dividend' for e in events):
            ex_div = info.get('exDividendDate')
            if ex_div:
                # yfinance sometimes returns epoch seconds
                if isinstance(ex_div, (int, float)) and ex_div > 1e9:
                    ex_div = datetime.fromtimestamp(ex_div, tz=timezone.utc).date()
                else:
                    ex_div = _parse_date(ex_div)
                if ex_div and today <= ex_div <= cutoff:
                    days_until = (ex_div - today).days
                    events.append({
                        **base,
                        'eventType': 'Ex-Dividend',
                        'eventDate': ex_div.isoformat(),
                        'daysUntil': days_until,
                    })

    except Exception as e:
        logger.debug('%s: event fetch failed: %s', ticker, e)

    return events


def _fetch_all_events():
    """Fetch upcoming events for all S&P 500 tickers in batches."""
    tickers = get_sp500_tickers()
    logger.info('Fetching upcoming events for %d S&P 500 tickers', len(tickers))
    t0 = time.time()

    all_events = []
    failed = 0

    for chunk_start in range(0, len(tickers), _CHUNK_SIZE):
        chunk = tickers[chunk_start:chunk_start + _CHUNK_SIZE]

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch_ticker_events, t): t for t in chunk}
            for future in as_completed(futures):
                t = futures[future]
                try:
                    events = future.result(timeout=15)
                    all_events.extend(events)
                except Exception as e:
                    logger.debug('Event fetch failed for %s: %s', t, e)
                    failed += 1

        logger.info('Events chunk %d-%d done — %d events so far',
                     chunk_start, chunk_start + len(chunk), len(all_events))

        if chunk_start + _CHUNK_SIZE < len(tickers):
            time.sleep(_CHUNK_DELAY)

    # Sort by event date ascending
    all_events.sort(key=lambda e: e['eventDate'])

    logger.info('Event fetch completed in %.1fs — %d events found (%d tickers failed)',
                time.time() - t0, len(all_events), failed)
    return all_events


def prewarm_events_cache():
    """Pre-warm the events cache in a background thread on server start."""
    global _fetching

    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached:
        logger.info('Events prewarm skipped — cache already warm (%d events)', cached.get('count', 0))
        return

    with _fetch_lock:
        cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
        if cached:
            return
        _fetching = True

    logger.info('Events prewarm started')
    t0 = time.time()
    try:
        events = _fetch_all_events()
        result = {
            'events': events,
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
            'count': len(events),
        }
        _cache.set(_CACHE_KEY, result)
        logger.info('Events prewarm complete in %.1fs — %d events cached',
                     time.time() - t0, len(events))
    except Exception as e:
        logger.error('Events prewarm failed: %s', e, exc_info=True)
    finally:
        _fetching = False


@upcoming_events_bp.route('/api/upcoming-events')
def get_upcoming_events():
    global _fetching

    cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached:
        logger.info('Events cache hit — returning %d events', cached.get('count', 0))
        return jsonify(cached)

    if _fetching:
        logger.info('Events fetch in progress — returning 202')
        return jsonify({
            'status': 'loading',
            'message': 'Upcoming events are being fetched. Please try again shortly.',
        }), 202

    # On-demand fetch if cache expired and no prewarm running
    logger.info('Events cache miss — starting on-demand fetch')
    try:
        with _fetch_lock:
            cached = _cache.get(_CACHE_KEY, _CACHE_TTL)
            if cached:
                return jsonify(cached)
            _fetching = True

        events = _fetch_all_events()
        result = {
            'events': events,
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
            'count': len(events),
        }
        _cache.set(_CACHE_KEY, result)
        logger.info('On-demand events fetch — %d events returned', len(events))
        return jsonify(result)

    except Exception as e:
        logger.error('get_upcoming_events failed: %s', e, exc_info=True)
        return jsonify({
            'error': f'Failed to fetch upcoming events: {str(e)}',
            'events': [],
        }), 500

    finally:
        _fetching = False
