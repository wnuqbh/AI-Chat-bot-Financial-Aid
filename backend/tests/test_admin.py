def test_non_admin_is_forbidden(client, register):
    _, headers = register()
    assert client.get("/api/admin/users", headers=headers).status_code == 403


def test_admin_lists_users_and_audit_logs(client, register):
    register(email="user@example.com")
    _, admin_headers = register(email="admin@example.com", is_admin=True)

    users = client.get("/api/admin/users", headers=admin_headers).get_json()
    assert users["total"] == 2

    logs = client.get("/api/admin/audit-logs?action=register", headers=admin_headers).get_json()
    assert logs["total"] == 2


def test_admin_unlocks_account(client, register, app):
    user_id, _ = register(email="user@example.com", password="password123")
    _, admin_headers = register(email="admin@example.com", is_admin=True)
    for _ in range(app.config["MAX_FAILED_LOGINS"]):
        client.post("/api/auth/login", json={"email": "user@example.com", "password": "wrong"})

    assert client.post(f"/api/admin/users/{user_id}/unlock", headers=admin_headers).status_code == 200
    response = client.post("/api/auth/login", json={"email": "user@example.com", "password": "password123"})
    assert response.status_code == 200
