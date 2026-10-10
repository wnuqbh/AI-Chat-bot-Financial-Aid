import os

import click
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config_by_name

db = SQLAlchemy()
jwt = JWTManager()
# render_as_batch lets future migrations alter columns on SQLite, which lacks most ALTER TABLE support.
migrate = Migrate(render_as_batch=True)
# Limits are applied per route with @limiter.limit; storage comes from RATELIMIT_STORAGE_URI.
limiter = Limiter(key_func=get_remote_address)


def create_app(config_name=None):
    config_class = config_by_name[config_name or os.getenv("FLASK_ENV", "development")]
    if hasattr(config_class, "validate"):
        config_class.validate()

    app = Flask(__name__)
    app.config.from_object(config_class)
    if app.config["TRUSTED_PROXY_COUNT"]:
        # Behind nginx or a hosting platform's load balancer, take the client IP from X-Forwarded-For
        # so per-IP rate limits and audit logs see real clients rather than the proxy.
        n = app.config["TRUSTED_PROXY_COUNT"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
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
    @limiter.exempt
    def health():
        return jsonify({"status": "ok"})

    _register_error_handlers(app)
    _register_commands(app)
    return app


def _register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def handle_validation_error(err):
        return jsonify({"error": "Invalid input", "details": err.messages}), 400

    @app.errorhandler(429)
    def handle_rate_limited(err):
        return jsonify({"error": f"Too many requests ({err.description}). Please wait a moment and try again."}), 429

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


def _register_commands(app):
    @app.cli.command("make-admin")
    @click.argument("email")
    @click.option("--revoke", is_flag=True, help="Remove admin rights instead of granting them.")
    def make_admin(email, revoke):
        """Grant (or revoke) admin rights for the user with EMAIL."""
        from app.models import User

        user = User.query.filter_by(email=email.lower()).first()
        if user is None:
            raise click.ClickException(f"No user with email {email}")
        user.is_admin = not revoke
        db.session.commit()
        click.echo(f"{user.email} is {'no longer' if revoke else 'now'} an admin.")
