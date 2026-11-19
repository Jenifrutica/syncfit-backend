"""Several servings of a supplement in one day (e.g. two scoops of whey)."""

from fastapi.testclient import TestClient

from app.main import app
from tests.test_bulk import _athlete

client = TestClient(app)
DAY = "2026-11-19"


def _get(h):
    return {r["supplement_id"]: r for r in client.get(f"/api/v1/supplement-intakes?date={DAY}", headers=h).json()}


def test_servings_are_stored_changed_and_reset_when_unmarked():
    h = _athlete()
    r = client.post("/api/v1/supplement-intakes", json={"supplement_id": "whey-protein", "date": DAY, "taken": True}, headers=h)
    assert r.json()["servings"] == 1
    client.post("/api/v1/supplement-intakes", json={"supplement_id": "whey-protein", "date": DAY, "taken": True, "servings": 3}, headers=h)
    assert _get(h)["whey-protein"]["servings"] == 3
    # Marking again without servings keeps the count.
    client.post("/api/v1/supplement-intakes", json={"supplement_id": "whey-protein", "date": DAY, "taken": True}, headers=h)
    assert _get(h)["whey-protein"]["servings"] == 3
    # Un-marking resets it.
    client.post("/api/v1/supplement-intakes", json={"supplement_id": "whey-protein", "date": DAY, "taken": False}, headers=h)
    row = _get(h)["whey-protein"]
    assert row["taken"] is False and row["servings"] == 1


def test_servings_are_validated():
    h = _athlete()
    for bad in (0, 11, "dos"):
        r = client.post("/api/v1/supplement-intakes", json={"supplement_id": "whey-protein", "date": DAY, "taken": True, "servings": bad}, headers=h)
        assert r.status_code == 422, bad
