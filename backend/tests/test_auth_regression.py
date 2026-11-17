import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_unauthenticated_positions_returns_401_in_prod(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "test-prod-token-xyz-1234")
    resp = client.get("/api/positions")
    assert resp.status_code == 401
    assert "Invalid or missing API Bearer token" in resp.json().get("detail", "")


def test_unauthenticated_watchlists_returns_401_in_prod(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "test-prod-token-xyz-1234")
    resp = client.get("/api/watchlists")
    assert resp.status_code == 401


def test_unauthenticated_settings_returns_401_in_prod(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "test-prod-token-xyz-1234")
    resp = client.get("/api/settings")
    assert resp.status_code == 401


def test_unauthenticated_paper_overview_returns_401_in_prod(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "test-prod-token-xyz-1234")
    resp = client.get("/api/paper-trading/prospective/overview")
    assert resp.status_code == 401


def test_wrong_token_returns_401_in_prod(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "test-prod-token-xyz-1234")
    resp = client.get("/api/positions", headers={"Authorization": "Bearer completely-wrong-token"})
    assert resp.status_code == 401
    assert "Invalid or missing API Bearer token" in resp.json().get("detail", "")


def test_valid_token_allows_access_in_prod(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "test-prod-token-xyz-1234")
    resp = client.get("/api/positions", headers={"Authorization": "Bearer test-prod-token-xyz-1234"})
    assert resp.status_code in (200, 422)  # Authorized; not 401 or 403


def test_health_endpoints_remain_public_in_prod(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "test-prod-token-xyz-1234")
    # Public probes must succeed without any Authorization header
    resp_healthz = client.get("/healthz")
    assert resp_healthz.status_code == 200
    assert resp_healthz.json().get("status") == "HEALTHY"

    resp_ping = client.get("/ping")
    assert resp_ping.status_code == 200

    resp_db = client.get("/api/health/db")
    assert resp_db.status_code in (200, 503)  # Reaches endpoint without 401 auth block


def test_production_fails_closed_when_app_token_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "app_token", "")
    resp = client.get("/api/positions")
    assert resp.status_code == 401
    assert "Production authentication is not configured" in resp.json().get("detail", "")


def test_cloud_environment_render_triggers_production_auth_gate(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "development")  # Even if env is omitted/dev!
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(settings, "app_token", "cloud-token-abc-987")

    # Because RENDER is set, settings.is_production is True -> fails closed without valid token
    resp = client.get("/api/positions")
    assert resp.status_code == 401

    # With correct token -> authorized
    resp_auth = client.get("/api/positions", headers={"Authorization": "Bearer cloud-token-abc-987"})
    assert resp_auth.status_code in (200, 422)
