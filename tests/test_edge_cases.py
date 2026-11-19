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
