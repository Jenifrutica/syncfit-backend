"""Cycle and gestation timeline computation."""

from __future__ import annotations

from datetime import date

from syncfit_core.graph import infer_phase_from_day
from syncfit_database import Profile


def compute_timeline(profile: Profile, today: date | None = None) -> dict | None:
    """Compute the current cycle day/phase or gestational week/trimester."""
    today = today or date.today()

    if profile.modality == "GESTATIONAL":
        week = profile.gestation_week
        if week is None and profile.last_period_date is not None:
            week = min(42, (today - profile.last_period_date).days // 7 + 1)
        if week is None:
            return None
        trimester = 1 if week <= 13 else 2 if week <= 27 else 3
        return {
            "modality": "GESTATIONAL",
            "week": week,
            "phase": f"TRIMESTER_{trimester}",
        }

    if profile.last_period_date is not None:
        length = profile.cycle_length_days or 28
        cycle_day = ((today - profile.last_period_date).days % length) + 1
        phase = infer_phase_from_day("MENSTRUAL_CYCLE", min(cycle_day, 40))
        return {
            "modality": "MENSTRUAL_CYCLE",
            "cycle_day": cycle_day,
            "cycle_length_days": length,
            "phase": phase.value,
        }

    return None


__all__ = ["compute_timeline"]
