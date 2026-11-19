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


def test_a_share_can_only_be_revoked_by_its_owner():
    owner = _register("edge-share-owner@example.com")
    other = _register("edge-share-other@example.com")
    share = client.post(
        "/api/v1/shares", json={"role": "TRAINER", "permissions": ["PROFILE"]}, headers=_auth(owner)
    ).json()
    assert client.delete(f"/api/v1/shares/{share['token']}", headers=_auth(other)).status_code == 404
    assert client.get(f"/api/v1/shared/{share['token']}").status_code == 200
    assert client.get("/api/v1/shared/sh_does-not-exist").status_code == 404


def test_removing_a_machine_that_is_not_mine_is_404():
    token = _register("edge-machine@example.com")
    assert client.delete("/api/v1/profile/machines/not-a-machine", headers=_auth(token)).status_code == 404


def test_latest_routine_is_404_before_the_first_one():
    token = _register("edge-routine@example.com")
    assert client.get("/api/v1/routine/latest", headers=_auth(token)).status_code == 404
