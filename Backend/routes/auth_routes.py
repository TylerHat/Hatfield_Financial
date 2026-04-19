from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User
from auth import create_token, login_required, validate_registration, validate_email

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip() or None

    error = validate_registration(username, password)
    if error:
        return jsonify({'error': error}), 400

    error = validate_email(email, required=True)
    if error:
        return jsonify({'error': error}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already taken'}), 409

    if email and User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already in use'}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        email=email,
    )
    db.session.add(user)
    db.session.commit()

    token = create_token(user.id)
    return jsonify({'token': token, 'user': user.to_dict()}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid username or password'}), 401

    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()

    token = create_token(user.id)
    return jsonify({'token': token, 'user': user.to_dict()})


@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    user = User.query.get(g.current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'user': user.to_dict()})


@auth_bp.route('/me', methods=['PATCH'])
@login_required
def update_me():
    user = User.query.get(g.current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    if 'email' not in data:
        return jsonify({'error': 'No updatable fields provided'}), 400

    new_email = (data['email'] or '').strip() or None
    err = validate_email(new_email)
    if err:
        return jsonify({'error': err}), 400

    if new_email and new_email != user.email:
        conflict = User.query.filter(User.email == new_email, User.id != user.id).first()
        if conflict:
            return jsonify({'error': 'Email already in use'}), 409

    user.email = new_email
    db.session.commit()
    return jsonify({'user': user.to_dict()})
