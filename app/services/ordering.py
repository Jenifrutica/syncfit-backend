"""Routine ordering.

Prefers the medical ordering from `syncfit-ai-reasoning`; falls back to a local
implementation when that package is not installed, so the flow always works.
"""

from __future__ import annotations

from typing import Any

_ROLE = {"ACTIVATION": 0, "WARMUP": 1, "MAIN": 2}


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def _local_order(entries: list[dict[str, Any]], phase: str | None = None) -> list[dict[str, Any]]:
    low_impact = _value(phase) in {"OVULATORY", "TRIMESTER_3"}

    def key(entry: dict[str, Any]) -> tuple:
        blocked = 1 if entry.get("blocked") else 0
        role = _ROLE.get(_value(entry.get("role") or "MAIN"), 2)
        groups = len(entry.get("muscle_groups") or [])
        return (blocked, role, 0 if low_impact else -groups)

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
