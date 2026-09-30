import hashlib
import zlib

from fastapi.testclient import TestClient
from syncfit_database import User

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


def test_register_login_and_me():
    token = _register("flow1@example.com")
    me = client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "flow1@example.com"

    login = client.post(
        "/api/v1/auth/login", json={"email": "flow1@example.com", "password": "secret123"}
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_duplicate_registration_rejected():
    _register("flow2@example.com")
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "flow2@example.com", "password": "secret123", "display_name": "Ana", "document_id": "2000000001"},
    )
    assert again.status_code == 409


def test_onboarding_and_cycle_tracking():
    token = _register("flow3@example.com")
    onboarding = {
        "language": "ES",
        "modality": "MENSTRUAL_CYCLE",
        "height_cm": 165,
        "weight_kg": 62,
        "objective": "HYPERTROPHY",
        "last_period_date": "2026-09-10",
        "cycle_length_days": 28,
        "loads": [{"exercise_id": "goblet-squat", "weight_kg": 20, "reps": 10}],
    }
    updated = client.put("/api/v1/profiles/me", json=onboarding, headers=_auth(token))
    assert updated.status_code == 200
    body = updated.json()
    assert body["loads"][0]["weight_kg"] == 20
    assert body["timeline"]["modality"] == "MENSTRUAL_CYCLE"
    assert body["timeline"]["cycle_day"] >= 1

    cycle = client.get("/api/v1/cycle", headers=_auth(token)).json()
    assert cycle["timeline"]["phase"] in {"MENSTRUAL", "FOLLICULAR", "OVULATORY", "LUTEAL"}


def test_capture_flow_generates_and_stores_routine():
    token = _register("flow4@example.com")
    client.put(
        "/api/v1/profiles/me",
        json={
            "language": "EN",
            "modality": "MENSTRUAL_CYCLE",
            "last_period_date": "2026-09-10",
            "cycle_length_days": 28,
            "loads": [{"exercise_id": "goblet-squat", "weight_kg": 20, "reps": 10}],
        },
        headers=_auth(token),
    )

    capture = client.post(
        "/api/v1/capture", params={"scenario": "high_risk"}, headers=_auth(token)
    )
    assert capture.status_code == 200, capture.text
    result = capture.json()
    assert result["routine"]
    order = [item["order_index"] for item in result["routine"]]
    assert order == sorted(order)  # stored in order
    assert result["phase_inferred"] == "OVULATORY"

    latest = client.get("/api/v1/routine/latest", headers=_auth(token))
    assert latest.status_code == 200
    assert latest.json()["items"]


def test_capture_requires_authentication():
    assert client.post("/api/v1/capture").status_code == 401


def test_calendar_and_machines_in_profile():
    token = _register("flow5@example.com")
    client.put(
        "/api/v1/profiles/me",
        json={
            "modality": "MENSTRUAL_CYCLE",
            "last_period_date": "2026-09-10",
            "cycle_length_days": 28,
            "body_fat_pct": 24.0,
            "daily_calories": 2100,
            "goal_phase": "VOLUME",
            "available_machines": ["leg-press", "smith-machine"],
        },
        headers=_auth(token),
    )
    me = client.get("/api/v1/profiles/me", headers=_auth(token)).json()
    assert me["goal_phase"] == "VOLUME"
    assert me["body_fat_pct"] == 24.0
    assert "leg-press" in me["available_machines"]

    calendar = client.get(
        "/api/v1/calendar", params={"month": "2026-09"}, headers=_auth(token)
    )
    assert calendar.status_code == 200
    body = calendar.json()
    assert body["month"] == "2026-09"
    assert len(body["days"]) == 30
    kinds = {day["kind"] for day in body["days"]}
    assert kinds & {"CYCLE", "OVULATION", "STRENGTH"}


