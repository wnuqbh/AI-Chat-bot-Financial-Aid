from app.services.advisor import AdvisorUnavailableError
from tests.conftest import parse_sse


def _conversation(client, headers):
    return client.post("/api/chat/session", json={}, headers=headers).get_json()["conversation_id"]


def test_stream_sends_deltas_then_saves(client, register, fake_stream):
    _, headers = register()
    conversation_id = _conversation(client, headers)

    response = client.post(
        "/api/chat/message/stream", json={"conversation_id": conversation_id, "content": "Diversify?"}, headers=headers
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"

    events = parse_sse(response)
    assert [e["text"] for e in events if e["type"] == "delta"] == ["Diversification ", "spreads risk."]
    done = events[-1]
    assert done["type"] == "done"
    assert done["assistant_message"]["content"] == "Diversification spreads risk."

    messages = client.get(f"/api/chat/history/{conversation_id}", headers=headers).get_json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_stream_error_mid_reply_saves_nothing(client, register, monkeypatch):
    def _failing_stream(messages, portfolio=None):
        yield "Partial"
        raise AdvisorUnavailableError("The advisor service is unavailable")

    monkeypatch.setattr("app.routes.chat.stream_reply", _failing_stream)
    _, headers = register()
    conversation_id = _conversation(client, headers)

    response = client.post(
        "/api/chat/message/stream", json={"conversation_id": conversation_id, "content": "hi"}, headers=headers
    )
    events = parse_sse(response)
    assert events[-1] == {"type": "error", "error": "The advisor service is unavailable"}
    assert client.get(f"/api/chat/history/{conversation_id}", headers=headers).get_json()["messages"] == []


def test_stream_rejects_other_users_conversation(client, register, fake_stream):
    _, owner = register(email="owner@example.com")
    _, other = register(email="other@example.com")
    conversation_id = _conversation(client, owner)

    response = client.post(
        "/api/chat/message/stream", json={"conversation_id": conversation_id, "content": "hi"}, headers=other
    )
    assert response.status_code == 404
