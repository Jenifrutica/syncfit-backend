"""Routine generation service.

Default path uses the shared-catalog generator from `syncfit-simulator` (fluid,
no API key). The optional AI path uses `syncfit-ai-reasoning` when installed and
configured.
"""

from __future__ import annotations

from typing import Any

from syncfit_contracts import RoutineRequest, RoutineResponse
from syncfit_core import EngineResult
from syncfit_core.enums import InferredPhase
from syncfit_simulator import build_routine

from .engine import engine_result

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
    engine: str = "simulator",
) -> dict[str, Any]:
    """Generate a routine; `engine` is 'simulator' (default) or 'ai'."""
    core_result = core_result_for_request(request)
    groups = [_value(g) for g in request.muscle_groups]
    language = _value(request.language)
    per_group = request.exercises_per_group or DEFAULT_EXERCISES_PER_GROUP

    if engine == "ai":
        try:
            from syncfit_ai import OpenCodeGoClient, RoutinePlanner
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "AI engine requested but syncfit-ai-reasoning is not installed "
                "(pip install 'syncfit-backend[reasoning]')."
            ) from exc
        planner = RoutinePlanner(OpenCodeGoClient())
        return planner.plan(request, core_result).model_dump(mode="json")

    payload = build_routine(
        groups,
        language=language,
        exercises_per_group=per_group,
        max_impact=max_impact_for(core_result),
        session_id=request.session_id,
    )
    return RoutineResponse.model_validate(payload).model_dump(mode="json")


__all__ = ["generate_routine", "core_result_for_request", "max_impact_for"]
