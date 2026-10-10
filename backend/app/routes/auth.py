import bcrypt
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required

from app import db
from app.middleware import current_user_id
from app.models import User
from app.schemas import LoginSchema, RegisterSchema
from app.services.audit import record_audit

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    data = RegisterSchema().load(request.get_json(silent=True) or {})
    email = data["email"].lower()

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email is already registered"}), 409

    password_hash = bcrypt.hashpw(
        data["password"].encode(), bcrypt.gensalt(rounds=current_app.config["BCRYPT_ROUNDS"])
    ).decode()
    user = User(email=email, password_hash=password_hash, full_name=data.get("full_name"))
    db.session.add(user)
    db.session.flush()
    record_audit("register", user_id=user.id)
    db.session.commit()

    return jsonify({"user": user.to_dict(), "access_token": create_access_token(identity=str(user.id))}), 201


@auth_bp.post("/login")
def login():
    data = LoginSchema().load(request.get_json(silent=True) or {})
    user = User.query.filter_by(email=data["email"].lower()).first()

    if user is not None and user.account_locked:
        record_audit("login_blocked_locked", user_id=user.id)
        db.session.commit()
        return jsonify({"error": "Account is locked"}), 403

    if user is None or not bcrypt.checkpw(data["password"].encode(), user.password_hash.encode()):
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= current_app.config["MAX_FAILED_LOGINS"]:
                user.account_locked = True
            record_audit("login_failed", user_id=user.id)
            db.session.commit()
        return jsonify({"error": "Invalid email or password"}), 401

    user.failed_login_attempts = 0
    record_audit("login", user_id=user.id)
    db.session.commit()
    return jsonify({"user": user.to_dict(), "access_token": create_access_token(identity=str(user.id))})


@auth_bp.get("/me")
@jwt_required()
def me():
    user = db.get_or_404(User, current_user_id())
    return jsonify({"user": user.to_dict()})
