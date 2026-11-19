"""Baseline-load adjustment.

Estimates how much the athlete's usual weights should vary, combining the
deterministic `k_load` with the subjective energy level.
"""

from __future__ import annotations

from typing import Any, Iterable

from syncfit_contracts import ExerciseLoad

_ENERGY_FACTOR = {"ENERGY": 1.0, "MODERATE": 0.95, "NO_ENERGY": 0.88}


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def load_multiplier(k_load: float | None, energy_level: object | None = None) -> float:
    base = float(k_load) if k_load is not None else 1.0
    energy = _ENERGY_FACTOR.get(_value(energy_level), 1.0) if energy_level else 1.0
    return round(base * energy, 3)


def variation_pct(k_load: float | None, energy_level: object | None = None) -> float:
    return round((load_multiplier(k_load, energy_level) - 1.0) * 100.0, 1)


def energy_factor(energy_level: object | None) -> float:
    return _ENERGY_FACTOR.get(_value(energy_level), 1.0) if energy_level else 1.0


def is_assisted(exercise_id: str) -> bool:
    """Assisted pull-up / chin-up / dip: the weight is a COUNTERWEIGHT (more = easier)."""
    try:
        from syncfit_contracts import get_exercise

        exercise = get_exercise(exercise_id)
    except Exception:
        exercise = None
    kind = str(getattr(exercise, "equipment_type", "") or "").upper() if exercise is not None else ""
    return kind.endswith("ASSISTED") or "assisted" in (exercise_id or "")


def assisted_weight(assist_kg: float, multiplier: float, body_weight_kg: float | None) -> float:
    """Counterweight for today's capacity.

    The work is the net load (body weight - assistance). Today's multiplier
    scales that net load, so a weaker day gets MORE assistance. Without the
    body weight, the assistance is divided by the multiplier (capped).
    """
    m = min(max(multiplier, 0.3), 1.0)
    if body_weight_kg and body_weight_kg > assist_kg:
        net = body_weight_kg - assist_kg
        return round(min(body_weight_kg - net * m, body_weight_kg * 0.9), 1)
    return round(min(assist_kg / m, assist_kg * 1.6), 1)


def _scale_sets(sets: list[dict[str, Any]], working_kg: float) -> list[dict[str, Any]]:
    """Put today's working weight on every set (approach sets keep their share)."""
    scaled = [dict(s) for s in sets]
    effective = [s for s in scaled if s.get("type") == "EFFECTIVE"]
    old_working = max((float(s.get("weight_kg") or 0) for s in effective), default=0.0)
    approach_shares = [0.5, 0.75]
    approach_index = 0
    for s in scaled:
        kind = s.get("type")
        if kind == "EFFECTIVE":
            s["weight_kg"] = round(working_kg, 1)
        elif kind == "APPROXIMATION":
            old = float(s.get("weight_kg") or 0)
            share = old / old_working if old_working > 0 and old > 0 else approach_shares[min(approach_index, 1)]
            s["weight_kg"] = round(working_kg * share, 1)
            approach_index += 1
    return scaled


def _assisted_sets(sets: list[dict[str, Any]], assist_today: float, body_weight_kg: float | None) -> list[dict[str, Any]]:
    """Approach sets of an assisted exercise get MORE help (they are lighter)."""
    scaled = [dict(s) for s in sets]
    shares = [0.5, 0.75]
    index = 0
    for s in scaled:
        if s.get("type") == "EFFECTIVE":
            s["weight_kg"] = assist_today
        elif s.get("type") == "APPROXIMATION":
            share = shares[min(index, 1)]
            if body_weight_kg and body_weight_kg > assist_today:
                s["weight_kg"] = round(body_weight_kg - (body_weight_kg - assist_today) * share, 1)
            else:
                s["weight_kg"] = round(min(assist_today / share, assist_today * 2.0), 1)
            index += 1
    return scaled


def adjust_entries(
    entries: list[dict[str, Any]],
    loads: Iterable[ExerciseLoad],
    k_load: float | None,
    energy_level: object | None = None,
    machine_factors: dict[str, float] | None = None,
    multiplier: float | None = None,
    body_weight_kg: float | None = None,
) -> list[dict[str, Any]]:
    """Today's weight for each exercise with a registered load.

    `multiplier` (from the sensor readiness) replaces `k_load x energy` when given.
    The working weight is written both as `weight_suggested_kg` and on the sets,
    which is what the app shows.
    """
    by_id = {load.exercise_id: float(load.weight_kg) for load in loads}
    factor_today = multiplier if multiplier is not None else load_multiplier(k_load, energy_level)
    factors = machine_factors or {}
    adjusted: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        exercise_id = item.get("exercise_id", "")
        base = by_id.get(exercise_id)
        if base is not None:
            if is_assisted(exercise_id):
                assist = assisted_weight(base * factors.get(exercise_id, 1.0), factor_today, body_weight_kg)
                item["weight_suggested_kg"] = assist
                item["assisted"] = True
                if item.get("sets"):
                    item["sets"] = _assisted_sets(item["sets"], assist, body_weight_kg)
            else:
                working = round(base * factor_today * factors.get(exercise_id, 1.0), 1)
                item["weight_suggested_kg"] = working
                if item.get("sets"):
                    item["sets"] = _scale_sets(item["sets"], working)
        adjusted.append(item)
    return adjusted


__all__ = ["adjust_entries", "assisted_weight", "energy_factor", "is_assisted", "load_multiplier", "variation_pct"]
