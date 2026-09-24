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


def test_routine_has_timing_and_warmup():
    payload = {"muscle_groups": ["GLUTES", "QUADRICEPS"], "language": "ES", "exercises_count": 5}
    routine = client.post("/api/v1/routines", json=payload).json()
    assert routine["total_estimated_minutes"] > 0
    assert routine["warmup"]
    assert len(routine["routine"]) <= 5
    assert any(s["type"] == "EFFECTIVE" for s in routine["routine"][0]["sets"])
    assert "variation_pct" in routine


def test_time_budget_limits_duration():
    payload = {
        "muscle_groups": ["UPPER_BODY"],
        "language": "EN",
        "exercises_count": 6,
        "time_budget_minutes": 20,
    }
    routine = client.post("/api/v1/routines", json=payload).json()
    assert routine["total_estimated_minutes"] <= 20


def test_supplements_endpoint_pregnancy_filter():
    response = client.get(
        "/api/v1/supplements",
        params={"modality": "GESTATIONAL", "language": "ES", "objective": "GESTATIONAL_HEALTH"},
    )
    assert response.status_code == 200
    ids = {item["supplement_id"] for item in response.json()["items"]}
    assert "folate" in ids
    assert "creatine" not in ids


def test_profile_and_loads_flow():
    profile = {
        "schema_version": "1.2.0",
        "profile_id": "8a2d4e6f-1b3c-4d5e-9f70-a1b2c3d4e5f6",
        "display_name": "Ana",
        "language": "ES",
        "height_cm": 165,
        "weight_kg": 62,
        "objective": "HYPERTROPHY",
        "modality": "MENSTRUAL_CYCLE",
        "loads": [{"exercise_id": "goblet-squat", "weight_kg": 20, "reps": 10}],
    }
    assert client.post("/api/v1/profiles", json=profile).status_code == 200
    fetched = client.get("/api/v1/profiles/by-id/8a2d4e6f-1b3c-4d5e-9f70-a1b2c3d4e5f6").json()
    assert fetched["loads"][0]["weight_kg"] == 20

    routine = client.post(
        "/api/v1/routines",
        params={"profile_id": "8a2d4e6f-1b3c-4d5e-9f70-a1b2c3d4e5f6"},
        json={"muscle_groups": ["QUADRICEPS"], "language": "EN", "energy_level": "NO_ENERGY"},
    ).json()
    goblet = next((e for e in routine["routine"] if e.get("exercise_id") == "goblet-squat"), None)
    assert goblet is not None and goblet["weight_suggested_kg"] < 20  # adjusted down


def test_energy_checkin_endpoint():
    checkin = {
        "schema_version": "1.2.0",
        "timestamp": "2026-09-23T07:00:00Z",
        "energy_level": "NO_ENERGY",
        "modality": "MENSTRUAL_CYCLE",
        "day_or_week": 14,
    }
    assert client.post("/api/v1/energy", json=checkin).status_code == 200
    energy = client.get("/api/v1/energy").json()
    assert any(item["energy_level"] == "NO_ENERGY" for item in energy)

