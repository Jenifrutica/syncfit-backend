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


@pytest.mark.parametrize("port,ssl", [(587, False), (465, True)])
def test_mailer_uses_tls_login_and_sends_both_parts(monkeypatch, port, ssl):
    """The SES path: STARTTLS on 587 (SSL on 465), login with SMTP_USER/PASS, text + HTML."""
    calls: list = []

    class FakeSMTP:
        def __init__(self, host, port_, timeout):
            calls.append(("connect", host, port_, "ssl" if ssl_mode[0] else "plain"))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["From"], message.get_content_type()))

    ssl_mode = [False]

    def plain(*a, **k):
        ssl_mode[0] = False
        return FakeSMTP(*a, **k)

    def secure(*a, **k):
        ssl_mode[0] = True
        return FakeSMTP(*a, **k)

    monkeypatch.setattr(mailer.smtplib, "SMTP", plain)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", secure)
    monkeypatch.setattr(mailer, "settings", replace(
        mailer.settings, smtp_host="email-smtp.us-east-1.amazonaws.com", smtp_port=port,
        smtp_from="no-reply@mail.jenilarper.dev", smtp_user="AKIATEST", smtp_password="secret",
    ))
    mailer.send_password_reset(to="ana@example.com", name="Ana", link="https://x/recuperar/?token=t", language="ES")

    assert calls[0] == ("connect", "email-smtp.us-east-1.amazonaws.com", port, "ssl" if ssl else "plain")
    assert (("starttls",) in calls) is (not ssl)
    assert ("login", "AKIATEST", "secret") in calls
    send = calls[-1]
    assert send[0] == "send" and send[1] == "ana@example.com" and "no-reply@mail.jenilarper.dev" in send[2]
    assert send[3] == "multipart/alternative"


def test_simulated_forgot_shows_the_link_for_demo_addresses(monkeypatch):
    _register()
    _configure(monkeypatch, demo_login_enabled=True, demo_simulated_emails=(EMAIL,))
    sent: list = []
    monkeypatch.setattr(auth_module.mailer, "send_password_reset", lambda **kw: sent.append(kw))
    response = client.post("/api/v1/auth/forgot/simulated", json={"email": EMAIL.upper()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulated"] is True and body["to"] == EMAIL and body["token"]
    assert sent == []  # nothing is emailed
    # The on-screen token works like the emailed one.
    assert client.get(f"/api/v1/auth/reset/{body['token']}").json()["email"] == EMAIL
    assert client.post("/api/v1/auth/reset", json={"token": body["token"], "password": NEW_PASSWORD}).status_code == 204
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}).status_code == 200


def test_simulated_forgot_refuses_real_addresses_super_admins_and_disabled_demo(monkeypatch):
    _register()
    _configure(monkeypatch, demo_login_enabled=True, demo_simulated_emails=(EMAIL, "root@syncfit.dev"))
    assert client.post("/api/v1/auth/forgot/simulated", json={"email": "otra@example.com"}).status_code == 404
    from app.services.admin import ensure_superadmin
    with get_database().session_scope() as s:
        ensure_superadmin(s)
    assert client.post("/api/v1/auth/forgot/simulated", json={"email": "root@syncfit.dev"}).status_code == 404
    _configure(monkeypatch, demo_login_enabled=False, demo_simulated_emails=(EMAIL,))
    assert client.post("/api/v1/auth/forgot/simulated", json={"email": EMAIL}).status_code == 404
