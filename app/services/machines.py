"""Gym machine catalog service."""

from __future__ import annotations

from typing import Any

from syncfit_contracts import get_machine, load_machines, localize


def list_machines(language: str = "EN") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for machine in load_machines():
        name_i18n = {"en": machine.name.en}
        name_i18n.update(machine.name.model_extra or {})
        notes_i18n = {"en": machine.notes.en}
        notes_i18n.update(machine.notes.model_extra or {})
        result.append(
            {
                "id": machine.id,
                "name": localize(machine.name, language),
                "type": str(machine.type),
                "unit": machine.unit,
                "weight_factor": machine.weight_factor,
                "exercises": list(machine.exercises),
                "notes": localize(machine.notes, language),
                "image_url": machine.image_url,
                "name_i18n": name_i18n,
                "notes_i18n": notes_i18n,
            }
        )
    return result


def machine_weight_factor(machine_id: str | None) -> float:
    if not machine_id:
        return 1.0
    machine = get_machine(machine_id)
    return machine.weight_factor if machine else 1.0


def factor_for_exercise(exercise_id: str, available_machine_ids: list[str] | None = None) -> float:
    """Weight factor of the first available machine supporting the exercise."""
    for machine in load_machines():
        if exercise_id not in machine.exercises:
            continue
        if available_machine_ids and machine.id not in available_machine_ids:
            continue
        return machine.weight_factor
    return 1.0


__all__ = ["list_machines", "machine_weight_factor", "factor_for_exercise"]