def test_supplement_intake_and_stats():
    token = _register("flow6@example.com")
    client.put(
        "/api/v1/profiles/me",
        json={"modality": "MENSTRUAL_CYCLE", "weekly_training_goal": 4, "rest_days_allowance": 3},
        headers=_auth(token),
    )

    # Mark creatine as taken today.
    today = "2026-09-24"
    mark = client.post(
        "/api/v1/supplement-intakes",
        json={"supplement_id": "creatine", "date": today, "taken": True},
        headers=_auth(token),
    )
    assert mark.status_code == 200
    intakes = client.get(
        "/api/v1/supplement-intakes", params={"date": today}, headers=_auth(token)
    ).json()
    assert any(i["supplement_id"] == "creatine" and i["taken"] for i in intakes)

    # A capture creates a training session, which feeds the streak.
    client.post("/api/v1/capture", headers=_auth(token))
    stats = client.get("/api/v1/stats", headers=_auth(token)).json()
    assert stats["weekly_goal"] == 4
    assert stats["rest_days_allowance"] == 3
    assert stats["week_training_days"] >= 1


def test_share_link_flow():
    token = _register("flow7@example.com")
    client.put(
        "/api/v1/profiles/me",
        json={
            "modality": "MENSTRUAL_CYCLE",
            "last_period_date": "2026-09-10",
            "cycle_length_days": 28,
            "current_supplements": ["creatine", "whey-protein"],
            "weight_unit": "LB",
            "available_machines": ["leg-press"],
        },
        headers=_auth(token),
    )
    client.post("/api/v1/capture", headers=_auth(token))

    created = client.post(
        "/api/v1/shares",
        json={"role": "TRAINER", "label": "Coach", "permissions": ["PROFILE", "ROUTINE", "PROGRESS"]},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    share = created.json()
    assert share["token"].startswith("sh_")

    # Public endpoint, no auth.
    shared = client.get(f"/api/v1/shared/{share['token']}")
    assert shared.status_code == 200
    body = shared.json()
    assert body["role"] == "TRAINER"
    assert body["owner_display_name"]
    assert body["routine"] is not None
    assert body["profile"]["progress"]["streak_days"] >= 1
    # Not permitted sections stay null.
    assert body["machines"] is None

    listed = client.get("/api/v1/shares", headers=_auth(token)).json()
    assert any(s["token"] == share["token"] for s in listed)

    deleted = client.delete(f"/api/v1/shares/{share['token']}", headers=_auth(token))
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/shared/{share['token']}").status_code == 404


def test_share_requires_permissions():
    token = _register("flow8@example.com")
    response = client.post(
        "/api/v1/shares", json={"role": "FRIEND", "permissions": []}, headers=_auth(token)
    )
    assert response.status_code == 422


def test_duplicate_email_is_case_insensitive():
    _register("case@example.com")
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "CASE@Example.com", "password": "secret123", "display_name": "Ana", "document_id": "7700000001"},
    )

    assert again.status_code == 409
    assert again.json()["detail"] == "email already registered"


def test_login_failures_share_the_same_message():
    _register("same@example.com")
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "secret123"})
    wrong = client.post("/api/v1/auth/login", json={"email": "same@example.com", "password": "wrong-pass"})

    #verify the status code of unknow and wrong user in login
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_legacy_pbkdf2_hash_is_upgraded_on_login():

    #verify if sha256 is upgraded to aragon2 in case that DB has already registered sha256 hash
    _register("legacy@example.com")
    salt = b"0123456789abcdef"
    digest = hashlib.pbkdf2_hmac("sha256", b"secret123", salt, 200_000)
    with get_database().session_scope() as s:
        user = s.query(User).filter_by(email="legacy@example.com").one()
        user.password_hash = f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"

    login = client.post("/api/v1/auth/login", json={"email": "legacy@example.com", "password": "secret123"})
    assert login.status_code == 200
    with get_database().session_scope() as s:
        user = s.query(User).filter_by(email="legacy@example.com").one()
        assert user.password_hash.startswith("$argon2id$")
