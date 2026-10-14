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
