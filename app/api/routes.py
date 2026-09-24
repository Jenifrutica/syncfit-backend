"""REST routes."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from syncfit_contracts import EnergyCheckIn, RoutineRequest, SupplementRequest, UserProfile
from syncfit_database import Routine, SupplementIntake, User

from ..config import settings
from ..db import get_session
from ..services import profiles
from ..services.auth import current_user
from ..services.capture import capture
from ..services.catalog import get_catalog, list_muscle_groups
from syncfit_contracts import load_symptoms, localize
from ..services.calendar import build_calendar
from ..services.cycles import compute_timeline
from ..services.engine import evaluate_frame
from ..services.machines import list_machines
from ..services.routines import generate_routine
from ..services.sharing import (
    build_shared_profile,
    create_share,
    delete_share,
    list_shares,
    serialize_link,
)
from ..services.stats import compute_stats
from ..services.supplements import catalog as supplements_catalog
from ..services.supplements import recommend
from ..services import profiles_db

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
    goal_phase: str | None = Query(default=None),
    week: int | None = Query(default=None),
    weight_kg: float | None = Query(default=None),
    height_cm: float | None = Query(default=None),
    body_fat_pct: float | None = Query(default=None),
    age: int | None = Query(default=None),
    daily_calories: int | None = Query(default=None),
) -> dict[str, Any]:
    try:
        request = SupplementRequest(
            modality=modality,
            language=language,
            objective=objective,
            goal_phase=goal_phase,
            week=week,
            weight_kg=weight_kg,
            height_cm=height_cm,
            body_fat_pct=body_fat_pct,
            age=age,
            daily_calories=daily_calories,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return recommend(request).model_dump(mode="json")


@router.get("/symptoms")
def symptoms(language: str = Query(default="EN")) -> list[dict[str, Any]]:
    result = []
    for symptom in load_symptoms():
        result.append({
            "id": symptom["id"],
            "name": localize(symptom["name"], language),
            "modality": symptom.get("modality", "ANY"),
            "advice": localize(symptom.get("advice", {}), language),
            "impact_cap": symptom.get("impact_cap"),
            "block_training": symptom.get("block_training", False),
        })
    return result


@router.get("/machines")
def machines(language: str = Query(default="EN")) -> list[dict[str, Any]]:
    return list_machines(language)


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


@router.get("/profiles/by-id/{profile_id}")
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


# --- Authenticated athlete flow -------------------------------------------------


@router.put("/profiles/me")
def update_my_profile(
    payload: dict[str, Any],
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = profiles_db.upsert_profile(session, user, payload)
    session.commit()
    session.refresh(profile)
    return _serialize_profile(profile)


@router.get("/profiles/me")
def get_my_profile(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = profiles_db.get_profile(session, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not set up")
    return _serialize_profile(profile)


@router.get("/cycle")
def get_cycle(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = profiles_db.get_profile(session, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not set up")
    return {"timeline": compute_timeline(profile)}


@router.get("/calendar")
def get_calendar(
    month: str | None = Query(default=None),
    language: str = Query(default="EN"),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = profiles_db.get_profile(session, user)
    return build_calendar(profile, month=month, language=language).model_dump(mode="json")


@router.post("/capture")
def take_data(
    language: str = Query(default="EN"),
    scenario: str | None = Query(default=None),
    muscle_groups: str | None = Query(default=None),
    exercises_count: int | None = Query(default=None),
    time_budget_minutes: int | None = Query(default=None),
    energy_level: str | None = Query(default=None),
    include_warmup: bool = Query(default=True),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = profiles_db.get_profile(session, user)
    groups = [g.strip() for g in muscle_groups.split(",")] if muscle_groups else None
    result = capture(
        session,
        user,
        profile,
        language=language,
        scenario=scenario,
        muscle_groups=groups,
        exercises_count=exercises_count,
        time_budget_minutes=time_budget_minutes,
        energy_level=energy_level,
        include_warmup=include_warmup,
    )
    session.commit()
    return result


@router.get("/routine/latest")
def latest_routine(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    routine = (
        session.query(Routine)
        .filter_by(user_id=user.id)
        .order_by(Routine.created_at.desc())
        .first()
    )
    if routine is None:
        raise HTTPException(status_code=404, detail="no routine yet")
    return {
        "routine_id": routine.id,
        "language": routine.language,
        "muscle_groups": routine.muscle_groups,
        "total_estimated_minutes": routine.total_estimated_minutes,
        "phase_inferred": routine.phase_inferred,
        "k_load": routine.k_load,
        "items": [
            {
                "order_index": item.order_index,
                "exercise_id": item.exercise_id,
                "name": item.name,
                "role": item.role,
                "blocked": item.blocked,
                "block_reason": item.block_reason,
                "substitute": item.substitute,
                "series": item.series,
                "reps": item.reps,
                "weight_suggested_kg": item.weight_suggested_kg,
                "rest_seconds": item.rest_seconds,
                "estimated_seconds": item.estimated_seconds,
                "image_url": item.image_url,
                "sets": item.sets,
                "description": item.description,
                "how_to": item.how_to,
                "tips": item.tips,
            }
            for item in routine.items
        ],
    }


@router.get("/supplements/catalog")
def supplements_catalog_endpoint(language: str = Query(default="EN")) -> list[dict[str, Any]]:
    return supplements_catalog(language)


@router.get("/stats")
def stats(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = profiles_db.get_profile(session, user)
    return compute_stats(session, user, profile)


@router.post("/supplement-intakes")
def set_supplement_intake(
    payload: dict[str, Any],
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    supplement_id = str(payload.get("supplement_id", ""))
    date_str = str(payload.get("date", date.today().isoformat()))
    taken = bool(payload.get("taken", False))
    if not supplement_id:
        raise HTTPException(status_code=422, detail="supplement_id required")
    row = (
        session.query(SupplementIntake)
        .filter_by(user_id=user.id, supplement_id=supplement_id, date=date.fromisoformat(date_str))
        .one_or_none()
    )
    if row is None:
        row = SupplementIntake(
            user_id=user.id,
            supplement_id=supplement_id,
            date=date.fromisoformat(date_str),
            taken=taken,
        )
        session.add(row)
    else:
        row.taken = taken
    session.commit()
    return {"supplement_id": supplement_id, "date": date_str, "taken": taken}


@router.get("/supplement-intakes")
def get_supplement_intakes(
    date_str: str | None = Query(default=None, alias="date"),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    query = session.query(SupplementIntake).filter_by(user_id=user.id)
    if date_str:
        query = query.filter_by(date=date.fromisoformat(date_str))
    return [
        {"supplement_id": row.supplement_id, "date": row.date.isoformat(), "taken": row.taken}
        for row in query.all()
    ]


@router.post("/shares")
def post_share(
    payload: dict[str, Any],
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from syncfit_contracts import SharePermission, ShareRole

    try:
        role = ShareRole(payload.get("role", "OTHER")).value
        permissions = [SharePermission(p).value for p in payload.get("permissions", [])]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not permissions:
        raise HTTPException(status_code=422, detail="select at least one permission")
    link = create_share(session, user, role, permissions, payload.get("label"))
    session.commit()
    session.refresh(link)
    return serialize_link(link)


@router.get("/shares")
def get_shares(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return [serialize_link(link) for link in list_shares(session, user)]


@router.delete("/shares/{token}")
def remove_share(
    token: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if not delete_share(session, user, token):
        raise HTTPException(status_code=404, detail="share not found")
    session.commit()
    return {"deleted": token}


@router.get("/shared/{token}")
def get_shared_profile(
    token: str,
    language: str = Query(default="EN"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    shared = build_shared_profile(session, token, language)
    if shared is None:
        raise HTTPException(status_code=404, detail="share not found")
    return shared.model_dump(mode="json")


def _serialize_profile(profile) -> dict[str, Any]:
    return {
        "profile_id": profile.id,
        "user_id": profile.user_id,
        "language": profile.language,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "body_fat_pct": profile.body_fat_pct,
        "daily_calories": profile.daily_calories,
        "age": profile.age,
        "objective": profile.objective,
        "goal_phase": profile.goal_phase,
        "modality": profile.modality,
        "available_machines": list(profile.available_machines or []),
        "symptoms": list(profile.symptoms or []),
        "pain_levels": dict(profile.pain_levels or {}),
        "symptom_notes": profile.symptom_notes,
        "current_supplements": list(profile.current_supplements or []),
        "supplement_macros": list(profile.supplement_macros or []),
        "weight_unit": profile.weight_unit or "KG",
        "photo_url": profile.photo_url,
        "last_period_date": profile.last_period_date.isoformat() if profile.last_period_date else None,
        "cycle_length_days": profile.cycle_length_days,
        "gestation_week": profile.gestation_week,
        "due_date": profile.due_date.isoformat() if profile.due_date else None,
        "loads": [
            {"exercise_id": load.exercise_id, "weight_kg": load.weight_kg, "reps": load.reps}
            for load in profile.loads
        ],
        "timeline": compute_timeline(profile),
    }


__all__ = ["router"]
