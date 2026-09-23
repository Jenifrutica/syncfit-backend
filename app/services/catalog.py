"""Exercise catalog service."""

from __future__ import annotations

from typing import Any

from syncfit_contracts import MuscleGroup, load_exercises, localize


def list_muscle_groups() -> list[str]:
    return [group.value for group in MuscleGroup]


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
                "name_i18n": name_i18n,
                "description_i18n": description_i18n,
            }
        )
    return result


__all__ = ["get_catalog", "list_muscle_groups"]
