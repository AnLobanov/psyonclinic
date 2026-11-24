from fastapi.testclient import TestClient

from doctor_compare import main
from doctor_compare.config import Settings
from doctor_compare.models import Doctor
from doctor_compare.sources import SourceError


def test_load_refresh_and_failed_refresh_preserves_report(monkeypatch):
    count = 0

    async def medical(_client, _settings):
        nonlocal count
        count += 1
        if count == 3:
            raise SourceError("Medical API временно недоступен.")
        return [Doctor(id="a", name="Иванов Иван Иванович", experience=count)], 1

    async def catalog(_client):
        return [], 1

    monkeypatch.setattr(main, "load_medical", medical)
    monkeypatch.setattr(main, "load_catalog", catalog)
    with TestClient(main.create_app(Settings(medical_api_key="test-key"))) as client:
        first = client.get("/api/comparison")
        assert first.status_code == 200
        assert first.headers["Cache-Control"] == "no-store"
        assert first.json()["rows"][0]["medical"]["experience"] == 1
        assert "test-key" not in first.text
        assert client.get("/api/comparison").json() == first.json()

        refreshed = client.post("/api/comparison/refresh")
        assert refreshed.json()["rows"][0]["medical"]["experience"] == 2
        assert client.post("/api/comparison/refresh").status_code == 502
        assert client.get("/api/comparison").json() == refreshed.json()


def test_missing_key_returns_useful_error():
    with TestClient(main.create_app(Settings(medical_api_key=""))) as client:
        response = client.get("/api/comparison")
    assert response.status_code == 503
    assert "MEDICAL_API_KEY" in response.json()["detail"]
