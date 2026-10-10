from flask_migrate import check, upgrade

from app import create_app
from config import TestingConfig


def test_migrations_build_the_current_schema(tmp_path, monkeypatch):
    """Fails if a model changed without a matching migration (run `flask --app main db migrate`)."""
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{tmp_path / 'migrated.db'}")
    app = create_app("testing")
    with app.app_context():
        upgrade()
        check()  # raises if the models and the migrated schema differ
