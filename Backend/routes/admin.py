from flask import Blueprint, jsonify, g

from models import db, User
from auth import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.asc()).all()
    return jsonify({'users': [u.to_dict() for u in users]})


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    if user_id == g.current_user_id:
        return jsonify({'error': 'Cannot delete your own account'}), 400

    target = User.query.get(user_id)
    if target is None:
        return jsonify({'error': 'User not found'}), 404

    if target.is_admin:
        return jsonify({'error': 'Cannot delete another admin'}), 403

    username = target.username
    db.session.delete(target)
    db.session.commit()
    return jsonify({'message': f'User {username} deleted'}), 200
