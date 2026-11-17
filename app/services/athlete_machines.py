"""The athlete's own machines: catalog ids plus machines typed by name."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session
from syncfit_database import AthleteMachine, Profile

from . import gyms as gyms_service
from .machines import list_machines

CUSTOM_PREFIX = "custom-"


def _catalog_by_id(language: str) -> dict[str, dict[str, Any]]:
    return {m["id"]: m for m in list_machines(language)}


def list_selected(session: Session, profile: Profile, language: str = "EN") -> list[dict[str, Any]]:
    catalog = _catalog_by_id(language)
    typed = {
        CUSTOM_PREFIX + row.id: row
        for row in session.query(AthleteMachine).filter_by(profile_id=profile.id).all()
    }
    result: list[dict[str, Any]] = []
    for machine_id in profile.available_machines or []:
        if machine_id in catalog:
            item = catalog[machine_id]
            result.append({"id": machine_id, "name": item["name"], "type": item["type"], "custom": False})
        elif machine_id in typed:
            row = typed[machine_id]
            result.append({
                "id": machine_id,
                "name": gyms_service.localize(row.name, language),
                "type": row.equipment_type,
                "custom": True,
            })
    return result


def add_catalog(session: Session, profile: Profile, ids: list[str]) -> list[str]:
    """Add catalog machines; unknown ids are returned and ignored."""
    catalog = _catalog_by_id("EN")
    current = list(profile.available_machines or [])
    unknown: list[str] = []
    for machine_id in ids:
        if machine_id not in catalog:
            unknown.append(machine_id)
        elif machine_id not in current:
            current.append(machine_id)
    profile.available_machines = current
    session.flush()
    return unknown


def add_typed(
    session: Session,
    profile: Profile,
    name: str,
    language: str,
    infer: Callable[[str, Any, str], dict[str, Any]],
) -> AthleteMachine:
    """Create a machine from a typed name; the AI infers type and exercises (best effort)."""
    info = infer(name, None, language) or {}
    row = AthleteMachine(
        profile_id=profile.id,
        name=gyms_service.build_i18n(name, info.get("name")),
        equipment_type=(str(info["inferred_type"])[:20] if info.get("inferred_type") else None),
        exercise_ids=gyms_service.sanitize_exercise_ids(list(info.get("exercise_ids") or [])),
    )
    session.add(row)
    session.flush()
    profile.available_machines = [*(profile.available_machines or []), CUSTOM_PREFIX + row.id]
    session.flush()
    return row


def remove(session: Session, profile: Profile, ids: list[str]) -> tuple[list[str], list[str]]:
    """Remove machines; typed ones are deleted. Returns (removed, missing)."""
    current = list(profile.available_machines or [])
    removed: list[str] = []
    missing: list[str] = []
    for machine_id in ids:
        if machine_id not in current:
            missing.append(machine_id)
            continue
        current.remove(machine_id)
        removed.append(machine_id)
        if machine_id.startswith(CUSTOM_PREFIX):
            row = session.get(AthleteMachine, machine_id[len(CUSTOM_PREFIX):])
            if row is not None and row.profile_id == profile.id:
                session.delete(row)
    profile.available_machines = current
    session.flush()
    return removed, missing


__all__ = ["CUSTOM_PREFIX", "add_catalog", "add_typed", "list_selected", "remove"]
