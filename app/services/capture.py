"""Capture flow: simulated telemetry -> core -> routine -> persistence.

This is the "Tomar datos" action. Data is simulated for now (several scenarios),
but the flow is identical to the hardware path: validate the frame, run the
deterministic core, generate and medically order the routine, and store
everything in the database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from syncfit_contracts import RoutineRequest
from syncfit_database import (
    EnergyCheckIn,
    Profile,
    Routine,
    RoutineExercise,
    SessionRecord,
    TelemetrySample,
    User,
)
from syncfit_simulator import generate_frame, get_scenario

from .cycles import compute_timeline
from .engine import engine_result
from .loads import adjust_entries
from .machines import factor_for_exercise
from .ordering import order_entries
from .routines import generate_routine

DEFAULT_GROUPS = ["LOWER_BODY", "UPPER_BODY", "CORE"]


def _scenario_for(modality: str, phase: str | None) -> str:
    if modality == "GESTATIONAL":
        return "gestational_t2"
    if phase == "OVULATORY":
        return "high_risk"
    if phase == "LUTEAL":
        return "fatigue"
    return "normal"


def _latest_energy(session: Session, user_id: str) -> str | None:
    row = (
        session.query(EnergyCheckIn)
        .filter_by(user_id=user_id)
        .order_by(EnergyCheckIn.timestamp.desc())
        .first()
    )
    return row.energy_level if row else None


def capture(
    session: Session,
    user: User,
    profile: Profile | None,
    language: str = "EN",
    scenario: str | None = None,
    muscle_groups: list[str] | None = None,
    exercises_count: int | None = None,
    time_budget_minutes: int | None = None,
    energy_level: str | None = None,
    include_warmup: bool = True,
) -> dict:
    """Run the simulated capture and persist session, telemetry and routine."""
    timeline = compute_timeline(profile) if profile is not None else None
    modality = (profile.modality if profile is not None else None) or "MENSTRUAL_CYCLE"
    phase = timeline.get("phase") if timeline else None
    day_or_week = None
    if timeline:
        day_or_week = timeline.get("cycle_day") or timeline.get("week")

    scenario_name = scenario or _scenario_for(modality, phase)
    scenario_obj = get_scenario(scenario_name)
    frame = generate_frame(
        scenario_obj,
        session_id=str(uuid.uuid4()),
        device_id="simulated-device",
        window_size=256,
    )
    core = engine_result(frame)
    groups = muscle_groups or DEFAULT_GROUPS
    energy = energy_level or _latest_energy(session, user.id)

    request = RoutineRequest(
        muscle_groups=groups,
        language=language,
        modality=modality,
        day_or_week=day_or_week,
        telemetry=frame,
        exercises_count=exercises_count or 5,
        time_budget_minutes=time_budget_minutes,
        energy_level=energy,
        objective=profile.objective if profile is not None else None,
        include_warmup=include_warmup,
    )
    payload = generate_routine(request, engine="simulator")
    ordered = order_entries(
        payload["routine"], payload.get("phase_inferred") or core.phase_inferred.value, language
    )
    warmup = payload.get("warmup", [])

    # Apply the athlete's baseline loads, adjusted per available machine.
    if profile is not None and profile.loads:
        available = list(profile.available_machines or [])
        factors = {
            entry.get("exercise_id"): factor_for_exercise(entry.get("exercise_id", ""), available)
            for entry in ordered + warmup
            if entry.get("exercise_id")
        }
        ordered = adjust_entries(ordered, profile.loads, core.k_load, energy, factors)
        warmup = adjust_entries(warmup, profile.loads, core.k_load, energy, factors)

    record = SessionRecord(
        user_id=user.id,
        modality=modality,
        day_or_week=day_or_week,
        phase_inferred=core.phase_inferred.value,
        fatigue_level=core.fatigue_level.value,
        k_load=core.k_load,
        source="simulated",
    )
    record.samples.append(
        TelemetrySample(
            timestamp=datetime.now(timezone.utc),
            delta_temperature_c=frame["biomarkers"]["delta_temperature_c"],
            rmssd_hrv_ms=frame["biomarkers"]["rmssd_hrv_ms"],
            isometric_force_loss_pct=frame["biomarkers"]["isometric_force_loss_pct"],
        )
    )
    session.add(record)
    session.flush()

    routine = Routine(
        user_id=user.id,
        session_id=record.id,
        language=language,
        muscle_groups=groups,
        total_estimated_minutes=payload.get("total_estimated_minutes"),
        phase_inferred=core.phase_inferred.value,
        k_load=core.k_load,
    )
    for index, entry in enumerate(ordered):
        routine.items.append(
            RoutineExercise(
                order_index=index,
                exercise_id=entry.get("exercise_id"),
                name=entry["exercise_original"],
                role=entry.get("role"),
                blocked=entry["blocked"],
                block_reason=entry.get("block_reason"),
                substitute=entry.get("exercise_substitute"),
                series=entry["series_adapted"],
                reps=entry["reps_adapted"],
                weight_suggested_kg=entry["weight_suggested_kg"],
                rest_seconds=entry.get("rest_seconds"),
                estimated_seconds=entry.get("estimated_seconds"),
                image_url=entry.get("image_url"),
                sets=entry.get("sets", []),
                description=entry.get("description") or {},
                how_to=entry.get("how_to") or {},
                tips=entry.get("tips") or [],
            )
        )
    session.add(routine)
    session.flush()

    return {
        "session_id": record.id,
        "routine_id": routine.id,
        "scenario": scenario_name,
        "phase_inferred": core.phase_inferred.value,
        "fatigue_level": core.fatigue_level.value,
        "k_load": core.k_load,
        "timeline": timeline,
        "total_estimated_minutes": payload.get("total_estimated_minutes"),
        "warmup": warmup,
        "routine": [
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


__all__ = ["capture", "DEFAULT_GROUPS"]
