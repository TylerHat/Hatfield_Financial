from datetime import date
from flask import Blueprint, request, jsonify, g

from models import db, Watchlist, WatchlistItem, PortfolioHolding, UserSettings
from auth import login_required

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
