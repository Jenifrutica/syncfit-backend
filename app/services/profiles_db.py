"""Profile persistence for the onboarding and settings flow."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session
from syncfit_database import ExerciseLoad, Profile, User

_SCALAR_FIELDS = (
    "language",
    "height_cm",
    "weight_kg",
    "body_fat_pct",
    "daily_calories",
    "age",
    "objective",
    "goal_phase",
    "modality",
    "cycle_length_days",
    "gestation_week",
    "weekly_training_goal",
    "rest_days_allowance",
    "weight_unit",
    "photo_url",
    "symptom_notes",
)


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def upsert_profile(session: Session, user: User, data: dict[str, Any]) -> Profile:
    profile = session.query(Profile).filter_by(user_id=user.id).one_or_none()
    if profile is None:
        profile = Profile(user_id=user.id)
        session.add(profile)

    for field in _SCALAR_FIELDS:
        if field in data and data[field] is not None:
            setattr(profile, field, data[field])

    if "last_period_date" in data:
        profile.last_period_date = _as_date(data["last_period_date"])
    if "due_date" in data:
        profile.due_date = _as_date(data["due_date"])
    if "available_machines" in data and data["available_machines"] is not None:
        profile.available_machines = list(data["available_machines"])
    if "symptoms" in data and data["symptoms"] is not None:
        profile.symptoms = list(data["symptoms"])
    if "pain_levels" in data and data["pain_levels"] is not None:
        profile.pain_levels = dict(data["pain_levels"])
    if "current_supplements" in data and data["current_supplements"] is not None:
        profile.current_supplements = list(data["current_supplements"])
    if "supplement_macros" in data and data["supplement_macros"] is not None:
        profile.supplement_macros = list(data["supplement_macros"])

    if "loads" in data and data["loads"] is not None:
        profile.loads.clear()
        for load in data["loads"]:
            profile.loads.append(
                ExerciseLoad(
                    exercise_id=load["exercise_id"],
                    weight_kg=float(load.get("weight_kg", 0.0)),
                    reps=load.get("reps", 10),
                )
            )

    session.flush()
    return profile


def get_profile(session: Session, user: User) -> Profile | None:
    return session.query(Profile).filter_by(user_id=user.id).one_or_none()


__all__ = ["upsert_profile", "get_profile"]
