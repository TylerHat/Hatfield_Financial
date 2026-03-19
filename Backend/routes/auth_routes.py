from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User
from auth import create_token, login_required, validate_registration

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    error = validate_registration(username, password)
    if error:
        return jsonify({'error': error}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already taken'}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
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

    token = create_token(user.id)
    return jsonify({'token': token, 'user': user.to_dict()})


@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    user = User.query.get(g.current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'user': user.to_dict()})
