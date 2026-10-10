import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _env(name, default=None):
    # Treat blank lines like "JWT_SECRET_KEY=" in .env as unset, so the default still applies.
    return os.getenv(name) or default


def _database_url(default):
    url = _env("DATABASE_URL", default)
    # Supabase/Heroku hand out postgres:// URLs; SQLAlchemy needs the psycopg 3 driver named explicitly.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Config:
    SECRET_KEY = _env("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = _env("JWT_SECRET_KEY", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    SQLALCHEMY_DATABASE_URI = _database_url("sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = _env("CORS_ORIGINS", "http://localhost:5173").split(",")

    BCRYPT_ROUNDS = 12
    MAX_FAILED_LOGINS = 5

    GEMINI_API_KEY = _env("GEMINI_API_KEY")
    GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-flash")
    # Gemini 2.5 models count internal "thinking" tokens against this limit, so it needs headroom.
    GEMINI_MAX_OUTPUT_TOKENS = int(_env("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
    # Older messages are dropped so long conversations stay within the model's context.
    CHAT_HISTORY_LIMIT = 20


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False

    @classmethod
    def validate(cls):
        missing = [name for name in ("JWT_SECRET_KEY", "SECRET_KEY", "DATABASE_URL") if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Missing required environment variables for production: {', '.join(missing)}")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-jwt-secret-at-least-32-bytes-long"
    BCRYPT_ROUNDS = 4
    GEMINI_API_KEY = "test-key"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
