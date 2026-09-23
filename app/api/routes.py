"""REST routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..services.catalog import get_catalog, list_muscle_groups
from ..services.engine import evaluate_frame
from ..services.routines import generate_routine
from syncfit_contracts import RoutineRequest

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Service health check."""
    return {"status": "ok", "version": settings.version}


@router.get("/muscle-groups")
def muscle_groups() -> list[str]:
    """Available muscle groups, isolated and general."""
    return list_muscle_groups()


@router.get("/catalog")
def catalog(language: str = Query(default="EN")) -> list[dict[str, Any]]:
    """Exercise catalog, localized to `language`."""
    return get_catalog(language)


@router.post("/telemetry")
def ingest_telemetry(frame: dict[str, Any]) -> dict[str, Any]:
    """Validate a telemetry frame and return the deterministic decision."""
    try:
        return {"decision": evaluate_frame(frame)}
    except Exception as exc:  # schema or model failure
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/routines")
def create_routine(
    payload: dict[str, Any],
    engine: str = Query(default="simulator", pattern="^(simulator|ai)$"),
) -> dict[str, Any]:
    """Generate an adapted routine for the selected muscle groups."""
    try:
        request = RoutineRequest.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return generate_routine(request, engine=engine)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]
