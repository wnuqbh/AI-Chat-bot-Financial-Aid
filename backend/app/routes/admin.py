from flask import Blueprint, jsonify, request

from app import db
from app.middleware import admin_required, current_user_id
from app.models import AuditLog, User
from app.services.audit import record_audit

admin_bp = Blueprint("admin", __name__)


def _page_args():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 50, type=int), 1), 200)
    return page, per_page


@admin_bp.get("/users")
@admin_required
def list_users():
    page, per_page = _page_args()
    result = db.paginate(db.select(User).order_by(User.id), page=page, per_page=per_page)
    return jsonify({"users": [u.to_dict() for u in result.items], "total": result.total, "page": page})


@admin_bp.post("/users/<int:user_id>/unlock")
@admin_required
def unlock_user(user_id):
    user = db.get_or_404(User, user_id, description="User not found")
    user.account_locked = False
    user.failed_login_attempts = 0
    record_audit("account_unlocked", user_id=current_user_id(), details=f"user {user.id}")
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@admin_bp.get("/audit-logs")
@admin_required
def audit_logs():
    page, per_page = _page_args()
    query = db.select(AuditLog).order_by(AuditLog.id.desc())
    if user_id := request.args.get("user_id", type=int):
        query = query.filter_by(user_id=user_id)
    if action := request.args.get("action"):
        query = query.filter_by(action=action)
    result = db.paginate(query, page=page, per_page=per_page)
    return jsonify({"audit_logs": [log.to_dict() for log in result.items], "total": result.total, "page": page})
