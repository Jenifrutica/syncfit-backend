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


def adjust_entries(
    entries: list[dict[str, Any]],
    loads: Iterable[ExerciseLoad],
    k_load: float | None,
    energy_level: object | None = None,
) -> list[dict[str, Any]]:
    by_id = {load.exercise_id: float(load.weight_kg) for load in loads}
    multiplier = load_multiplier(k_load, energy_level)
    adjusted: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        base = by_id.get(item.get("exercise_id", ""))
        if base is not None:
            item["weight_suggested_kg"] = round(base * multiplier, 1)
        adjusted.append(item)
    return adjusted


__all__ = ["load_multiplier", "variation_pct", "adjust_entries"]
