"""Gyms and machine surveys (for gym admins)."""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session
from syncfit_database import Gym, GymMachine, Profile, User


def _code() -> str:
    return secrets.token_hex(3).upper()  # e.g. A1B2C3


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
    name: str,
    purpose: str | None = None,
    image_url: str | None = None,
    weight_factor: float = 1.0,
) -> GymMachine:
    machine = GymMachine(
        gym_id=gym.id, name=name, purpose=purpose, image_url=image_url, weight_factor=weight_factor
    )
    session.add(machine)
    session.flush()
    return machine


def serialize_gym(gym: Gym) -> dict:
    return {
        "id": gym.id,
        "name": gym.name,
        "code": gym.code,
        "owner_user_id": gym.owner_user_id,
        "machines": [serialize_machine(m) for m in gym.machines],
    }


def serialize_machine(machine: GymMachine) -> dict:
    return {
        "id": machine.id,
        "gym_id": machine.gym_id,
        "name": machine.name,
        "purpose": machine.purpose,
        "image_url": machine.image_url,
        "weight_factor": machine.weight_factor,
    }


def join_gym(session: Session, profile: Profile, gym: Gym) -> Profile:
    profile.active_gym_id = gym.id
    # Gym machines are added as custom entries: "gym:<machine_id>".
    current = {m for m in (profile.available_machines or []) if m.startswith("gym:")}
    gym_ids = {f"gym:{m.id}" for m in gym.machines}
    others = [m for m in (profile.available_machines or []) if not m.startswith("gym:")]
    profile.available_machines = others + sorted(current | gym_ids)
    session.flush()
    return profile


__all__ = [
    "create_gym",
    "list_owned",
    "get_by_id",
    "get_by_code",
    "add_machine",
    "serialize_gym",
    "serialize_machine",
    "join_gym",
]
