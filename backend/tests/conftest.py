import pytest

from app import create_app, db
from app.models import User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def register(client):
    """Register a user and return (user_id, auth headers)."""

    def _register(email="investor@example.com", password="correct-horse", is_admin=False):
        response = client.post("/api/auth/register", json={"email": email, "password": password})
        assert response.status_code == 201, response.get_json()
        body = response.get_json()
        if is_admin:
            user = db.session.get(User, body["user"]["id"])
            user.is_admin = True
            db.session.commit()
        return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}

    return _register


@pytest.fixture
def fake_advisor(monkeypatch):
    """Replace the Gemini call with a canned reply; records what it was given."""
    calls = []

    def _fake_generate_reply(messages, portfolio=None):
        calls.append({"messages": [(m.role, m.content) for m in messages], "portfolio": portfolio})
        return "Diversification spreads risk across assets."

    monkeypatch.setattr("app.routes.chat.generate_reply", _fake_generate_reply)
    return calls


def close_request_session():
    """Mimic a real server, which closes the request's DB session before a streamed body is generated.

    The test client keeps it open, which would hide bugs where the stream relies on objects from the view.
    """
    db.session.remove()


@pytest.fixture
def fake_stream(monkeypatch):
    """Replace the streaming Gemini call with canned chunks; returns the requests it was given."""
    requests = []

    def _fake_stream_reply(gemini_request):
        close_request_session()
        requests.append(gemini_request)
        yield "Diversification "
        yield "spreads risk."

    monkeypatch.setattr("app.routes.chat.stream_reply", _fake_stream_reply)
    return requests


def parse_sse(response):
    """Decode a text/event-stream response body into a list of event dicts."""
    import json

    body = response.get_data(as_text=True)
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]
