"""Routine ordering.

Prefers the medical ordering from `syncfit-ai-reasoning`; falls back to a local
implementation when that package is not installed, so the flow always works.

The rules mirror `syncfit_ai.ordering`: activation/warm-up, then bilateral
compounds, then unilateral multi-joint work, then accessories. ACSM (2009)
recommends multiple-joint before single-joint and large before small muscle
groups; Nunes et al. (2020) found multi-joint strength improves when
multi-joint work comes first, while hypertrophy is similar either way.
"""

from __future__ import annotations

from typing import Any

_ROLE = {"ACTIVATION": 0, "WARMUP": 1, "MAIN": 2}
_IMPACT = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_COMPOUND_THRESHOLD = 3
_UNILATERAL_PATTERNS = {"lunge", "step_up", "step-up", "split_squat", "single_leg", "single_arm"}


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def _compound(entry: dict[str, Any]) -> bool:
    flag = entry.get("compound")
    if isinstance(flag, bool):
        return flag
    return len(entry.get("muscle_groups") or []) >= _COMPOUND_THRESHOLD


def _tier(entry: dict[str, Any]) -> int:
    """0 bilateral compound · 1 unilateral multi-joint · 2 accessory / single-joint."""
    if not _compound(entry):
        return 2
    pattern = _value(entry.get("movement_pattern") or "").strip().lower()
    return 1 if pattern in _UNILATERAL_PATTERNS else 0


def _local_order(entries: list[dict[str, Any]], phase: str | None = None) -> list[dict[str, Any]]:
    low_impact = _value(phase) in {"OVULATORY", "TRIMESTER_3"}

    def key(entry: dict[str, Any]) -> tuple:
        blocked = 1 if entry.get("blocked") else 0
        role = _ROLE.get(_value(entry.get("role") or "MAIN"), 2)
        tier = _tier(entry)
        impact = _IMPACT.get(_value(entry.get("impact") or "MEDIUM"), 1) if low_impact else 0
        groups = len(entry.get("muscle_groups") or [])
        return (blocked, role, tier, impact, -groups)

    return sorted(entries, key=key)


def order_entries(
    entries: list[dict[str, Any]],
    phase: str | None = None,
    language: str = "EN",
) -> list[dict[str, Any]]:
    try:
        from syncfit_ai import order_routine
    except Exception:  # pragma: no cover - optional dependency
        return _local_order(entries, phase)
    return order_routine(entries, phase, language)


__all__ = ["order_entries"]
