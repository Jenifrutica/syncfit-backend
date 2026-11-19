"""Edge cases of existing endpoints: bad input and other users' data."""

import zlib

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register(email: str) -> str:
    document_id = f"{zlib.crc32(email.encode()) % 10**10:010d}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "display_name": "Eva", "document_id": document_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_profile_requires_a_valid_token():
    assert client.get("/api/v1/profile").status_code == 401
    assert client.get("/api/v1/profile", headers=_auth("not-a-jwt")).status_code == 401


def test_energy_rejects_an_unknown_level():
    checkin = {
        "schema_version": "1.2.0",
        "timestamp": "2026-09-23T07:00:00Z",
        "energy_level": "HYPER",
        "modality": "MENSTRUAL_CYCLE",
        "day_or_week": 3,
    }
    assert client.post("/api/v1/energy", json=checkin).status_code == 422


def test_unknown_gym_code_is_404_and_athletes_cannot_create_gyms():
    token = _register("edge-gym@example.com")
    assert client.post("/api/v1/gyms/join", json={"code": "ZZ9999"}, headers=_auth(token)).status_code == 404
    assert client.get("/api/v1/gyms/ZZ9999", headers=_auth(token)).status_code == 404
    assert client.post("/api/v1/gyms", json={"name": "Mine"}, headers=_auth(token)).status_code == 403
