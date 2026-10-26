import zlib
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from syncfit_database import SessionRecord, TelemetrySample, User

from app.db import get_database
from app.main import app

client = TestClient(app)


def _register(email: str) -> str:
    document_id = f"{zlib.crc32(email.encode()) % 10**10:010d}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "display_name": "Ana", "document_id": document_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed(email: str, readings: list[tuple[int, float]]) -> None:
    """Store (day of September 2026, rmssd) samples for the user."""
    with get_database().session() as db:
        user = db.query(User).filter_by(email=email).one()
        record = SessionRecord(user_id=user.id, modality="MENSTRUAL_CYCLE")
        db.add(record)
        db.flush()
        for day, rmssd in readings:
            db.add(
                TelemetrySample(
                    session_id=record.id,
                    timestamp=datetime(2026, 9, day, 10, tzinfo=timezone.utc),
                    delta_temperature_c=0.3,
                    rmssd_hrv_ms=rmssd,
                    isometric_force_loss_pct=5.0,
                )
            )
        db.commit()


def test_summary_over_a_range_and_weekly_windows():
    token = _register("bio1@example.com")
    _seed("bio1@example.com", [(1, 40.0), (1, 50.0), (3, 20.0), (9, 60.0)])
    response = client.get(
        "/api/v1/stats/biomarkers",
        params={"from": "2026-09-01", "to": "2026-09-10"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == {"min": 20.0, "max": 60.0, "mean": 42.5, "readings": 4}
    assert [w["from"] for w in body["windows"]] == ["2026-09-01", "2026-09-08"]
    assert body["windows"][0]["max"] == 50.0
    assert body["windows"][1]["readings"] == 1


def test_empty_range_returns_null_stats():
    token = _register("bio2@example.com")
    body = client.get(
        "/api/v1/stats/biomarkers",
        params={"from": "2026-09-01", "to": "2026-09-03"},
        headers=_auth(token),
    ).json()
    assert body["overall"] == {"min": None, "max": None, "mean": None, "readings": 0}


def test_other_users_readings_are_not_included():
    token = _register("bio3@example.com")
    _register("bio4@example.com")
    _seed("bio4@example.com", [(2, 33.0)])
    body = client.get(
        "/api/v1/stats/biomarkers",
        params={"from": "2026-09-01", "to": "2026-09-05"},
        headers=_auth(token),
    ).json()
    assert body["overall"]["readings"] == 0


def test_rejects_unknown_metric_and_reversed_range():
    token = _register("bio5@example.com")
    bad_metric = client.get("/api/v1/stats/biomarkers", params={"metric": "weight"}, headers=_auth(token))
    assert bad_metric.status_code == 422
    reversed_range = client.get(
        "/api/v1/stats/biomarkers",
        params={"from": "2026-09-10", "to": "2026-09-01"},
        headers=_auth(token),
    )
    assert reversed_range.status_code == 422


def test_requires_authentication():
    assert client.get("/api/v1/stats/biomarkers").status_code in {401, 403}
