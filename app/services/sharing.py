"""Sharing: create guest links and build the read-only shared profile."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from syncfit_contracts import SharedProfile, ShareLink as ShareLinkContract
from syncfit_database import Profile, Routine, ShareLink, SupplementIntake, User

from .calendar import build_calendar
from .cycles import compute_timeline
from .stats import compute_stats


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def create_share(
    session: Session,
    user: User,
    role: str,
    permissions: list[str],
    label: str | None = None,
) -> ShareLink:
    link = ShareLink(
        token="sh_" + secrets.token_urlsafe(16),
        owner_user_id=user.id,
        role=_value(role),
        label=label,
        permissions=[_value(p) for p in permissions],
        active=True,
    )
    session.add(link)
    session.flush()
    return link


def list_shares(session: Session, user: User) -> list[ShareLink]:
    return (
        session.query(ShareLink)
        .filter_by(owner_user_id=user.id)
        .order_by(ShareLink.created_at.desc())
        .all()
    )


def find_share(session: Session, token: str) -> ShareLink | None:
    return session.query(ShareLink).filter_by(token=token).one_or_none()


def delete_share(session: Session, user: User, token: str) -> bool:
    link = session.query(ShareLink).filter_by(token=token, owner_user_id=user.id).one_or_none()
    if link is None:
        return False
    session.delete(link)
    return True


def serialize_link(link: ShareLink) -> dict:
    return {
        "schema_version": "1.5.0",
        "token": link.token,
        "role": link.role,
        "label": link.label,
        "permissions": list(link.permissions or []),
        "active": link.active,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
    }


def _serialize_routine(routine: Routine | None) -> dict | None:
    if routine is None:
        return None
    return {
        "routine_id": routine.id,
        "language": routine.language,
        "muscle_groups": routine.muscle_groups,
        "total_estimated_minutes": routine.total_estimated_minutes,
        "phase_inferred": routine.phase_inferred,
        "k_load": routine.k_load,
        "items": [
            {
                "order_index": item.order_index,
                "name": item.name,
                "blocked": item.blocked,
                "series": item.series,
                "reps": item.reps,
                "weight_suggested_kg": item.weight_suggested_kg,
                "image_url": item.image_url,
            }
            for item in routine.items
        ],
    }


def build_shared_profile(
    session: Session, token: str, language: str = "EN"
) -> SharedProfile | None:
    link = session.query(ShareLink).filter_by(token=token, active=True).one_or_none()
    if link is None:
        return None
    owner = session.get(User, link.owner_user_id)
    if owner is None:
        return None
    profile = session.query(Profile).filter_by(user_id=owner.id).one_or_none()
    permissions = [_value(p) for p in (link.permissions or [])]
    allowed = set(permissions)

    result: dict = {
        "owner_display_name": owner.display_name,
        "owner_photo_url": profile.photo_url if profile is not None else None,
        "role": link.role,
        "permissions": permissions,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if "PROFILE" in allowed and profile is not None:
        result["profile"] = {
            "modality": profile.modality,
            "objective": profile.objective,
            "goal_phase": profile.goal_phase,
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "body_fat_pct": profile.body_fat_pct,
            "daily_calories": profile.daily_calories,
            "weight_unit": profile.weight_unit or "KG",
        }
        result["timeline"] = compute_timeline(profile)

    if "ROUTINE" in allowed:
        latest = (
            session.query(Routine)
            .filter_by(user_id=owner.id)
            .order_by(Routine.created_at.desc())
            .first()
        )
        result["routine"] = _serialize_routine(latest)

    if "CALENDAR" in allowed:
        calendar = build_calendar(profile, language=language)
        result["calendar"] = {"month": calendar.month, "days": [d.model_dump() for d in calendar.days]}

    if "PROGRESS" in allowed:
        progress = compute_stats(session, owner, profile)
        result["profile"] = {**(result.get("profile") or {}), "progress": progress}

    if "MACHINES" in allowed and profile is not None:
        result["machines"] = list(profile.available_machines or [])

    if "LOADS" in allowed and profile is not None:
        result["loads"] = [
            {"exercise_id": load.exercise_id, "weight_kg": load.weight_kg, "reps": load.reps}
            for load in profile.loads
        ]

    if "SUPPLEMENTS" in allowed and profile is not None:
        intakes = (
            session.query(SupplementIntake)
            .filter_by(user_id=owner.id)
            .order_by(SupplementIntake.date.desc())
            .limit(14)
            .all()
        )
        result["supplements"] = [
            {"supplement_id": sid, "current": True}
            for sid in (profile.current_supplements or [])
        ] + [
            {"supplement_id": i.supplement_id, "date": i.date.isoformat(), "taken": i.taken}
            for i in intakes
        ]

    return SharedProfile(**result)


__all__ = [
    "create_share",
    "list_shares",
    "find_share",
    "delete_share",
    "serialize_link",
    "build_shared_profile",
]
