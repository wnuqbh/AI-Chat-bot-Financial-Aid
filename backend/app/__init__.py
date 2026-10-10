from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

from config import config_by_name

db = SQLAlchemy()
jwt = JWTManager()


def create_app(config_name="development"):
    config_class = config_by_name[config_name]
    if hasattr(config_class, "validate"):
        config_class.validate()

    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    jwt.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"])

    from app import models  # noqa: F401  (registers tables with SQLAlchemy)
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.chat import chat_bp
    from app.routes.portfolio import portfolio_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(portfolio_bp, url_prefix="/api/portfolio")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    _register_error_handlers(app)
    return app


def _register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def handle_validation_error(err):
        return jsonify({"error": "Invalid input", "details": err.messages}), 400

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        return jsonify({"error": err.description}), err.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        app.logger.exception("Unhandled error")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return jsonify({"error": "Token has expired"}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"error": f"Invalid token: {reason}"}), 401

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"error": reason}), 401
