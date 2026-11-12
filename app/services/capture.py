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
from syncfit_contracts import RoutineRequest, get_exercise, patterns_of
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

from ..config import settings
from .cycles import compute_timeline
from .engine import engine_result
from .gyms import available_equipment_keys, available_exercise_ids, station_index
from .live import latest as latest_live
from .loads import adjust_entries
from .machines import factor_for_exercise
from .ordering import order_entries
from .symptom_policy import build_symptom_context, fallback_patterns, hard_patterns
from .symptoms import apply_symptoms
from .routines import generate_routine

DEFAULT_GROUPS = ["LOWER_BODY", "UPPER_BODY", "CORE"]

_ALERT_LABELS = {
    "EN": {"notes": "Notes", "pain": "Pain"},
    "ES": {"notes": "Notas", "pain": "Dolor"},
    "ZH": {"notes": "备注", "pain": "疼痛"},
}


def _label(language: str, key: str) -> str:
    labels = _ALERT_LABELS.get(language.upper(), _ALERT_LABELS["EN"])
    return labels.get(key, key)


def _annotate_machines(entries: list[dict], station_map: dict[str, dict]) -> list[dict]:
    """Tag entries that map to a gym machine with its id, name and photo."""
    annotated: list[dict] = []
    for entry in entries:
        item = dict(entry)
        station = station_map.get(item.get("exercise_id"))
        if station:
            item["machine_id"] = station["id"]
            item["machine_name"] = station["name"]
            if station.get("image_url"):
                item["image_url"] = station["image_url"]
        annotated.append(item)
    return annotated


def _with_catalog_flags(entries: list[dict]) -> list[dict]:
    """Fill `compound` / `movement_pattern` from the catalog before ordering.

    Generators and symptom substitutions do not always carry those flags; the
    sequencing rules (compound -> unilateral -> accessory) need them.
    """
    for entry in entries:
        exercise_id = entry.get("exercise_id")
        exercise = get_exercise(exercise_id) if exercise_id else None
        if exercise is None:
            continue
        if not entry.get("movement_pattern"):
            entry["movement_pattern"] = patterns_of(exercise)
        if entry.get("compound") is None:
            entry["compound"] = bool(getattr(exercise, "compound", False))
    return entries


def _scenario_for(modality: str, phase: str | None) -> str:
    if modality == "GESTATIONAL":
        return "gestational_t2"
    if phase == "OVULATORY":
        return "high_risk"
    if phase == "LUTEAL":
        return "fatigue"
    return "normal"


def _autonomic_status(rmssd: float, fatigue: str) -> str:
    if fatigue == "HIGH":
        return "PARASYMPATHETIC_WITHDRAWAL"
    if rmssd < 25:
        return "SYMPATHETIC_DOMINANT"
    return "BALANCED"


