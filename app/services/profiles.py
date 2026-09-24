"""In-memory user profiles and energy check-ins.

Guest profiles are ephemeral; a real deployment would persist these. The store
keeps the API contract stable so the frontend can already offer guest vs account.
"""

from __future__ import annotations

from typing import Any

from syncfit_contracts import EnergyCheckIn, UserProfile

_PROFILES: dict[str, UserProfile] = {}
_ENERGY: list[EnergyCheckIn] = []


def upsert_profile(profile: UserProfile) -> UserProfile:
    _PROFILES[profile.profile_id] = profile
    return profile


def get_profile(profile_id: str) -> UserProfile | None:
    return _PROFILES.get(profile_id)


def list_profiles() -> list[UserProfile]:
    return list(_PROFILES.values())


def add_energy_checkin(checkin: EnergyCheckIn) -> EnergyCheckIn:
    _ENERGY.append(checkin)
    return checkin


def list_energy(profile_id: str | None = None) -> list[EnergyCheckIn]:
    if profile_id is None:
        return list(_ENERGY)
    return [c for c in _ENERGY if c.profile_id == profile_id]


def clear() -> None:
    _PROFILES.clear()
    _ENERGY.clear()


__all__ = [
    "upsert_profile",
    "get_profile",
    "list_profiles",
    "add_energy_checkin",
    "list_energy",
    "clear",
]
