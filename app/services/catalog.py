"""Exercise catalog service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from syncfit_contracts import MuscleGroup, load_exercises, localize
from syncfit_database import AppOption

from .options import GENERAL, ISOLATED


def list_muscle_groups(session: Session | None = None) -> list[str]:
    """Active muscle groups, from the database when a session is available."""
    if session is None:
        return [group.value for group in MuscleGroup]
    rows = (
        session.query(AppOption.value)
        .filter(
            AppOption.active.is_(True),
            AppOption.category.in_((ISOLATED, GENERAL)),
        )
        .order_by(AppOption.sort_order, AppOption.value)
        .all()
    )
    values = [value for (value,) in rows]
    return values or [group.value for group in MuscleGroup]


def get_catalog(language: str = "EN") -> list[dict[str, Any]]:
    """Return the catalog with text localized to `language`."""
    result: list[dict[str, Any]] = []
    for exercise in load_exercises():
        name_i18n = {"en": exercise.name.en}
        name_i18n.update(exercise.name.model_extra or {})
        description_i18n = {"en": exercise.description.en}
        description_i18n.update(exercise.description.model_extra or {})
        result.append(
            {
                "id": exercise.id,
                "name": localize(exercise.name, language),
                "description": localize(exercise.description, language),
                "muscle_groups": list(exercise.muscle_groups),
                "equipment": exercise.equipment,
                "impact": str(exercise.impact),
                "image_url": exercise.image_url,
                "media_url": exercise.media_url,
                "supine": bool(getattr(exercise, "supine", False)),
                "setup": exercise.setup.model_dump() if exercise.setup else None,
                "pregnancy_tip": exercise.pregnancy_tip.model_dump()
                if exercise.pregnancy_tip
                else None,
                "name_i18n": name_i18n,
                "description_i18n": description_i18n,
            }
        )
    return result


__all__ = ["get_catalog", "list_muscle_groups"]
