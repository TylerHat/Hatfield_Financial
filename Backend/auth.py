import jwt
import re
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import request, g, current_app, jsonify


TOKEN_EXPIRY_HOURS = 24


def create_token(user_id):
    """Create a JWT token for the given user ID."""
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def decode_token(token):
    """Decode and validate a JWT token. Returns payload dict or None."""
    try:
        return jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def login_required(f):
    """Decorator that requires a valid Bearer token. Sets g.current_user_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401

        token = auth_header[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({'error': 'Invalid or expired token'}), 401

        g.current_user_id = payload['user_id']
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator that requires a valid Bearer token from an admin user.
    Sets g.current_user_id and g.current_user."""
    from models import User  # local import to avoid circular dependency

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401

        token = auth_header[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({'error': 'Invalid or expired token'}), 401

        user = User.query.get(payload['user_id'])
        if user is None:
            return jsonify({'error': 'User not found'}), 401
        if not user.is_admin:
            return jsonify({'error': 'Admin privileges required'}), 403

        g.current_user_id = user.id
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def validate_registration(username, password):
    """Validate registration fields. Returns error string or None."""
    if not username or len(username) < 3 or len(username) > 30:
        return 'Username must be between 3 and 30 characters'

    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return 'Username can only contain letters, numbers, and underscores'

    if not password or len(password) < 8:
        return 'Password must be at least 8 characters'

    if not re.search(r'[A-Z]', password):
        return 'Password must contain at least one uppercase letter'

    if not re.search(r'[a-z]', password):
        return 'Password must contain at least one lowercase letter'

    if not re.search(r'[0-9]', password):
        return 'Password must contain at least one digit'

    return None
