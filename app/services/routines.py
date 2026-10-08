"""Routine generation service.

Default path uses the shared-catalog generator from `syncfit-simulator` (fluid,
no API key). The optional AI path uses `syncfit-ai-reasoning` when installed and
configured. Baseline loads from the athlete profile are applied in both paths.
"""

from __future__ import annotations

from typing import Any, Iterable

from syncfit_contracts import RoutineRequest, RoutineResponse
from syncfit_core import EngineResult
from syncfit_core.enums import InferredPhase
from syncfit_simulator import build_routine

from . import profiles
from .engine import engine_result
from .loads import adjust_entries, variation_pct

DEFAULT_EXERCISES_PER_GROUP = 2


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def max_impact_for(core_result: EngineResult | None) -> str:
    if core_result is None:
        return "HIGH"
    if core_result.phase_inferred in (InferredPhase.OVULATORY, InferredPhase.TRIMESTER_3):
        return "LOW"
    return "HIGH"


def core_result_for_request(request: RoutineRequest) -> EngineResult | None:
    if request.telemetry is None:
        return None
    return engine_result(request.telemetry.model_dump(mode="json"))


def generate_routine(
    request: RoutineRequest,
    engine: str = "deterministic",
    profile_id: str | None = None,
    preferred_exercise_ids: Iterable[str] | None = None,
    contraindicated_patterns: Iterable[str] | None = None,
    gym_machines: list[dict[str, Any]] | None = None,
    assessment: dict[str, Any] | None = None,
    equipment_keys: Iterable[str] | None = None,
    available_exercise_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Generate a routine.

    ``engine``:
    - ``ai``: OpenCode reasoning (DeepSeek, GPT-6 Luna on transient failures).
    - ``deterministic``: the evidence-based pattern engine (fast, same guarantees).
    - ``simulator``: legacy catalog builder (fallback).

    ``preferred_exercise_ids`` are the athlete's gym machines; ``contraindicated_patterns``
    come from symptoms (e.g. knee pain -> lunge/squat).
    """
    core_result = core_result_for_request(request)
    k_load = core_result.k_load if core_result is not None else None
    groups = [_value(g) for g in request.muscle_groups]
    language = _value(request.language)
    per_group = request.exercises_per_group or DEFAULT_EXERCISES_PER_GROUP
    profile = profiles.get_profile(profile_id) if profile_id else None
    loads = profile.loads if profile else []
    preferred = list(preferred_exercise_ids or [])
    contraindicated = list(contraindicated_patterns or [])
    equipment = list(equipment_keys) if equipment_keys is not None else None
    allowed = list(available_exercise_ids or [])

    if engine == "ai":
        try:
            from syncfit_ai import OpenCodeGoClient, RoutinePlanner
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "AI engine requested but syncfit-ai-reasoning is not installed "
                "(pip install 'syncfit-backend[reasoning]')."
            ) from exc
        planner = RoutinePlanner(OpenCodeGoClient())
        result = planner.plan(
            request,
            core_result,
            baseline_loads=loads or None,
            contraindicated_patterns=contraindicated,
            preferred_exercise_ids=preferred,
            gym_machines=gym_machines,
            assessment=assessment,
            equipment_keys=equipment,
            available_exercise_ids=allowed,
        )
        payload = result.model_dump(mode="json")
        payload["engine_used"] = planner.last_engine
        if not loads:
            payload["variation_pct"] = variation_pct(k_load, request.energy_level)
        return payload

    if engine == "deterministic":
        try:
            from syncfit_ai import build_prescription

            payload = build_prescription(
                request,
                core_result,
                contraindicated_patterns=contraindicated,
                preferred_exercise_ids=preferred,
                equipment_keys=equipment,
                available_exercise_ids=allowed,
            )
            if loads:
                payload["warmup"] = adjust_entries(
                    payload.get("warmup", []), loads, k_load, request.energy_level
                )
                payload["routine"] = adjust_entries(
                    payload.get("routine", []), loads, k_load, request.energy_level
                )
            validated = RoutineResponse.model_validate(payload).model_dump(mode="json")
            validated["variation_pct"] = variation_pct(k_load, request.energy_level)
            return validated
        except Exception:
            pass  # fall through to the simulator builder

    payload = build_routine(
        groups,
        language=language,
        exercises_per_group=per_group,
        max_impact=max_impact_for(core_result),
        session_id=request.session_id,
        exercises_count=request.exercises_count,
        time_budget_minutes=request.time_budget_minutes,
        include_warmup=request.include_warmup,
        objective=_value(request.objective) if request.objective else None,
        preferred_exercise_ids=preferred,
    )
    if loads:
        payload["warmup"] = adjust_entries(
            payload.get("warmup", []), loads, k_load, request.energy_level
        )
        payload["routine"] = adjust_entries(
            payload.get("routine", []), loads, k_load, request.energy_level
        )
    validated = RoutineResponse.model_validate(payload).model_dump(mode="json")
    validated["variation_pct"] = variation_pct(k_load, request.energy_level)
    return validated


__all__ = ["generate_routine", "core_result_for_request", "max_impact_for"]
