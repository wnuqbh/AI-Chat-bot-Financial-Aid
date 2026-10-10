def test_add_update_delete_holding(client, register):
    _, headers = register()

    response = client.post(
        "/api/portfolio/holding", json={"symbol": "vti", "quantity": "10", "average_cost": "220.50"}, headers=headers
    )
    assert response.status_code == 201
    holding = response.get_json()["holding"]
    assert holding["symbol"] == "VTI"

    response = client.put(
        f"/api/portfolio/holding/{holding['id']}", json={"quantity": "12", "average_cost": "225"}, headers=headers
    )
    assert response.status_code == 200
    assert response.get_json()["holding"]["quantity"].startswith("12")

    assert client.delete(f"/api/portfolio/holding/{holding['id']}", headers=headers).status_code == 204
    assert client.get("/api/portfolio/", headers=headers).get_json()["portfolio"]["holdings"] == []


def test_duplicate_symbol_conflicts(client, register):
    _, headers = register()
    payload = {"symbol": "VTI", "quantity": "1", "average_cost": "1"}
    client.post("/api/portfolio/holding", json=payload, headers=headers)
    assert client.post("/api/portfolio/holding", json=payload, headers=headers).status_code == 409


def test_cannot_modify_another_users_holding(client, register):
    _, owner_headers = register(email="owner@example.com")
    _, other_headers = register(email="other@example.com")
    holding_id = client.post(
        "/api/portfolio/holding", json={"symbol": "VTI", "quantity": "1", "average_cost": "1"}, headers=owner_headers
    ).get_json()["holding"]["id"]

    assert client.delete(f"/api/portfolio/holding/{holding_id}", headers=other_headers).status_code == 404


def test_portfolio_is_given_to_advisor(client, register, fake_advisor):
    _, headers = register()
    client.post("/api/portfolio/holding", json={"symbol": "VTI", "quantity": "1", "average_cost": "1"}, headers=headers)
    conversation_id = client.post("/api/chat/session", json={}, headers=headers).get_json()["conversation_id"]
    client.post("/api/chat/message", json={"conversation_id": conversation_id, "content": "hi"}, headers=headers)

    assert [h.symbol for h in fake_advisor[0]["portfolio"].holdings] == ["VTI"]
