from app.services.advisor import AdvisorUnavailableError


def _start_conversation(client, headers):
    response = client.post("/api/chat/session", json={"title": "Retirement"}, headers=headers)
    assert response.status_code == 201
    return response.get_json()["conversation_id"]


def test_send_message_stores_both_sides(client, register, fake_advisor):
    _, headers = register()
    conversation_id = _start_conversation(client, headers)

    response = client.post(
        "/api/chat/message", json={"conversation_id": conversation_id, "content": "Should I diversify?"}, headers=headers
    )
    assert response.status_code == 201
    assert fake_advisor[0]["messages"] == [("user", "Should I diversify?")]

    messages = client.get(f"/api/chat/history/{conversation_id}", headers=headers).get_json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Should I diversify?"),
        ("assistant", "Diversification spreads risk across assets."),
    ]


def test_untitled_session_is_named_after_first_message(client, register, fake_advisor):
    _, headers = register()
    conversation_id = client.post("/api/chat/session", json={}, headers=headers).get_json()["conversation_id"]
    for text in ("How do index funds work?", "Thanks"):
        client.post("/api/chat/message", json={"conversation_id": conversation_id, "content": text}, headers=headers)

    sessions = client.get("/api/chat/sessions", headers=headers).get_json()["sessions"]
    assert sessions[0]["title"] == "How do index funds work?"


def test_history_is_passed_to_advisor(client, register, fake_advisor):
    _, headers = register()
    conversation_id = _start_conversation(client, headers)
    for text in ("first", "second"):
        client.post("/api/chat/message", json={"conversation_id": conversation_id, "content": text}, headers=headers)

    assert [role for role, _ in fake_advisor[1]["messages"]] == ["user", "assistant", "user"]


def test_cannot_access_another_users_conversation(client, register, fake_advisor):
    _, owner_headers = register(email="owner@example.com")
    _, other_headers = register(email="other@example.com")
    conversation_id = _start_conversation(client, owner_headers)

    assert client.get(f"/api/chat/history/{conversation_id}", headers=other_headers).status_code == 404
    response = client.post(
        "/api/chat/message", json={"conversation_id": conversation_id, "content": "hi"}, headers=other_headers
    )
    assert response.status_code == 404


def test_advisor_failure_returns_503_and_saves_nothing(client, register, monkeypatch):
    def _fail(messages, portfolio=None):
        raise AdvisorUnavailableError("The advisor service is unavailable")

    monkeypatch.setattr("app.routes.chat.generate_reply", _fail)
    _, headers = register()
    conversation_id = _start_conversation(client, headers)

    response = client.post("/api/chat/message", json={"conversation_id": conversation_id, "content": "hi"}, headers=headers)
    assert response.status_code == 503
    assert client.get(f"/api/chat/history/{conversation_id}", headers=headers).get_json()["messages"] == []
