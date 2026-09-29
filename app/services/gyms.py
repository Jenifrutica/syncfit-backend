"""Gyms, machines and memberships (admin + athlete side)."""

from __future__ import annotations

import re
import secrets
from collections import defaultdict

from sqlalchemy.orm import Session
from syncfit_contracts import load_exercises
from syncfit_database import Gym, GymMachine, GymMembership, Profile, User

LANGS = ("en", "es", "zh")
_TOKEN_RE = re.compile(r"[a-záéíóúüñ]+")
# Generic words that must not create false machine<->exercise matches.
_STOPWORDS = {
    "machine", "maquina", "máquina", "de", "del", "en", "la", "el", "los", "las",
    "y", "o", "para", "con", "the", "and", "with", "a", "of", "to", "seated",
}


def _code() -> str:
    return secrets.token_hex(3).upper()  # e.g. A1B2C3


def localize(value: object, language: str = "EN") -> str:
    """Resolve a localized value (dict or plain string) to a single string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get(language.lower()) or value.get("en") or next(iter(value.values()), ""))
    return str(value)


def build_i18n(text: str, ai_value: object = None) -> dict:
    """Build a localized dict from text, using AI translations when valid.

    Fallback (no AI): the typed text is copied to every language so the value
    is never empty and can be shown in any locale.
    """
    if isinstance(ai_value, dict) and ai_value.get("en"):
        result = {"en": str(ai_value["en"])}
        for lang in LANGS:
            if ai_value.get(lang):
                result[lang] = str(ai_value[lang])
        return result
    return {lang: text for lang in LANGS}


def create_gym(session: Session, user: User, name: str) -> Gym:
    gym = Gym(name=name, code=_code(), owner_user_id=user.id)
    session.add(gym)
    session.flush()
    return gym


def list_owned(session: Session, user: User) -> list[Gym]:
    return session.query(Gym).filter_by(owner_user_id=user.id).all()


def get_by_id(session: Session, gym_id: str) -> Gym | None:
    return session.get(Gym, gym_id)


def get_by_code(session: Session, code: str) -> Gym | None:
    return session.query(Gym).filter_by(code=code.upper()).one_or_none()


def add_machine(
    session: Session,
    gym: Gym,
    name: dict,
    purpose: dict | None = None,
    image_url: str | None = None,
    weight_factor: float = 1.0,
    exercise_ids: list[str] | None = None,
    equipment_key: str | None = None,
    equipment_type: str | None = None,
) -> GymMachine:
    machine = GymMachine(
        gym_id=gym.id,
        name=name,
        purpose=purpose,
        exercise_ids=list(exercise_ids or []),
        equipment_key=equipment_key,
        equipment_type=equipment_type,
        image_url=image_url,
        weight_factor=weight_factor,
    )
    session.add(machine)
    session.flush()
    return machine


def get_machine(session: Session, gym: Gym, machine_id: str) -> GymMachine | None:
    machine = session.get(GymMachine, machine_id)
    if machine is None or machine.gym_id != gym.id:
        return None
    return machine


def update_machine(
    session: Session,
    machine: GymMachine,
    *,
    name: dict | None = None,
    purpose: dict | None = None,
    image_url: str | None = None,
    weight_factor: float | None = None,
    exercise_ids: list[str] | None = None,
    equipment_key: str | None = None,
    equipment_type: str | None = None,
) -> GymMachine:
    if name is not None:
        machine.name = name
    if purpose is not None:
        machine.purpose = purpose
    if image_url is not None:
        machine.image_url = image_url
    if weight_factor is not None:
        machine.weight_factor = weight_factor
    if exercise_ids is not None:
        machine.exercise_ids = list(exercise_ids)
    if equipment_key is not None:
        machine.equipment_key = equipment_key
    if equipment_type is not None:
        machine.equipment_type = equipment_type
    session.flush()
    return machine


def delete_machine(session: Session, machine: GymMachine) -> None:
    session.delete(machine)
    session.flush()


def rename_gym(session: Session, gym: Gym, name: str) -> Gym:
    gym.name = name
    session.flush()
    return gym


def delete_gym(session: Session, gym: Gym) -> None:
    """Delete a gym: its memberships, dangling active pointers and machines."""
    session.query(GymMembership).filter_by(gym_id=gym.id).delete()
    session.query(Profile).filter_by(active_gym_id=gym.id).update({"active_gym_id": None})
    session.delete(gym)  # machines cascade via the relationship
    session.flush()


def serialize_gym(gym: Gym, language: str = "EN") -> dict:
    return {
        "id": gym.id,
        "name": gym.name,
        "code": gym.code,
        "owner_user_id": gym.owner_user_id,
        "machines": [serialize_machine(m, language) for m in gym.machines],
    }


def serialize_machine(machine: GymMachine, language: str = "EN") -> dict:
    """Serialize a gym machine with localized name/purpose.

    Keeps the localized dicts (contract shape) and adds `name_text`/`purpose_text`
    resolved strings for convenience.
    """
    name = machine.name if isinstance(machine.name, dict) else {"en": str(machine.name)}
    purpose = machine.purpose if isinstance(machine.purpose, dict) else (
        {"en": str(machine.purpose)} if machine.purpose else None
    )
    return {
        "id": machine.id,
        "gym_id": machine.gym_id,
        "name": name,
        "purpose": purpose,
        "name_text": localize(name, language),
        "purpose_text": localize(purpose, language) if purpose else None,
        "exercise_ids": list(machine.exercise_ids or []),
        "equipment_key": machine.equipment_key,
        "equipment_type": machine.equipment_type,
        "image_url": machine.image_url,
        "weight_factor": machine.weight_factor,
    }


def join_gym(session: Session, profile: Profile, gym: Gym) -> GymMembership:
    """Join a gym idempotently and make it active if nothing else is.

    Machines are NOT copied into the profile: they are resolved live from the
    membership, so admin edits are always reflected.
    """
    membership = (
        session.query(GymMembership)
        .filter_by(profile_id=profile.id, gym_id=gym.id)
        .one_or_none()
    )
    if membership is None:
        membership = GymMembership(profile_id=profile.id, gym_id=gym.id)
        session.add(membership)
        session.flush()
    if not profile.active_gym_id:
        profile.active_gym_id = gym.id
        session.flush()
    return membership


def list_memberships(session: Session, profile: Profile) -> list[GymMembership]:
    return (
        session.query(GymMembership)
        .filter_by(profile_id=profile.id)
        .order_by(GymMembership.created_at)
        .all()
    )


def leave_gym(session: Session, profile: Profile, gym_id: str) -> bool:
    membership = (
        session.query(GymMembership)
        .filter_by(profile_id=profile.id, gym_id=gym_id)
        .one_or_none()
    )
    if membership is None:
        return False
    session.delete(membership)
    if profile.active_gym_id == gym_id:
        profile.active_gym_id = None
    session.flush()
    return True


def set_active_gym(session: Session, profile: Profile, gym_id: str) -> bool:
    membership = (
        session.query(GymMembership)
        .filter_by(profile_id=profile.id, gym_id=gym_id)
        .one_or_none()
    )
    if membership is None:
        return False
    profile.active_gym_id = gym_id
    session.flush()
    return True


def serialize_joined_gym(
    gym: Gym, active: bool, joined_at=None, machines=None, language: str = "EN"
) -> dict:
    source = gym.machines if machines is None else machines
    return {
        "gym_id": gym.id,
        "name": gym.name,
        "code": gym.code,
        "active": bool(active),
        "joined_at": joined_at.isoformat() if joined_at else None,
        "machines": [serialize_machine(m, language) for m in source],
    }


def joined_gyms(session: Session, profile: Profile, language: str = "EN") -> list[dict]:
    """Resolve all joined gyms in O(G + M) instead of N+1 queries.

    Uses three structures:
    - a **hash map** (dict) ``gyms_by_id`` for O(1) gym lookup by id;
    - a **defaultdict grouping** ``machines_by_gym`` built from a single
      ``IN`` query, avoiding one query per gym;
    - a **set-like** active check (``gym.id == profile.active_gym_id``).
    """
    memberships = list_memberships(session, profile)
    if not memberships:
        return []

    gym_ids = [m.gym_id for m in memberships]
    gyms_by_id = {g.id: g for g in session.query(Gym).filter(Gym.id.in_(gym_ids)).all()}

    machines_by_gym: dict[str, list[GymMachine]] = defaultdict(list)
    for machine in session.query(GymMachine).filter(GymMachine.gym_id.in_(gym_ids)).all():
        machines_by_gym[machine.gym_id].append(machine)

    active_id = profile.active_gym_id
    result: list[dict] = []
    for membership in memberships:
        gym = gyms_by_id.get(membership.gym_id)
        if gym is None:
            continue
        result.append(
            serialize_joined_gym(
                gym,
                gym.id == active_id,
                membership.created_at,
                machines_by_gym[gym.id],
                language,
            )
        )
    return result


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _significant_tokens(text: str) -> set[str]:
    return _tokens(text) - _STOPWORDS


def resolved_exercise_ids(machine: GymMachine) -> list[str]:
    """Exercise ids a machine covers: declared ids, plus a fuzzy name fallback.

    Machines created before `exercise_ids` existed (or where the AI left it
    empty) are matched by token overlap between the machine's localized
    name/purpose and the exercise's localized names, preferring machine
    variants. This keeps the routine able to use gym machines regardless.
    """
    ids = [str(x) for x in (machine.exercise_ids or [])]
    # Match on the ENGLISH name only (canonical catalog names). Purpose and the
    # translated names add words ("empuje", "cadera") that create false matches.
    haystack = _significant_tokens(localize(machine.name, "EN"))
    if not haystack:
        return ids

    candidates: list[tuple[int, str]] = []
    for exercise in load_exercises():
        exercise_tokens = _significant_tokens(exercise.name.en)
        if not exercise_tokens:
            continue
        overlap = exercise_tokens & haystack
        # Two shared words (or full containment) ties a machine to its exercise
        # without letting generic words ("machine", "hip") match unrelated work.
        if overlap and (len(overlap) >= 2 or haystack <= exercise_tokens):
            is_machine = str(getattr(exercise, "equipment_type", "") or "") == "MACHINE"
            candidates.append((0 if is_machine else 1, exercise.id))
    candidates.sort()
    for _, exercise_id in candidates:
        if exercise_id not in ids:
            ids.append(exercise_id)
    return ids


_EQUIPMENT_TYPE_KEYS = {
    "MACHINE": "machine", "SMITH": "smith", "CABLE": "cable", "BAND": "band",
    "BODYWEIGHT": "none", "ASSISTED": "machine", "FREE_WEIGHT": "dumbbell",
}


def _active_gym_id(session: Session, profile: Profile) -> str | None:
    if profile.active_gym_id:
        return profile.active_gym_id
    memberships = list_memberships(session, profile)
    return memberships[0].gym_id if memberships else None


def gym_inventory(session: Session, profile: Profile) -> list[GymMachine]:
    gym_id = _active_gym_id(session, profile)
    if not gym_id:
        return []
    return session.query(GymMachine).filter_by(gym_id=gym_id).all()


def available_equipment_keys(session: Session, profile: Profile) -> set[str] | None:
    """Equipment keys available from the gym inventory (None = unknown, don't filter)."""
    machines = gym_inventory(session, profile)
    if not machines:
        return None
    keys: set[str] = set()
    for machine in machines:
        # Every inventory item is gym equipment; machines default to the machine key.
        keys.add(machine.equipment_key or "machine")
        if machine.equipment_type:
            mapped = _EQUIPMENT_TYPE_KEYS.get(str(machine.equipment_type).upper())
            if mapped:
                keys.add(mapped)
    return keys


def available_exercise_ids(session: Session, profile: Profile) -> set[str]:
    """Exercise ids explicitly covered by the gym inventory (bypass equipment filter)."""
    ids: set[str] = set()
    for machine in gym_inventory(session, profile):
        ids.update(resolved_exercise_ids(machine))
    return ids


def sanitize_exercise_ids(ids: list[str] | None) -> list[str]:
    """Keep only catalog exercise ids (drops AI hallucinations) and deduplicate."""
    from syncfit_contracts import get_exercise

    result: list[str] = []
    for raw in ids or []:
        exercise_id = str(raw)
        if exercise_id and get_exercise(exercise_id) is not None and exercise_id not in result:
            result.append(exercise_id)
    return result


def _best_machine_variant(ids: list[str], declared: list[str] | None = None) -> str:
    """Best variant: a MACHINE exercise of the SAME movement as the declared id.

    Falls back to the declared id, then to the first resolved id. This keeps a
    "Hip Thrust Machine" from resolving to an unrelated (but machine-type) match.
    """
    from syncfit_contracts import get_exercise, patterns_of

    if not ids and not declared:
        return ""
    declared = [str(x) for x in (declared or [])]
    target_pattern = None
    for exercise_id in declared:
        exercise = get_exercise(exercise_id)
        if exercise is not None:
            target_pattern = patterns_of(exercise)
            break
    for exercise_id in ids:
        exercise = get_exercise(exercise_id)
        if exercise is None:
            continue
        if str(getattr(exercise, "equipment_type", "") or "") != "MACHINE":
            continue
        if target_pattern and patterns_of(exercise) != target_pattern:
            continue
        return exercise_id
    return declared[0] if declared else ids[0]


def station_index(
    session: Session, profile: Profile, language: str = "EN"
) -> tuple[dict[str, dict], set[str]]:
    """Index the active gym's machines by exercise id.

    Returns ``(index, preferred)`` where ``index`` is a **hash map**
    ``exercise_id -> serialized station`` (O(1) lookup per routine entry) and
    ``preferred`` is the **set** of exercise ids those machines cover. Exercises
    in ``preferred`` are requested first when building the routine.

    If no gym is active, the first joined gym is used.
    """
    gym_id = profile.active_gym_id
    if not gym_id:
        memberships = list_memberships(session, profile)
        gym_id = memberships[0].gym_id if memberships else None
    if not gym_id:
        return {}, set()

    index: dict[str, dict] = {}
    preferred: set[str] = set()
    for machine in session.query(GymMachine).filter_by(gym_id=gym_id).all():
        station = serialize_machine(machine, language)
        resolved = resolved_exercise_ids(machine)
        for exercise_id in resolved:
            index.setdefault(exercise_id, station)
        if resolved:
            # Only the best variant is a hard preference: a MACHINE exercise of the
            # same movement as the declared id, else the declared id.
            preferred.add(_best_machine_variant(resolved, machine.exercise_ids))
    return index, preferred


__all__ = [
    "create_gym",
    "list_owned",
    "get_by_id",
    "get_by_code",
    "add_machine",
    "get_machine",
    "update_machine",
    "delete_machine",
    "rename_gym",
    "delete_gym",
    "resolved_exercise_ids",
    "sanitize_exercise_ids",
    "available_equipment_keys",
    "available_exercise_ids",
    "serialize_gym",
    "serialize_machine",
    "serialize_joined_gym",
    "joined_gyms",
    "station_index",
    "join_gym",
    "list_memberships",
    "leave_gym",
    "set_active_gym",
    "build_i18n",
    "localize",
]
