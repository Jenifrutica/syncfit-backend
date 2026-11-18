"""Resumable routine generation keyed by a client ``request_id``.

The app creates the id before calling ``POST /capture`` and keeps it until the
routine arrives. If the page is reloaded or the connection drops, it asks
``GET /capture/{id}`` or sends the same POST again: a finished job returns the
stored result and a running one answers "pending", so one tap never produces
two routines.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from syncfit_database import CaptureJob, User

# A PENDING job older than this is considered dead (worker crashed) and reruns.
STALE_AFTER = timedelta(minutes=3)
# Old jobs are pruned per user so the table stays small.
KEEP_FOR = timedelta(days=2)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get(session: Session, user: User, request_id: str) -> CaptureJob | None:
    job = session.get(CaptureJob, request_id)
    if job is None or job.user_id != user.id:
        return None
    return job


def claim(session: Session, user: User, request_id: str) -> tuple[str, CaptureJob | None]:
    """Decide what to do with a request id.

    Returns ``("done", job)`` when the result exists, ``("pending", job)`` when
    another request is generating it, ``("forbidden", None)`` when the id
    belongs to someone else, and ``("run", job)`` when this request must
    generate it (the job is committed as PENDING first).
    """
    job = session.get(CaptureJob, request_id)
    if job is not None:
        if job.user_id != user.id:
            return "forbidden", None
        if job.status == "DONE":
            return "done", job
        if job.status == "PENDING" and _now() - _aware(job.updated_at) < STALE_AFTER:
            return "pending", job
        job.status, job.error, job.updated_at = "PENDING", None, _now()
        session.commit()
        return "run", job

    session.query(CaptureJob).filter(
        CaptureJob.user_id == user.id, CaptureJob.created_at < _now() - KEEP_FOR
    ).delete(synchronize_session=False)
    job = CaptureJob(request_id=request_id, user_id=user.id, status="PENDING", created_at=_now(), updated_at=_now())
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        # Two identical requests raced: the other one is generating.
        session.rollback()
        other = session.get(CaptureJob, request_id)
        if other is None or other.user_id != user.id:
            return "forbidden", None
        return ("done", other) if other.status == "DONE" else ("pending", other)
    return "run", job


def finish(job: CaptureJob, result: dict[str, Any]) -> None:
    """Attach the result; committed together with the saved routine."""
    job.result = jsonable_encoder(result)
    job.status = "DONE"
    job.updated_at = _now()


def fail(session: Session, request_id: str, error: str) -> None:
    session.rollback()
    job = session.get(CaptureJob, request_id)
    if job is not None:
        job.status, job.error, job.updated_at = "ERROR", error[:500], _now()
        session.commit()


def is_stale(job: CaptureJob) -> bool:
    return _now() - _aware(job.updated_at) >= STALE_AFTER


def serialize(job: CaptureJob) -> dict[str, Any]:
    body: dict[str, Any] = {"request_id": job.request_id, "status": job.status}
    if job.status == "DONE":
        body["result"] = job.result
    if job.status == "ERROR":
        body["error"] = job.error
    return body


__all__ = ["STALE_AFTER", "claim", "fail", "finish", "get", "is_stale", "serialize"]
