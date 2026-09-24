from fastapi.testclient import TestClient

from app.db import get_database
from app.main import app
from app.services.admin import ensure_superadmin

client = TestClient(app)


def _login(email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json().get("access_token") if r.status_code == 200 else None


def _ensure_root():
    with get_database().session_scope() as s:
        ensure_superadmin(s)


def test_superadmin_creates_gym_admin_and_gym_flow():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    assert root
    h = {"Authorization": f"Bearer {root}"}

    created = client.post("/api/v1/admin/gym-admins", json={"email": "nico@asgard.dev", "password": "secret123", "display_name": "Nicolas"}, headers=h)
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "GYM_ADMIN"

    gymadmin = _login("nico@asgard.dev", "secret123")
    g = {"Authorization": f"Bearer {gymadmin}"}
    gym = client.post("/api/v1/gyms", json={"name": "Asgard"}, headers=g)
    assert gym.status_code == 200
    gym_id = gym.json()["id"]; code = gym.json()["code"]

    machine = client.post(f"/api/v1/gyms/{gym_id}/machines", json={"name": "Hip thrust machine", "purpose": "gluteos"}, headers=g)
    assert machine.status_code == 200
    assert client.get(f"/api/v1/gyms/{gym_id}/qr.png", headers=g).status_code == 200

    # An athlete can register and join by code.
    reg = client.post("/api/v1/auth/register", json={"email": "ana@x.dev", "password": "secret123", "display_name": "Ana"})
    assert reg.json()["user"]["role"] == "ATHLETE"
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE"}, headers=ah)
    joined = client.post("/api/v1/gyms/join", json={"code": code}, headers=ah)
    assert joined.status_code == 200


def test_athlete_cannot_create_gym_admin():
    reg = client.post("/api/v1/auth/register", json={"email": "bob@x.dev", "password": "secret123", "display_name": "Bob"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert client.post("/api/v1/admin/gym-admins", json={"email": "z@z.dev", "password": "secret123", "display_name": "Z"}, headers=h).status_code == 403
