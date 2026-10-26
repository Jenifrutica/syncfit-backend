from fastapi.testclient import TestClient
from syncfit_database import AppOption

from app.db import get_database
from app.main import app
from app.services.options import DEFAULT_OPTIONS, ensure_default_options

client = TestClient(app)


def test_options_are_served_grouped_in_display_order():
    with TestClient(app) as started:  # runs the startup seeding
        body = started.get("/api/v1/options").json()
    assert set(body) == {"muscle_group_isolated", "muscle_group_general", "objective", "goal_phase"}
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
