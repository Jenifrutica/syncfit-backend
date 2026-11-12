import zlib

import pytest
from fastapi.testclient import TestClient
from syncfit_database import AppOption, CatalogItem

from app.db import get_database
from app.main import app
from app.services.admin import ensure_superadmin
from app.services.catalog_db import ensure_catalog, load_registry
from app.services.credentials import client_digest

@pytest.fixture(scope="module")
def client():
    """Context-managed client: the lifespan seeds options and catalogs."""
    with TestClient(app) as started:
        yield started


ROOT_EMAIL = "root@syncfit.dev"
ROOT_PASSWORD = client_digest("root@syncfit.dev", "rootsecret123")

NECK_EXERCISE = {
    "id": "test-neck-curl",
    "name": {"en": "Neck curl", "es": "Curl de cuello", "zh": "颈部弯举"},
    "muscle_groups": ["NECK"],
    "equipment": "machine",
    "impact": "LOW",
    "description": {"en": "Test exercise", "es": "Ejercicio de prueba", "zh": "测试"},
    "image_url": "https://placehold.co/600x400",
    "role": "MAIN",
    "compound": False,
    "movement_pattern": "neck_curl",
    "required_equipment": ["machine"],
}


def _register(client: TestClient, email: str) -> dict:
    document_id = f"{zlib.crc32(email.encode()) % 10**10:010d}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "display_name": "Ana", "document_id": document_id},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    client.put("/api/v1/profile", json={"modality": "MENSTRUAL_CYCLE"}, headers=headers)
    return headers


def _root(client: TestClient) -> dict:
    with get_database().session_scope() as session:
        ensure_superadmin(session)
    response = client.post("/api/v1/auth/login", json={"email": ROOT_EMAIL, "password": ROOT_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _cleanup() -> None:
    with get_database().session_scope() as session:
        session.query(CatalogItem).filter_by(kind="exercise", external_id="test-neck-curl").delete()
        session.query(AppOption).filter_by(category="muscle_group_isolated", value="NECK").delete()
    with get_database().session_scope() as session:
        load_registry(session)


def test_seed_is_idempotent(client: TestClient):
    with get_database().session_scope() as session:
        assert ensure_catalog(session) == 0
        assert session.query(CatalogItem).count() >= 100


def test_muscle_groups_come_from_the_database(client: TestClient):
    groups = client.get("/api/v1/muscle-groups").json()
    assert "GLUTES" in groups and "UPPER_BODY" in groups
    with get_database().session_scope() as session:
        active = {
            value
            for (value,) in session.query(AppOption.value)
            .filter(AppOption.active.is_(True))
            .all()
        }
    assert set(groups) <= active


def test_unknown_muscle_group_is_422(client: TestClient):
    headers = _register(client, "cat-unknown@example.com")
    response = client.post("/api/v1/capture?muscle_groups=NECK", headers=headers)
    assert response.status_code == 422
    assert "NECK" in response.text


def test_admin_adds_muscle_and_exercise_then_capture_uses_them(client: TestClient):
    root = _root(client)
    headers = _register(client, "cat-add@example.com")
    try:
        option = client.post(
            "/api/v1/admin/options",
            json={
                "category": "muscle_group_isolated",
                "value": "NECK",
                "labels": {"en": "Neck", "es": "Cuello", "zh": "颈部"},
                "sort_order": 99,
            },
            headers=root,
        )
        assert option.status_code == 200, option.text
        assert "NECK" in client.get("/api/v1/muscle-groups").json()

        created = client.post("/api/v1/admin/catalog/exercise", json=NECK_EXERCISE, headers=root)
        assert created.status_code == 200, created.text
        catalog = client.get("/api/v1/catalog", params={"language": "ES"}).json()
        assert any(item["id"] == "test-neck-curl" for item in catalog)

        captured = client.post("/api/v1/capture?muscle_groups=NECK&exercises_count=1", headers=headers)
        assert captured.status_code == 200, captured.text

        off = client.patch("/api/v1/admin/catalog/exercise/test-neck-curl", json={"active": False}, headers=root)
        assert off.status_code == 200, off.text
        assert not any(item["id"] == "test-neck-curl" for item in client.get("/api/v1/catalog").json())
    finally:
        _cleanup()


def test_athlete_cannot_edit_the_catalog(client: TestClient):
    headers = _register(client, "cat-athlete@example.com")
    response = client.post("/api/v1/admin/catalog/exercise", json=NECK_EXERCISE, headers=headers)
    assert response.status_code == 403
    response = client.post(
        "/api/v1/admin/options",
        json={"category": "muscle_group_isolated", "value": "NECK", "labels": {"en": "Neck"}},
        headers=headers,
    )
    assert response.status_code == 403


def test_catalog_edit_survives_a_reseed(client: TestClient):
    root = _root(client)
    with get_database().session_scope() as session:
        row = session.query(CatalogItem).filter_by(kind="exercise", external_id="goblet-squat").one()
        original = dict(row.payload)
    try:
        edited = dict(original)
        edited["name"] = {**edited["name"], "es": "Sentadilla goblet editada"}
        saved = client.post("/api/v1/admin/catalog/exercise", json=edited, headers=root)
        assert saved.status_code == 200, saved.text
        with get_database().session_scope() as session:
            ensure_catalog(session)
        catalog = client.get("/api/v1/catalog", params={"language": "ES"}).json()
        goblet = next(item for item in catalog if item["id"] == "goblet-squat")
        assert goblet["name"] == "Sentadilla goblet editada"
    finally:
        client.post("/api/v1/admin/catalog/exercise", json=original, headers=root)
