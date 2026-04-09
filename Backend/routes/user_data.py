import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd
import yfinance as yf
from flask import Blueprint, request, jsonify, g

from models import db, Watchlist, WatchlistItem, PortfolioHolding, UserSettings
from auth import login_required
from routes.recommendations import _build_stock_data, _get_ticker_info

logger = logging.getLogger(__name__)

user_data_bp = Blueprint('user_data', __name__, url_prefix='/api/user')


# ── Watchlists ──────────────────────────────────────────────────────────────

@user_data_bp.route('/watchlists', methods=['GET'])
@login_required
def get_watchlists():
    watchlists = Watchlist.query.filter_by(user_id=g.current_user_id).all()
    return jsonify({'watchlists': [w.to_dict() for w in watchlists]})


@user_data_bp.route('/watchlists', methods=['POST'])
@login_required
def create_watchlist():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Watchlist name is required'}), 400

    if len(name) > 100:
        return jsonify({'error': 'Watchlist name must be 100 characters or less'}), 400

    watchlist = Watchlist(user_id=g.current_user_id, name=name)
    db.session.add(watchlist)
    db.session.commit()
    return jsonify({'watchlist': watchlist.to_dict()}), 201


@user_data_bp.route('/watchlists/<int:watchlist_id>/items', methods=['POST'])
@login_required
def add_watchlist_item(watchlist_id):
    watchlist = Watchlist.query.filter_by(id=watchlist_id, user_id=g.current_user_id).first()
    if not watchlist:
        return jsonify({'error': 'Watchlist not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    ticker = (data.get('ticker') or '').strip().upper()
    if not ticker:
        return jsonify({'error': 'Ticker is required'}), 400

    existing = WatchlistItem.query.filter_by(watchlist_id=watchlist_id, ticker=ticker).first()
    if existing:
        return jsonify({'error': f'{ticker} is already in this watchlist'}), 409

    item = WatchlistItem(watchlist_id=watchlist_id, ticker=ticker)
    db.session.add(item)
    db.session.commit()
    return jsonify({'item': item.to_dict()}), 201


@user_data_bp.route('/watchlists/<int:watchlist_id>/items/<string:ticker>', methods=['DELETE'])
@login_required
def remove_watchlist_item(watchlist_id, ticker):
    watchlist = Watchlist.query.filter_by(id=watchlist_id, user_id=g.current_user_id).first()
    if not watchlist:
        return jsonify({'error': 'Watchlist not found'}), 404

    item = WatchlistItem.query.filter_by(watchlist_id=watchlist_id, ticker=ticker.upper()).first()
    if not item:
        return jsonify({'error': 'Ticker not found in watchlist'}), 404

    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': f'{ticker.upper()} removed from watchlist'}), 200


@user_data_bp.route('/watchlists/<int:watchlist_id>/data', methods=['GET'])
@login_required
def get_watchlist_data(watchlist_id):
    """Fetch enriched stock data for all tickers in a watchlist."""
    watchlist = Watchlist.query.filter_by(id=watchlist_id, user_id=g.current_user_id).first()
    if not watchlist:
        return jsonify({'error': 'Watchlist not found'}), 404

    tickers = [item.ticker for item in watchlist.items]
    if not tickers:
        return jsonify({'stocks': [], 'count': 0})

    if len(tickers) > 50:
        return jsonify({'error': 'Watchlist exceeds 50 ticker limit'}), 400

    # SPY 1M return for relative momentum
    spy_1m_return = None
    try:
        spy_raw = yf.download(['SPY'], period='10mo', progress=False)
        spy_close = spy_raw['Close'].dropna()
        if len(spy_close) >= 22:
            spy_1m_return = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-22]) - 1) * 100
        del spy_raw
    except Exception as e:
        logger.warning('Could not fetch SPY return: %s', e)

    # Download OHLCV for all watchlist tickers
    try:
        raw = yf.download(tickers, period='10mo', group_by='ticker',
                          threads=True, progress=False)
    except Exception as e:
        logger.error('yf.download failed for watchlist: %s', e)
        return jsonify({'error': 'Failed to fetch stock data'}), 502

    # Fetch .info concurrently
    info_map = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_get_ticker_info, t): t for t in tickers}
        for future in as_completed(futures):
            try:
                t, info = future.result(timeout=5)
                if info:
                    info_map[t] = info
            except Exception:
                pass

    # Build enriched records
    stocks = []
    for t in tickers:
        try:
            if len(tickers) == 1:
                hist_df = raw.dropna(how='all')
            else:
                hist_df = raw[t].dropna(how='all')
            if hist_df.empty or len(hist_df) < 50:
                continue
        except Exception:
            continue

        record = _build_stock_data(t, info_map.get(t), hist_df, spy_1m_return)
        if record:
            stocks.append(record)

    return jsonify({'stocks': stocks, 'count': len(stocks)})


