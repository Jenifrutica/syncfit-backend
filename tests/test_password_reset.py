"""Forgot/reset password: token lifecycle and the email hook."""

from __future__ import annotations

import zlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from syncfit_database import PasswordResetToken, Profile, User

from app.api import auth as auth_module
from app.db import get_database
from app.main import app
from app.services import mailer

client = TestClient(app)
EMAIL = "reset-flow@example.com"
OLD_PASSWORD = "secret123"
NEW_PASSWORD = "Nueva123!"


@pytest.fixture(autouse=True)
def _clean():
    _cleanup()
    yield
    _cleanup()


def _cleanup() -> None:
    with get_database().session_scope() as session:
        user = session.query(User).filter(func.lower(User.email) == EMAIL).one_or_none()
        if user is not None:
            session.query(PasswordResetToken).filter_by(user_id=user.id).delete()
            session.query(Profile).filter_by(user_id=user.id).delete()
            session.delete(user)


def _configure(monkeypatch, **overrides) -> None:
    patched = replace(auth_module.settings, **overrides)
    monkeypatch.setattr(auth_module, "settings", patched)
    monkeypatch.setattr(mailer, "settings", replace(mailer.settings, **overrides))


def _register() -> None:
    document_id = f"{zlib.crc32(EMAIL.encode()) % 10**10:010d}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": OLD_PASSWORD, "display_name": "Reset", "document_id": document_id},
    )
    assert response.status_code == 201, response.text


def test_full_reset_flow(monkeypatch):
    _register()
    sent: list[dict] = []
    monkeypatch.setattr(
        auth_module.mailer,
        "send_password_reset",
        lambda **kwargs: sent.append(kwargs),
    )
    _configure(
        monkeypatch,
        smtp_host="smtp.test",
        smtp_from="no-reply@test.dev",
        app_base_url="https://app.test",
        password_reset_minutes=30,
    )

    forgot = client.post("/api/v1/auth/forgot", json={"email": EMAIL})
    assert forgot.status_code == 202, forgot.text
    assert len(sent) == 1
    link = sent[0]["link"]
    assert link.startswith("https://app.test/recuperar/?token=")
    token = link.rsplit("token=", 1)[1]

    valid = client.get(f"/api/v1/auth/reset/{token}")
    assert valid.status_code == 200
    assert valid.json() == {"valid": True, "email": EMAIL}

    weak = client.post("/api/v1/auth/reset", json={"token": token, "password": "abc"})
    assert weak.status_code == 422

    reset = client.post("/api/v1/auth/reset", json={"token": token, "password": NEW_PASSWORD})
    assert reset.status_code == 204, reset.text

    # The token is single use.
    assert client.get(f"/api/v1/auth/reset/{token}").status_code == 404
    assert client.post("/api/v1/auth/reset", json={"token": token, "password": "Otra123!"}).status_code == 404

    old = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD})
    assert old.status_code == 401
    new = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
    assert new.status_code == 200


def test_forgot_does_not_reveal_unknown_accounts(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(auth_module.mailer, "send_password_reset", lambda **kwargs: sent.append(kwargs))
    _configure(monkeypatch, smtp_host="smtp.test", smtp_from="no-reply@test.dev")
    response = client.post("/api/v1/auth/forgot", json={"email": "nadie@example.com"})
    assert response.status_code == 202
    assert sent == []


def test_forgot_stays_generic_when_delivery_fails(monkeypatch):
    _register()

    def boom(**_kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(auth_module.mailer, "send_password_reset", boom)
    _configure(monkeypatch, smtp_host="smtp.test", smtp_from="no-reply@test.dev")
    response = client.post("/api/v1/auth/forgot", json={"email": EMAIL})
    assert response.status_code == 202


def test_forgot_requires_a_configured_mailer(monkeypatch):
    _configure(monkeypatch, smtp_host=None, smtp_from=None)
    response = client.post("/api/v1/auth/forgot", json={"email": EMAIL})
    assert response.status_code == 503


def test_issuing_a_new_token_invalidates_the_previous_one(monkeypatch):
    _register()
    sent: list[dict] = []
    monkeypatch.setattr(auth_module.mailer, "send_password_reset", lambda **kwargs: sent.append(kwargs))
    _configure(monkeypatch, smtp_host="smtp.test", smtp_from="no-reply@test.dev")

    client.post("/api/v1/auth/forgot", json={"email": EMAIL})
    client.post("/api/v1/auth/forgot", json={"email": EMAIL})
    first = sent[0]["link"].rsplit("token=", 1)[1]
    second = sent[1]["link"].rsplit("token=", 1)[1]
    assert client.get(f"/api/v1/auth/reset/{first}").status_code == 404
    assert client.get(f"/api/v1/auth/reset/{second}").status_code == 200
