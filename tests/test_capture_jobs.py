"""Resumable routine generation: one request_id never produces two routines."""

import threading
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from syncfit_database import CaptureJob, Routine, User

from app.api import routes as routes_module
from app.db import get_database
from app.main import app
from tests.test_bulk import _athlete

client = TestClient(app)


def _rid() -> str:
    return "rq-" + uuid.uuid4().hex


def _routines(headers) -> int:
    me = client.get("/api/v1/account", headers=headers).json()["id"]
    with get_database().session_scope() as s:
        return s.query(Routine).filter_by(user_id=me).count()


def _capture(headers, rid, **params):
    return client.post("/api/v1/capture", params={"language": "ES", "muscle_groups": "GLUTES", "request_id": rid, **params}, headers=headers)


def test_same_request_id_returns_the_stored_routine():
    h = _athlete()
    rid = _rid()
    first = _capture(h, rid)
    assert first.status_code == 200, first.text
    before = _routines(h)
    again = _capture(h, rid)
    assert again.status_code == 200
    assert again.json()["routine"] == first.json()["routine"]
    assert _routines(h) == before  # no second routine saved

    status = client.get(f"/api/v1/capture/{rid}", headers=h).json()
    assert status["status"] == "DONE" and status["result"]["routine"] == first.json()["routine"]


def test_request_id_is_private_to_its_owner():
    a, b = _athlete(), _athlete()
    rid = _rid()
    assert _capture(a, rid).status_code == 200
    assert _capture(b, rid).status_code == 409
    assert client.get(f"/api/v1/capture/{rid}", headers=b).status_code == 404
    assert client.get(f"/api/v1/capture/{rid}").status_code == 401


def test_pending_job_answers_409_and_stale_job_reruns():
    h = _athlete()
    me = client.get("/api/v1/account", headers=h).json()["id"]
    rid = _rid()
    with get_database().session_scope() as s:
        s.add(CaptureJob(request_id=rid, user_id=me, status="PENDING"))
    busy = _capture(h, rid)
    assert busy.status_code == 409 and busy.json()["detail"]["status"] == "pending"
    assert client.get(f"/api/v1/capture/{rid}", headers=h).json()["status"] == "PENDING"

    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    with get_database().session_scope() as s:
        s.get(CaptureJob, rid).updated_at = old
    assert client.get(f"/api/v1/capture/{rid}", headers=h).json()["status"] == "STALE"
    rerun = _capture(h, rid)
    assert rerun.status_code == 200 and rerun.json()["routine"]


def test_failed_generation_is_marked_and_can_be_retried(monkeypatch):
    h = _athlete()
    rid = _rid()
    real = routes_module.capture
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("engine down")
        return real(*args, **kwargs)

    monkeypatch.setattr(routes_module, "capture", flaky)
    failing = TestClient(app, raise_server_exceptions=False)
    assert failing.post("/api/v1/capture", params={"muscle_groups": "GLUTES", "request_id": rid}, headers=h).status_code == 500
    status = client.get(f"/api/v1/capture/{rid}", headers=h).json()
    assert status["status"] == "ERROR" and "engine down" in status["error"]
    assert _routines(h) == 0  # nothing half-saved
    retry = _capture(h, rid)
    assert retry.status_code == 200 and calls["n"] == 2


def test_two_simultaneous_taps_create_one_routine():
    h = _athlete()
    rid = _rid()
    results: list[int] = []

    def tap():
        results.append(_capture(h, rid).status_code)

    threads = [threading.Thread(target=tap) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(200) >= 1
    assert set(results) <= {200, 409}
    assert _routines(h) == 1


def test_invalid_request_id_is_rejected_and_unknown_is_404():
    h = _athlete()
    assert _capture(h, "x").status_code == 422
    assert _capture(h, "bad id with spaces").status_code == 422
    assert client.get(f"/api/v1/capture/{_rid()}", headers=h).status_code == 404


def test_capture_without_request_id_still_works():
    h = _athlete()
    r = client.post("/api/v1/capture", params={"muscle_groups": "GLUTES"}, headers=h)
    assert r.status_code == 200 and r.json()["routine"]
