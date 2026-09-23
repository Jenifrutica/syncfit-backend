import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SESSION_ID = "3f1b2c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"

FRAME = {
    "schema_version": "1.0.0",
    "device_id": "test-device",
    "session_id": SESSION_ID,
    "timestamp": "2026-09-21T13:24:05Z",
    "modality": "MENSTRUAL_CYCLE",
    "day_or_week": 14,
    "biomarkers": {
        "delta_temperature_c": 0.42,
        "rmssd_hrv_ms": 28.5,
        "isometric_force_loss_pct": 12.8,
    },
    "ppg_window": {
        "sample_rate_hz": 100,
        "window_size": 8,
        "samples": [0.1, 0.2, -0.1, 0.3, 0.0, -0.2, 0.15, 0.05],
    },
}


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ingest_telemetry_returns_decision():
    response = client.post("/api/v1/telemetry", json=FRAME)
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["phase_inferred"] == "OVULATORY"
    assert 0.70 <= decision["k_load_multiplier"] <= 1.05


def test_ingest_invalid_frame_is_rejected():
    bad = dict(FRAME)
    bad["biomarkers"] = {"delta_temperature_c": 99.0, "rmssd_hrv_ms": 28.5, "isometric_force_loss_pct": 12.8}
    response = client.post("/api/v1/telemetry", json=bad)
    assert response.status_code == 422


def test_telemetry_websocket_roundtrip():
    with client.websocket_connect("/api/v1/ws/telemetry") as websocket:
        websocket.send_json({"type": "telemetry", "payload": FRAME})
        message = websocket.receive_json()
        assert message["type"] == "prescription"
        assert "k_load_multiplier" in message["payload"]
