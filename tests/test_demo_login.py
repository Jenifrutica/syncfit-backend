"""One-click demo access: off by default, and safe when enabled."""

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import func
from syncfit_database import Gym, Profile, User

from app.api import auth as auth_module
from app.db import get_database
from app.main import app
from app.services.admin import ensure_superadmin

ROOT_EMAIL = "root@syncfit.dev"
DEMO_EMAIL = "demo-athlete@example.com"
DEMO_ADMIN_EMAIL = "demo-admin@example.com"
client = TestClient(app)


def _ensure_root() -> None:
    with get_database().session_scope() as session:
        ensure_superadmin(session)


def _cleanup_user(email: str) -> None:
    with get_database().session_scope() as session:
        user = session.query(User).filter(func.lower(User.email) == email.lower()).one_or_none()
        if user is not None:
            session.query(Gym).filter_by(owner_user_id=user.id).delete()
            session.query(Profile).filter_by(user_id=user.id).delete()
            session.delete(user)


def _configure(monkeypatch, **overrides) -> None:
    # Settings is frozen; replace the object the auth routes read.
    monkeypatch.setattr(auth_module, "settings", replace(auth_module.settings, **overrides))


def test_demo_login_is_disabled_by_default(monkeypatch):
    _configure(monkeypatch, demo_login_enabled=False)
    response = client.post("/api/v1/auth/demo", json={"role": "SUPER_ADMIN"})
    assert response.status_code == 404


def test_demo_login_rejects_unknown_roles(monkeypatch):
    _configure(monkeypatch, demo_login_enabled=True)
    response = client.post("/api/v1/auth/demo", json={"role": "HACKER"})
    assert response.status_code == 422


def test_demo_login_superadmin(monkeypatch):
    _ensure_root()
    _configure(monkeypatch, demo_login_enabled=True, demo_superadmin_email=ROOT_EMAIL)
    response = client.post("/api/v1/auth/demo", json={"role": "SUPER_ADMIN"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["role"] == "SUPER_ADMIN"
    me = client.get("/api/v1/account", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == ROOT_EMAIL


def test_demo_admin_is_created_once_with_a_gym(monkeypatch):
    _cleanup_user(DEMO_ADMIN_EMAIL)
    _configure(
        monkeypatch,
        demo_login_enabled=True,
        demo_admin_email=DEMO_ADMIN_EMAIL,
        demo_admin_name="Demo Admin",
        demo_admin_gym_name="Demo Gym",
    )
    try:
        first = client.post("/api/v1/auth/demo", json={"role": "GYM_ADMIN"})
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["user"]["role"] == "GYM_ADMIN"
        assert body["user"]["display_name"] == "Demo Admin"

        second = client.post("/api/v1/auth/demo", json={"role": "GYM_ADMIN"})
        assert second.status_code == 200, second.text
        assert second.json()["user"]["id"] == body["user"]["id"]

        with get_database().session_scope() as session:
            user = session.query(User).filter(func.lower(User.email) == DEMO_ADMIN_EMAIL).one()
            gyms = session.query(Gym).filter_by(owner_user_id=user.id).all()
            assert [gym.name for gym in gyms] == ["Demo Gym"]
    finally:
        _cleanup_user(DEMO_ADMIN_EMAIL)


def test_demo_athlete_is_created_once_with_a_profile(monkeypatch):
    _cleanup_user(DEMO_EMAIL)
    _configure(
        monkeypatch,
        demo_login_enabled=True,
        demo_athlete_email=DEMO_EMAIL,
        demo_athlete_name="Nicolasa",
    )
    try:
        first = client.post("/api/v1/auth/demo", json={"role": "ATHLETE"})
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["user"]["role"] == "ATHLETE"
        assert body["user"]["display_name"] == "Nicolasa"

        second = client.post("/api/v1/auth/demo", json={"role": "ATHLETE"})
        assert second.status_code == 200, second.text
        assert second.json()["user"]["id"] == body["user"]["id"]

        with get_database().session_scope() as session:
            user = session.query(User).filter(func.lower(User.email) == DEMO_EMAIL).one()
            assert session.query(User).filter(func.lower(User.email) == DEMO_EMAIL).count() == 1
            assert session.query(Profile).filter_by(user_id=user.id).count() == 1
    finally:
        _cleanup_user(DEMO_EMAIL)

