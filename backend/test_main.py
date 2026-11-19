from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_reports_demo_mode_without_provider():
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "tradepilot-api"
    assert body["demo_mode"] is True
    assert body["data_provider"] == "not_configured"
    assert "checked_at" in body


def test_ibkr_portfolio_persists_successful_snapshot(monkeypatch):
    snapshot = {
        "account_id": "DU123",
        "base_currency": "SGD",
        "account_value": 1000,
        "available_cash": 900,
        "positions": [],
        "source": "ibkr_tws_read_only",
    }
    saved = []
    monkeypatch.setattr("backend.main.read_ibkr_portfolio", lambda: snapshot)
    monkeypatch.setattr("backend.main.sync_ibkr_portfolio", lambda payload: saved.append(payload))

    response = client.get("/api/ibkr/portfolio")

    assert response.status_code == 200
    assert response.json()["account_id"] == "DU123"
    assert saved == [snapshot]


def test_alert_status_does_not_expose_telegram_credentials():
    response = client.get("/api/alerts/status")

    assert response.status_code == 200
    body = response.json()
    assert "notifier_configured" in body
    assert "token" not in str(body).lower()
