from flask import Blueprint, jsonify, g, request

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


@admin_bp.route('/users/<int:user_id>/role', methods=['PATCH'])
@admin_required
def update_user_role(user_id):
    if user_id == g.current_user_id:
        return jsonify({'error': 'You cannot change your own admin status'}), 400

    target = User.query.get(user_id)
    if target is None:
        return jsonify({'error': 'User not found'}), 404

    body = request.get_json(silent=True)
    if body is None or 'is_admin' not in body:
        return jsonify({'error': 'Request body must include "is_admin" (boolean)'}), 400
    if not isinstance(body['is_admin'], bool):
        return jsonify({'error': '"is_admin" must be a boolean'}), 400

    target.is_admin = body['is_admin']
    db.session.commit()

    action = 'granted admin to' if target.is_admin else 'revoked admin from'
    return jsonify({
        'message': f'Successfully {action} {target.username}',
        'user': target.to_dict(),
    }), 200
