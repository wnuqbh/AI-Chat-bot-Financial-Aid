import pytest

from app.services import quotes


@pytest.fixture
def fake_prices(app, monkeypatch):
    app.config["QUOTES_ENABLED"] = True
    quotes.clear_cache()
    calls = []

    def _fake_fetch(symbol):
        calls.append(symbol)
        if symbol == "NOPE":
            raise ValueError("unknown symbol")
        return {"price": 100.0, "previous_close": 98.0, "currency": "USD"}

    monkeypatch.setattr(quotes, "_fetch_quote", _fake_fetch)
    yield calls
    quotes.clear_cache()


def test_quotes_endpoint_returns_prices_and_tolerates_bad_symbols(client, register, fake_prices):
    _, headers = register()
    for symbol in ("VTI", "NOPE"):
        client.post(
            "/api/portfolio/holding", json={"symbol": symbol, "quantity": "1", "average_cost": "1"}, headers=headers
        )

    body = client.get("/api/portfolio/quotes", headers=headers).get_json()
    assert body["enabled"] is True
    assert body["quotes"]["VTI"]["price"] == 100.0
    assert body["quotes"]["NOPE"] is None


def test_quotes_are_cached(app, fake_prices):
    with app.test_request_context():
        quotes.get_quotes(["VTI"])
        quotes.get_quotes(["VTI"])
    assert fake_prices == ["VTI"]


def test_quotes_disabled_returns_nothing(client, register):
    _, headers = register()
    client.post("/api/portfolio/holding", json={"symbol": "VTI", "quantity": "1", "average_cost": "1"}, headers=headers)
    assert client.get("/api/portfolio/quotes", headers=headers).get_json() == {"enabled": False, "quotes": {}}


def test_prices_are_given_to_the_advisor(app, register, fake_prices):
    from app.models import Holding, Portfolio
    from app.services.advisor import _portfolio_context

    user_id, _ = register()
    with app.test_request_context():
        portfolio = Portfolio(user_id=user_id, holdings=[Holding(symbol="VTI", quantity=2, average_cost=50)])
        assert "current price 100.0 USD" in _portfolio_context(portfolio)
