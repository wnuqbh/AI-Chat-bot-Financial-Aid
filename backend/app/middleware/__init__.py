from functools import wraps

from flask import abort
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app import db
from app.models import User


def current_user_id():
    # JWT subjects must be strings; tokens are issued with str(user.id).
    return int(get_jwt_identity())


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = db.session.get(User, current_user_id())
        if user is None or not user.is_admin:
            abort(403, description="Admin access required")
        return fn(*args, **kwargs)

    return wrapper
