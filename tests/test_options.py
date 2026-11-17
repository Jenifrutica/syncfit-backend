from fastapi.testclient import TestClient
from syncfit_database import AppOption

from app.db import get_database
from app.main import app
from app.services.options import DEFAULT_OPTIONS, ensure_default_options

client = TestClient(app)


def test_options_are_served_grouped_in_display_order():
    with TestClient(app) as started:  # runs the startup seeding
        body = started.get("/api/v1/options").json()
    assert set(body) == {"muscle_group_isolated", "muscle_group_general", "objective", "goal_phase", "equipment"}
    assert [o["value"] for o in body["muscle_group_isolated"]][:3] == ["GLUTES", "QUADRICEPS", "HAMSTRINGS"]
    assert body["goal_phase"][0] == {
        "value": "VOLUME",
        "label": "Volume (bulk)",
        "labels": {"en": "Volume (bulk)", "es": "Volumen", "zh": "增肌期"},
    }


def test_label_follows_the_requested_language():
    with TestClient(app) as started:
        body = started.get("/api/v1/options", params={"language": "ES"}).json()
    assert body["objective"][0]["label"] == "Fuerza"


def test_seeding_is_idempotent_and_keeps_database_edits():
    with get_database().session_scope() as s:
        ensure_default_options(s)
    with get_database().session_scope() as s:
        row = s.query(AppOption).filter_by(category="objective", value="HEALTH").one()
        row.labels = {"en": "General health"}
        assert ensure_default_options(s) == 0
    with get_database().session_scope() as s:
        assert s.query(AppOption).count() == len(DEFAULT_OPTIONS)
        assert s.query(AppOption).filter_by(category="objective", value="HEALTH").one().labels == {"en": "General health"}


def test_inactive_options_are_hidden():
    with get_database().session_scope() as s:
        ensure_default_options(s)
        s.query(AppOption).filter_by(category="goal_phase", value="MAINTENANCE").one().active = False
    body = client.get("/api/v1/options").json()
    assert "MAINTENANCE" not in [o["value"] for o in body["goal_phase"]]


def _root_headers() -> dict[str, str]:
    from app.services.admin import ensure_superadmin

    with get_database().session_scope() as s:
        ensure_superadmin(s)
    from app.services.credentials import client_digest

    token = client.post("/api/v1/auth/login", json={"email": "root@syncfit.dev", "password": client_digest("root@syncfit.dev", "rootsecret123")}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_new_objective_from_the_database_drives_the_routine():
    h = _root_headers()
    created = client.post("/api/v1/admin/options", headers=h, json={
        "category": "objective", "value": "MOBILITY", "labels": {"en": "Mobility", "es": "Movilidad"},
        "meta": {"sets": 2, "reps": 15, "rest_compound": 45, "rest_iso": 30},
    })
    assert created.status_code == 200, created.text
    assert created.json()["meta"]["reps"] == 15
    try:
        routine = client.post("/api/v1/routines", json={"muscle_groups": ["GLUTES"], "objective": "MOBILITY"})
        assert routine.status_code == 200, routine.text
        from syncfit_contracts import RoutineRequest
        from app.services.routines import generate_routine

        main = generate_routine(RoutineRequest(muscle_groups=["GLUTES"], objective="MOBILITY"), engine="deterministic")["routine"]
        assert main and all(entry["reps_adapted"] == 15 for entry in main), main[:1]
        assert client.post("/api/v1/routines", json={"muscle_groups": ["GLUTES"], "objective": "NOPE"}).status_code == 422
        bad = client.post("/api/v1/admin/options", headers=h, json={"category": "objective", "value": "X", "labels": {"en": "X"}, "meta": {"sets": 0}})
        assert bad.status_code == 422
    finally:
        with get_database().session_scope() as s:
            s.query(AppOption).filter_by(category="objective", value="MOBILITY").delete()
        with get_database().session_scope() as s:
            from app.services.options import sync_engine_options
            sync_engine_options(s)


def test_goal_phase_calorie_factor_comes_from_meta():
    from app.services.options import sync_engine_options, calorie_factor

    with get_database().session_scope() as s:
        ensure_default_options(s)
        sync_engine_options(s)
    assert calorie_factor("DEFINITION") == 0.82
