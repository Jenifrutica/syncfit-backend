from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_muscle_groups_endpoint():
    response = client.get("/api/v1/muscle-groups")
    assert response.status_code == 200
    groups = response.json()
    assert "GLUTES" in groups
    assert "UPPER_BODY" in groups
    assert "FULL_LEG" in groups


def test_catalog_endpoint_localizes_names():
    response = client.get("/api/v1/catalog", params={"language": "ES"})
    assert response.status_code == 200
    catalog = response.json()
    assert len(catalog) >= 20
    goblet = next(item for item in catalog if item["id"] == "goblet-squat")
    assert goblet["name"] == "Sentadilla goblet"
    assert goblet["image_url"].startswith("https://")


def test_create_routine_default_engine():
    payload = {
        "schema_version": "1.1.0",
        "muscle_groups": ["GLUTES", "QUADRICEPS"],
        "language": "ES",
        "exercises_per_group": 1,
    }
    response = client.post("/api/v1/routines", json=payload)
    assert response.status_code == 200
    routine = response.json()
    assert routine["language"] == "ES"
    assert len(routine["routine"]) >= 1
    entry = routine["routine"][0]
    assert entry["image_url"].startswith("https://")
    assert entry["description"]["es"]


def test_create_routine_rejects_unknown_group():
    response = client.post(
        "/api/v1/routines",
        json={"muscle_groups": ["NOT_A_GROUP"], "language": "EN"},
    )
    assert response.status_code == 422


def test_ai_engine_without_reasoning_returns_503():
    response = client.post(
        "/api/v1/routines",
        params={"engine": "ai"},
        json={"muscle_groups": ["GLUTES"], "language": "EN"},
    )
    assert response.status_code in (502, 503)
