def test_register_and_login(client, register):
    register(email="a@example.com", password="password123")

    response = client.post("/api/auth/login", json={"email": "A@example.com", "password": "password123"})
    assert response.status_code == 200
    assert "access_token" in response.get_json()


def test_register_duplicate_email(client, register):
    register(email="a@example.com")
    response = client.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 409


def test_register_validates_input(client):
    response = client.post("/api/auth/register", json={"email": "not-an-email", "password": "short"})
    assert response.status_code == 400
    assert set(response.get_json()["details"]) == {"email", "password"}


def test_account_locks_after_repeated_failures(client, register, app):
    register(email="a@example.com", password="password123")
    for _ in range(app.config["MAX_FAILED_LOGINS"]):
        assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong"}).status_code == 401

    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 403


def test_protected_route_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}
