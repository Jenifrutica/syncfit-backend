"""Exercises without an exact machine show the gym station where they are done."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.gyms import station_for_equipment
from tests.test_bulk import _athlete, _gym_admin, _root

client = TestClient(app)

ALTA = {"id": "alta", "name": {"es": "Poleas Altas"}, "name_text": "Poleas Altas", "image_url": "data:alta"}
BAJA = {"id": "baja", "name": {"es": "Poleas Bajas"}, "name_text": "Poleas Bajas", "image_url": "data:baja"}
PLANO = {"id": "plano", "name": {"es": "Banco Horizontal"}, "name_text": "Banco Horizontal"}
GRADUABLE = {"id": "grad", "name": {"es": "Banco Graduable"}, "name_text": "Banco Graduable"}
RACK = {"id": "rack", "name": {"es": "Rack de Barras"}, "name_text": "Rack de Barras"}


def test_cable_exercises_pick_high_or_low_pulley():
    stations = {"cable": [BAJA, ALTA]}
    assert station_for_equipment("triceps-pushdown", stations)["id"] == "alta"
    assert station_for_equipment("cable-lateral-raise", stations)["id"] == "baja"
    assert station_for_equipment("triceps-pushdown", {"cable": [BAJA]})["id"] == "baja"  # only one pulley


def test_bench_work_picks_flat_or_adjustable_and_prefers_specific_equipment():
    stations = {"bench": [PLANO, GRADUABLE], "barbell": [RACK]}
    assert station_for_equipment("incline-bench-press", stations)["id"] == "grad"
    assert station_for_equipment("flat-bench-press", stations)["id"] == "plano"  # bench beats the barbell rack
    assert station_for_equipment("bent-over-row", stations)["id"] == "rack"


def test_no_station_for_missing_equipment_or_unknown_exercise():
    assert station_for_equipment("triceps-pushdown", {"bench": [PLANO]}) is None
    assert station_for_equipment("does-not-exist", {"cable": [ALTA]}) is None
    assert station_for_equipment("triceps-pushdown", {}) is None


def test_capture_shows_the_gyms_high_pulley_for_a_cable_triceps_exercise():
    g = _gym_admin(_root())
    gym = client.post("/api/v1/gyms", json={"name": "Poleagym"}, headers=g).json()
    for name, key in (("Poleas Altas", "cable"), ("Poleas Bajas", "cable")):
        r = client.post(
            f"/api/v1/gyms/{gym['id']}/machines?language=ES",
            json={"name": name, "equipment_key": key, "image_url": f"data:image/png;base64,{name[-5:]}"},
            headers=g,
        )
        assert r.status_code == 200, r.text
    h = _athlete()
    assert client.post("/api/v1/gyms/join", json={"code": gym["code"]}, headers=h).status_code == 200

    found = None
    for _ in range(4):  # the engine picks among several triceps exercises
        body = client.post("/api/v1/capture", params={"muscle_groups": "TRICEPS", "use_live": "false", "exercises_count": 6}, headers=h).json()
        found = next((e for e in body["routine"] if e["exercise_id"] == "triceps-pushdown"), None)
        if found:
            break
    assert found is not None, [e["exercise_id"] for e in body["routine"]]
    assert found["machine_name"]["es"] == "Poleas Altas"
    assert found["image_url"].endswith("Altas")