@user_data_bp.route('/watchlists/<int:watchlist_id>/data/<string:ticker>', methods=['GET'])
@login_required
def get_watchlist_ticker_data(watchlist_id, ticker):
    """Fetch enriched data for a single ticker in a watchlist."""
    ticker = ticker.upper()
    watchlist = Watchlist.query.filter_by(id=watchlist_id, user_id=g.current_user_id).first()
    if not watchlist:
        return jsonify({'error': 'Watchlist not found'}), 404

    item_tickers = [item.ticker for item in watchlist.items]
    if ticker not in item_tickers:
        return jsonify({'error': 'Ticker not in watchlist'}), 404

    # SPY 1M return for relative momentum
    spy_1m_return = None
    try:
        spy_raw = yf.download(['SPY'], period='10mo', progress=False)
        spy_close = spy_raw['Close'].dropna()
        if len(spy_close) >= 22:
            spy_1m_return = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-22]) - 1) * 100
        del spy_raw
    except Exception as e:
        logger.warning('Could not fetch SPY return: %s', e)

    # Download OHLCV for the single ticker
    try:
        raw = yf.download([ticker], period='10mo', progress=False)
    except Exception as e:
        logger.error('yf.download failed for %s: %s', ticker, e)
        return jsonify({'error': 'Failed to fetch stock data'}), 502

    # Fetch .info
    _, info = _get_ticker_info(ticker)

    try:
        hist_df = raw.dropna(how='all')
        if hist_df.empty or len(hist_df) < 50:
            return jsonify({'error': f'Insufficient data for {ticker}'}), 422
    except Exception:
        return jsonify({'error': f'Failed to process data for {ticker}'}), 422

    record = _build_stock_data(ticker, info, hist_df, spy_1m_return)
    if not record:
        return jsonify({'error': f'Could not build data for {ticker}'}), 422

    return jsonify({'stock': record})


# ── Portfolio ───────────────────────────────────────────────────────────────

@user_data_bp.route('/portfolio', methods=['GET'])
@login_required
def get_portfolio():
    holdings = PortfolioHolding.query.filter_by(user_id=g.current_user_id).all()
    return jsonify({'holdings': [h.to_dict() for h in holdings]})


@user_data_bp.route('/portfolio', methods=['POST'])
@login_required
def add_holding():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    ticker = (data.get('ticker') or '').strip().upper()
    if not ticker:
        return jsonify({'error': 'Ticker is required'}), 400

    shares = data.get('shares')
    cost_basis = data.get('cost_basis')

    if shares is None or cost_basis is None:
        return jsonify({'error': 'shares and cost_basis are required'}), 400

    try:
        shares = float(shares)
        cost_basis = float(cost_basis)
    except (ValueError, TypeError):
        return jsonify({'error': 'shares and cost_basis must be numbers'}), 400

    if shares <= 0:
        return jsonify({'error': 'shares must be positive'}), 400
    if cost_basis < 0:
        return jsonify({'error': 'cost_basis cannot be negative'}), 400

    acquired_at = None
    if data.get('acquired_at'):
        try:
            acquired_at = date.fromisoformat(data['acquired_at'])
        except ValueError:
            return jsonify({'error': 'acquired_at must be ISO date format (YYYY-MM-DD)'}), 400

    holding = PortfolioHolding(
        user_id=g.current_user_id,
        ticker=ticker,
        shares=shares,
        cost_basis=cost_basis,
        acquired_at=acquired_at,
        notes=data.get('notes'),
    )
    db.session.add(holding)
    db.session.commit()
    return jsonify({'holding': holding.to_dict()}), 201


@user_data_bp.route('/portfolio/<int:holding_id>', methods=['PUT'])
@login_required
def update_holding(holding_id):
    holding = PortfolioHolding.query.filter_by(id=holding_id, user_id=g.current_user_id).first()
    if not holding:
        return jsonify({'error': 'Holding not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    if 'shares' in data:
        try:
            shares = float(data['shares'])
        except (ValueError, TypeError):
            return jsonify({'error': 'shares must be a number'}), 400
        if shares <= 0:
            return jsonify({'error': 'shares must be positive'}), 400
        holding.shares = shares

    if 'cost_basis' in data:
        try:
            cost_basis = float(data['cost_basis'])
        except (ValueError, TypeError):
            return jsonify({'error': 'cost_basis must be a number'}), 400
        if cost_basis < 0:
            return jsonify({'error': 'cost_basis cannot be negative'}), 400
        holding.cost_basis = cost_basis

    if 'acquired_at' in data:
        if data['acquired_at']:
            try:
                holding.acquired_at = date.fromisoformat(data['acquired_at'])
            except ValueError:
                return jsonify({'error': 'acquired_at must be ISO date format (YYYY-MM-DD)'}), 400
        else:
            holding.acquired_at = None

    if 'notes' in data:
        holding.notes = data['notes']

    if 'ticker' in data:
        ticker = (data['ticker'] or '').strip().upper()
        if ticker:
            holding.ticker = ticker

    db.session.commit()
    return jsonify({'holding': holding.to_dict()})


@user_data_bp.route('/portfolio/<int:holding_id>', methods=['DELETE'])
@login_required
def delete_holding(holding_id):
    holding = PortfolioHolding.query.filter_by(id=holding_id, user_id=g.current_user_id).first()
    if not holding:
        return jsonify({'error': 'Holding not found'}), 404

    db.session.delete(holding)
    db.session.commit()
    return jsonify({'message': 'Holding removed'}), 200


# ── Settings ────────────────────────────────────────────────────────────────

@user_data_bp.route('/settings', methods=['GET'])
@login_required
def get_settings():
    settings = UserSettings.query.filter_by(user_id=g.current_user_id).first()
    if not settings:
        settings = UserSettings(user_id=g.current_user_id)
        db.session.add(settings)
        db.session.commit()
    return jsonify({'settings': settings.to_dict()})


@user_data_bp.route('/settings', methods=['PUT'])
@login_required
def update_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    settings = UserSettings.query.filter_by(user_id=g.current_user_id).first()
    if not settings:
        settings = UserSettings(user_id=g.current_user_id)
        db.session.add(settings)

    if 'default_strategy' in data:
        settings.default_strategy = data['default_strategy']

    if 'default_date_range_months' in data:
        try:
            months = int(data['default_date_range_months'])
        except (ValueError, TypeError):
            return jsonify({'error': 'default_date_range_months must be an integer'}), 400
        if months < 1 or months > 120:
            return jsonify({'error': 'default_date_range_months must be between 1 and 120'}), 400
        settings.default_date_range_months = months

    db.session.commit()
    return jsonify({'settings': settings.to_dict()})
