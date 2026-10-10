from functools import wraps

from flask import abort, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_limiter.util import get_remote_address

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


def user_rate_limit_key():
    """Rate-limit key: the logged-in user, falling back to the client IP."""
    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    return f"user:{identity}" if identity else get_remote_address()


def chat_rate_limit():
    return current_app.config["CHAT_RATE_LIMIT"]


def auth_rate_limit():
    return current_app.config["AUTH_RATE_LIMIT"]
