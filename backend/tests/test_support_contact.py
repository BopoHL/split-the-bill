"""Whom «Contact support» in the app opens: an operator setting with a default,
served to the app without a sign-in."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    from app.routers import admin

    admin._LOGIN_ATTEMPTS.clear()


def _login(client: TestClient) -> None:
    assert client.post(
        "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
    ).status_code == 200


def test_the_operator_names_whom_contact_support_opens(client: TestClient):
    _login(client)
    assert client.get("/app-config").json() == {"support_username": "splitt_support"}

    saved = client.put("/admin/settings", json={"support_username": "@split_help"})
    assert saved.status_code == 200 and saved.json()["support_username"] == "split_help"
    assert client.get("/app-config").json() == {"support_username": "split_help"}

    assert client.put("/admin/settings", json={"support_username": "no spaces here"}).status_code == 400
    assert client.put("/admin/settings", json={"support_username": "abc"}).status_code == 400
    assert client.get("/app-config").json() == {"support_username": "split_help"}

    client.put("/admin/settings", json={"support_username": ""})
    assert client.get("/app-config").json() == {"support_username": "splitt_support"}


def test_the_app_config_needs_no_sign_in(client: TestClient):
    assert client.get("/app-config", headers={"X-Telegram-Init-Data": ""}).status_code == 200
