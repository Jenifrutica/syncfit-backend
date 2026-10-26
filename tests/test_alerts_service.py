from fastapi.testclient import TestClient

from app.analytics.alert_heap import AlertHeap
from app.main import app
from app.services.alerts import MAX_ALERTS_PER_FRAME, MAX_PENDING, dispatch_alerts

client = TestClient(app)

CALM = {"biomarkers": {"rmssd_hrv_ms": 55.0, "delta_temperature_c": 0.2, "isometric_force_loss_pct": 4.0}}
STRESSED = {"biomarkers": {"rmssd_hrv_ms": 15.0, "delta_temperature_c": 1.6, "isometric_force_loss_pct": 31.0}}


def test_calm_frame_releases_nothing():
    assert dispatch_alerts(AlertHeap(), CALM) == {"alerts": [], "alerts_pending": 0}


def test_release_is_capped_and_backlog_waits_in_the_heap():
    heap = AlertHeap()
    for _ in range(2):
        out = dispatch_alerts(heap, STRESSED)
    assert len(out["alerts"]) == MAX_ALERTS_PER_FRAME
    assert out["alerts_pending"] == 2


def test_stale_backlog_is_dropped_under_sustained_stress():
    heap = AlertHeap()
    for _ in range(100):
        out = dispatch_alerts(heap, STRESSED)
    assert out["alerts_pending"] <= MAX_PENDING


def test_telemetry_endpoint_includes_alerts(monkeypatch):
    monkeypatch.setattr("app.api.routes.evaluate_frame", lambda frame: {"k_load_multiplier": 0.8})
    response = client.post("/api/v1/telemetry", json=STRESSED)
    decision = response.json()["decision"]
    assert [a["severity"] for a in decision["alerts"]] == ["CRITICAL"] * 2
    assert decision["k_load_multiplier"] == 0.8
