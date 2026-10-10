def test_chat_is_rate_limited_per_user(app, client, register, fake_advisor):
    app.config["CHAT_RATE_LIMIT"] = "2 per minute"
    _, alice = register(email="alice@example.com")
    _, bob = register(email="bob@example.com")
    alice_conversation = client.post("/api/chat/session", json={}, headers=alice).get_json()["conversation_id"]
    bob_conversation = client.post("/api/chat/session", json={}, headers=bob).get_json()["conversation_id"]

    def send(headers, conversation_id):
        return client.post(
            "/api/chat/message", json={"conversation_id": conversation_id, "content": "hi"}, headers=headers
        )

    assert send(alice, alice_conversation).status_code == 201
    assert send(alice, alice_conversation).status_code == 201
    limited = send(alice, alice_conversation)
    assert limited.status_code == 429
    assert "Too many requests" in limited.get_json()["error"]

    # Another user has their own allowance.
    assert send(bob, bob_conversation).status_code == 201


def test_login_is_rate_limited_per_ip(app, client):
    app.config["AUTH_RATE_LIMIT"] = "3 per minute"
    for _ in range(3):
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever"})
    response = client.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever"})
    assert response.status_code == 429