def _articular_risk(core) -> float:
    phase = core.phase_inferred.value
    bonus = {"OVULATORY": 30.0, "TRIMESTER_3": 25.0, "TRIMESTER_2": 15.0}.get(phase, 0.0)
    return round(min(100.0, core.fatigue_probability * 60.0 + bonus), 1)


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
    use_live: bool = True,
) -> dict:
    """Run the simulated capture and persist session, telemetry and routine."""
    timeline = compute_timeline(profile) if profile is not None else None
    modality = (profile.modality if profile is not None else None) or "MENSTRUAL_CYCLE"
    phase = timeline.get("phase") if timeline else None
    day_or_week = None
    if timeline:
        day_or_week = timeline.get("cycle_day") or timeline.get("week")

    live = latest_live() if use_live and scenario is None else None
    if live is not None:
        # Real device: keep its biomarkers and PPG window, but the cycle data
        # comes from the athlete's profile so the phase inference matches.
        scenario_name = "device"
        frame = dict(live.frame)
        frame["modality"] = modality
        if day_or_week is not None:
            frame["day_or_week"] = day_or_week
    else:
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

    # Machines of the athlete's active gym: prefer exercises they cover.
    station_map, preferred = ({}, set())
    if profile is not None:
        station_map, preferred = station_index(session, profile, language)

    # Machine-first: summarize the active gym's machines (pattern -> machine) for
    # the reasoning layer and for visibility in the response.
    gym_machines: list[dict] = []
    machine_preferences: dict[str, dict] = {}
    for exercise_id in sorted(preferred):
        station = station_map.get(exercise_id)
        exercise = get_exercise(exercise_id)
        pattern = patterns_of(exercise) if exercise is not None else None
        summary = {
            "exercise_id": exercise_id,
            "pattern": pattern,
            "name": station.get("name_text") if station else None,
            "weight_factor": station.get("weight_factor") if station else None,
            "image_url": station.get("image_url") if station else None,
        }
        gym_machines.append(summary)
        if pattern and pattern not in machine_preferences:
            machine_preferences[pattern] = summary

    equipment = available_equipment_keys(session, profile) if profile is not None else None
    allowed_ids = available_exercise_ids(session, profile) if profile is not None else set()
    symptom_ids = list(profile.symptoms or []) if profile is not None else []
    symptom_notes = profile.symptom_notes if profile is not None else None
    extra_avoid = (
        list(getattr(profile, "symptom_avoid_patterns", None) or [])
        if profile is not None
        else []
    )
    symptom_context = build_symptom_context(
        symptom_ids=symptom_ids,
        pain_levels=profile.pain_levels if profile is not None else None,
        notes=symptom_notes,
        extra_avoid=extra_avoid,
        language=language,
    )
    # The model decides how to adapt the routine to the pain. Only absolute red
    # flags are hard blocks; the pattern policy below is for the fallback when
    # the model is unavailable.
    contraindicated = list(hard_patterns(symptom_context))
    fallback_blocked = list(fallback_patterns(symptom_context))
    context_payload = symptom_context.prompt_payload()

    # Local model -> structured assessment consumed by the reasoning layer.
    assessment = {
        "schema_version": "1.12.0",
        "phase_inferred": core.phase_inferred.value,
        "fatigue_level": core.fatigue_level.value,
        "k_load_multiplier": core.k_load,
        "autonomic_status": _autonomic_status(core.rmssd_hrv_ms, core.fatigue_level.value),
        "articular_risk_pct": _articular_risk(core),
        "contraindicated_patterns": contraindicated,
        "symptom_context": context_payload,
        "notes": [],
        "source": "core",
    }

    request = RoutineRequest(
        session_id=str(uuid.uuid4()),
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
    # OpenCode models reason from the assessment; deterministic evidence is the
    # last resort if both generative calls are unavailable.
    try:
        payload = generate_routine(
            request,
            engine=settings.routine_engine,
            preferred_exercise_ids=list(preferred),
            contraindicated_patterns=contraindicated,
            gym_machines=gym_machines,
            assessment=assessment,
            symptom_context=context_payload,
            impact_cap=symptom_context.impact_cap,
            equipment_keys=None if equipment is None else list(equipment),
            available_exercise_ids=list(allowed_ids),
            symptom_notes=symptom_notes,
        )
    except Exception:
        payload = generate_routine(
            request,
            engine="deterministic",
            preferred_exercise_ids=list(preferred),
            contraindicated_patterns=fallback_blocked,
            gym_machines=gym_machines,
            assessment=assessment,
            symptom_context=context_payload,
            impact_cap=symptom_context.impact_cap,
            equipment_keys=None if equipment is None else list(equipment),
            available_exercise_ids=list(allowed_ids),
            symptom_notes=symptom_notes,
        )
    phase_name = payload.get("phase_inferred") or core.phase_inferred.value
    ordered = order_entries(_with_catalog_flags(payload["routine"]), phase_name, language)
    warmup = payload.get("warmup", [])

    # Apply declared symptoms (stop if an absolute contraindication is present).
    ordered, symptom_alerts, block_training = apply_symptoms(ordered, symptom_ids, language)
    warmup, _, _ = apply_symptoms(warmup, symptom_ids, language)
    if profile is not None and profile.symptom_notes:
        symptom_alerts.append(f"{_label(language, 'notes')}: {profile.symptom_notes}")
    if block_training:
        ordered = []
        warmup = []
    else:
        # Substitutions can change the movement pattern: keep the sequence valid.
        ordered = order_entries(_with_catalog_flags(ordered), phase_name, language)

    # Tag exercises handled by one of the athlete's gym machines (id, name, photo).
    ordered = _annotate_machines(ordered, station_map)
    warmup = _annotate_machines(warmup, station_map)

    # Apply the athlete's baseline loads, adjusted per available machine.
    if profile is not None and profile.loads:
        available = list(profile.available_machines or [])
        factors: dict[str, float] = {}
        for entry in ordered + warmup:
            exercise_id = entry.get("exercise_id")
            if not exercise_id or exercise_id in factors:
                continue
            station = station_map.get(exercise_id)
            factors[exercise_id] = (
                station["weight_factor"] if station else factor_for_exercise(exercise_id, available)
            )
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
                setup=entry.get("setup") or {},
                pregnancy_tip=entry.get("pregnancy_tip") or None,
                tips=entry.get("tips") or [],
                machine_id=entry.get("machine_id"),
                machine_name=entry.get("machine_name"),
                movement_pattern=entry.get("movement_pattern"),
                rationale=entry.get("rationale"),
            )
        )
    session.add(routine)
    session.flush()

    groups_by_id = {
        entry.get("exercise_id"): list(entry.get("muscle_groups") or []) for entry in ordered
    }

    alerts = list(symptom_context.advice) + list(symptom_alerts)
    if ordered:
        alerts.append(
            {
                "ES": f"Rutina con {len(ordered)} ejercicios; no se repite el mismo tipo de ejercicio.",
                "EN": f"Routine with {len(ordered)} exercises; no exercise type is repeated.",
                "ZH": f"共 {len(ordered)} 个动作，同类动作不重复。",
            }.get(language.upper(), f"Routine with {len(ordered)} exercises.")
        )
    empty_reason = None
    if not ordered:
        if block_training:
            empty_reason = "TRAINING_BLOCKED"
        elif symptom_context.ids:
            empty_reason = "SYMPTOMS_BLOCK_ALL"
        else:
            empty_reason = "NO_EXERCISES"
        alerts.append(
            {
                "ES": "No quedaron ejercicios seguros para este grupo. Revisa tus síntomas o elige otra zona.",
                "EN": "No safe exercises left for this group. Check your symptoms or pick another area.",
                "ZH": "该部位没有安全的动作。请检查症状或选择其他部位。",
            }.get(language.upper(), "No safe exercises left for this group.")
        )

    return {
        "session_id": record.id,
        "routine_id": routine.id,
        "scenario": scenario_name,
        "capture_source": "device" if live is not None else "simulated",
        "phase_inferred": core.phase_inferred.value,
        "fatigue_level": core.fatigue_level.value,
        "k_load": core.k_load,
        "assessment": assessment,
        "engine_used": payload.get("engine_used", "deterministic"),
        "machine_preferences": machine_preferences,
        "biomarkers": dict(frame["biomarkers"]),
        "timeline": timeline,
        "total_estimated_minutes": payload.get("total_estimated_minutes"),
        "alerts": alerts,
        "empty_reason": empty_reason,
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
                "setup": item.setup,
                "pregnancy_tip": item.pregnancy_tip,
                "tips": item.tips,
                "machine_id": item.machine_id,
                "machine_name": item.machine_name,
                "movement_pattern": item.movement_pattern,
                "muscle_groups": groups_by_id.get(item.exercise_id, []),
                "rationale": item.rationale,
            }
            for item in routine.items
        ],
    }


__all__ = ["capture", "DEFAULT_GROUPS"]
