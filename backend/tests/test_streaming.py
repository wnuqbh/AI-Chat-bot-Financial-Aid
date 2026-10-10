from app.services.advisor import AdvisorUnavailableError
from tests.conftest import close_request_session, parse_sse


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
    def _failing_stream(gemini_request):
        close_request_session()
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


def test_stream_request_includes_history_and_portfolio(client, register, fake_stream):
    _, headers = register()
    client.post("/api/portfolio/holding", json={"symbol": "VTI", "quantity": "3", "average_cost": "10"}, headers=headers)
    conversation_id = _conversation(client, headers)
    for text in ("first question", "second question"):
        client.post(
            "/api/chat/message/stream", json={"conversation_id": conversation_id, "content": text}, headers=headers
        ).get_data()

    request = fake_stream[-1]
    assert [(c.role, c.parts[0].text) for c in request["contents"]] == [
        ("user", "first question"),
        ("model", "Diversification spreads risk."),
        ("user", "second question"),
    ]
    assert "VTI: 3.000000 shares" in request["config"].system_instruction


def test_stream_with_deleted_conversation_saves_nothing(client, register, monkeypatch):
    _, headers = register()
    session = client.post("/api/chat/session", json={}, headers=headers).get_json()

    def _stream_then_delete(gemini_request):
        close_request_session()
        yield "Hi"
        client.delete(f"/api/chat/session/{session['session']['id']}", headers=headers)

    monkeypatch.setattr("app.routes.chat.stream_reply", _stream_then_delete)
    response = client.post(
        "/api/chat/message/stream", json={"conversation_id": session["conversation_id"], "content": "hi"}, headers=headers
    )
    assert parse_sse(response)[-1] == {"type": "error", "error": "This conversation was deleted"}
