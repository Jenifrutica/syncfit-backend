import zlib

from fastapi.testclient import TestClient

from app.main import app
from app.services import live

client = TestClient(app)

FRAME = {
    "schema_version": "1.0.0",
    "device_id": "syncfit-esp32-test",
    "session_id": "8f14e45f-ceea-467f-a1f0-1a2b3c4d5e6f",
    "timestamp": "2026-11-12T10:00:00Z",
    "modality": "MENSTRUAL_CYCLE",
    "day_or_week": 14,
    "biomarkers": {
        "delta_temperature_c": 0.31,
        "rmssd_hrv_ms": 55.0,
        "isometric_force_loss_pct": 7.5,
    },
    "ppg_window": {
        "sample_rate_hz": 100,
        "window_size": 8,
        "samples": [0.1, 0.2, -0.1, 0.3, 0.0, -0.2, 0.15, 0.05],
    },
}


def _register(email: str) -> dict:
    document_id = f"{zlib.crc32(email.encode()) % 10**10:010d}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "display_name": "Ana", "document_id": document_id},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    client.put("/api/v1/profile", json={"modality": "MENSTRUAL_CYCLE"}, headers=headers)
    return headers


def test_store_returns_recent_frame_and_expires():
    live.clear()
    assert live.latest() is None

    live.record(FRAME)
    reading = live.latest()
    assert reading is not None
    assert reading.frame["device_id"] == "syncfit-esp32-test"
    assert reading.age_seconds < 1

    assert live.latest(max_age_seconds=0) is None


def test_live_endpoint_reports_connection():
    live.clear()
    assert client.get("/api/v1/live").json()["connected"] is False

    live.record(FRAME, {"phase_inferred": "OVULATORY"})
    body = client.get("/api/v1/live").json()
    assert body["connected"] is True
    assert body["device_id"] == "syncfit-esp32-test"
    assert body["frame"]["biomarkers"]["rmssd_hrv_ms"] == 55.0
    assert body["decision"]["phase_inferred"] == "OVULATORY"


def test_capture_uses_the_live_frame():
    live.clear()
    live.record(FRAME)
    headers = _register("live1@example.com")

    captured = client.post("/api/v1/capture?muscle_groups=QUADRICEPS&exercises_count=1", headers=headers)
    assert captured.status_code == 200, captured.text
    body = captured.json()
    assert body["capture_source"] == "device"
    assert body["scenario"] == "device"
    assert body["biomarkers"]["rmssd_hrv_ms"] == 55.0
    assert body["biomarkers"]["delta_temperature_c"] == 0.31


def test_capture_falls_back_to_simulation():
    live.clear()
    headers = _register("live2@example.com")

    captured = client.post("/api/v1/capture?muscle_groups=QUADRICEPS&exercises_count=1", headers=headers)
    assert captured.status_code == 200, captured.text
    assert captured.json()["capture_source"] == "simulated"


def test_tare_requires_a_connected_device():
    headers = _register("tare-offline@example.com")
    response = client.post("/api/v1/live/tare", headers=headers)
    assert response.status_code == 503


def test_tare_sends_a_command_to_the_active_socket():
    from app.ws import routes as ws_routes

    class FakeSocket:
        def __init__(self) -> None:
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    headers = _register("tare-online@example.com")
    fake = FakeSocket()
    ws_routes._active_socket = fake
    try:
        response = client.post("/api/v1/live/tare", headers=headers)
        assert response.status_code == 202, response.text
        assert fake.sent == [{"type": "command", "action": "tare"}]
    finally:
        ws_routes._active_socket = None


def test_fast_force_channel_over_websocket():
    import time

    with client.websocket_connect("/api/v1/ws/telemetry") as ws:
        ws.send_json({"type": "force", "force_kg": 8.4, "loss_pct": 12.3})
        ws.send_json({"type": "force", "force_kg": "bad"})  # ignored, no reply
        ws.send_json(FRAME)  # a full frame still gets its prescription
        assert ws.receive_json()["type"] == "prescription"
    body = client.get("/api/v1/live").json()
    assert body["force"]["force_kg"] == 8.4 and body["force"]["loss_pct"] == 12.3
    assert body["force"]["age_seconds"] < 1.0 and body["connected"] is True

    started = time.monotonic()
    live.record_force({"force_kg": 3.0})
    assert live.latest_force().loss_pct is None
    assert live.latest_force(max_age_seconds=0.0) is None or time.monotonic() - started < 0.01


def test_live_without_force_reports_null():
    live.clear()
    assert client.get("/api/v1/live").json()["force"] is None
