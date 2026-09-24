from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_machines_endpoint():
    response = client.get("/api/v1/machines", params={"language": "ES"})
    assert response.status_code == 200
    machines = response.json()
    assert len(machines) >= 10
    leg_press = next(m for m in machines if m["id"] == "leg-press")
    assert leg_press["weight_factor"] > 1
    assert leg_press["name"]  # localized


def test_supplements_includes_daily_macros():
    response = client.get(
        "/api/v1/supplements",
        params={
            "modality": "MENSTRUAL_CYCLE",
            "language": "EN",
            "objective": "HYPERTROPHY",
            "goal_phase": "VOLUME",
            "weight_kg": 62,
            "height_cm": 165,
            "age": 29,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["daily_macros"]["kcal"] > 1200
    assert body["daily_macros"]["protein_g"] > 80
    # Ordered by safety: first item should be SAFE.
    assert body["items"][0]["safety"] == "SAFE"


def test_supplement_catalog_has_brands_and_frequency():
    response = client.get("/api/v1/supplements/catalog", params={"language": "ES"})
    assert response.status_code == 200
    catalog = response.json()
    assert len(catalog) >= 20
    whey = next(s for s in catalog if s["id"] == "whey-protein")
    assert whey["is_daily"] is True
    assert whey["frequency"] == "DAILY"
    assert whey["brand_examples"]
    burner = next(s for s in catalog if s["id"] == "fat-burner")
    assert any("Black Viper" in b for b in burner["brand_examples"])
