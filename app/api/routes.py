"""REST routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from syncfit_contracts import EnergyCheckIn, RoutineRequest, SupplementRequest, UserProfile

from ..config import settings
from ..services import profiles
from ..services.catalog import get_catalog, list_muscle_groups
from ..services.engine import evaluate_frame
from ..services.routines import generate_routine
from ..services.supplements import recommend

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version}


@router.get("/muscle-groups")
def muscle_groups() -> list[str]:
    return list_muscle_groups()


@router.get("/catalog")
def catalog(language: str = Query(default="EN")) -> list[dict[str, Any]]:
    return get_catalog(language)


@router.post("/telemetry")
def ingest_telemetry(frame: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"decision": evaluate_frame(frame)}
    except Exception as exc:  # schema or model failure
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/routines")
def create_routine(
    payload: dict[str, Any],
    engine: str = Query(default="simulator", pattern="^(simulator|ai)$"),
    profile_id: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        request = RoutineRequest.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return generate_routine(request, engine=engine, profile_id=profile_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/supplements")
def supplements(
    modality: str = Query(default="MENSTRUAL_CYCLE"),
    language: str = Query(default="EN"),
    objective: str | None = Query(default=None),
    week: int | None = Query(default=None),
) -> dict[str, Any]:
    try:
        request = SupplementRequest(
            modality=modality, language=language, objective=objective, week=week
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return recommend(request).model_dump(mode="json")


@router.post("/profiles")
def create_or_update_profile(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = UserProfile.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return profiles.upsert_profile(profile).model_dump(mode="json")


@router.get("/profiles")
def get_profiles() -> list[dict[str, Any]]:
    return [p.model_dump(mode="json") for p in profiles.list_profiles()]


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str) -> dict[str, Any]:
    profile = profiles.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return profile.model_dump(mode="json")


@router.post("/energy")
def add_energy(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        checkin = EnergyCheckIn.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return profiles.add_energy_checkin(checkin).model_dump(mode="json")


@router.get("/energy")
def get_energy(profile_id: str | None = Query(default=None)) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in profiles.list_energy(profile_id)]


__all__ = ["router"]
