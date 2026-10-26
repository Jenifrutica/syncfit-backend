"""Cycle and gestation timeline computation."""

from __future__ import annotations

from datetime import date

from syncfit_database import Profile

from ..analytics.phase_graph import build_cycle_graph, build_gestation_graph


def compute_timeline(profile: Profile, today: date | None = None) -> dict | None:
    """Compute the current cycle day/phase or gestational week/trimester."""
    today = today or date.today()

    if profile.modality == "GESTATIONAL":
        week = profile.gestation_week
        if week is None and profile.last_period_date is not None:
            week = min(42, (today - profile.last_period_date).days // 7 + 1)
        if week is None:
            return None
        graph = build_gestation_graph()
        node = graph.phase_for(week)
        following = graph.next_phase(node.phase)
        return {
            "modality": "GESTATIONAL",
            "week": week,
            "phase": node.phase,
            "next_phase": following.target if following else None,
            "weeks_to_next_phase": graph.units_until(week, following.target) if following else None,
        }

    if profile.last_period_date is not None:
        length = profile.cycle_length_days or 28
        cycle_day = ((today - profile.last_period_date).days % length) + 1
        graph = build_cycle_graph(length)
        node = graph.phase_for(cycle_day)
        following = graph.next_phase(node.phase)
        return {
            "modality": "MENSTRUAL_CYCLE",
            "cycle_day": cycle_day,
            "cycle_length_days": length,
            "phase": node.phase,
            "next_phase": following.target if following else None,
            "days_to_next_phase": graph.units_until(cycle_day, following.target) if following else None,
        }

    return None


__all__ = ["compute_timeline"]
