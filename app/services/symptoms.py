"""Apply symptoms to a generated routine (block risky exercises, add advice)."""

from __future__ import annotations

from typing import Any

from syncfit_core.enums import Modality

from .cycles import compute_timeline

SUBSTITUTES = {
    "knee_pain": {"en": "Sumo deadlift / hip thrust (knee-friendly)", "es": "Peso muerto sumo / hip thrust (amigable con rodilla)", "zh": "相扑硬拉/臀推（对膝友好）"},
    "low_back_pain": {"en": "Supported row / goblet squat", "es": "Remo con apoyo / sentadilla goblet", "zh": "有支撑划船/高脚杯深蹲"},
    "cramps": {"en": "Light mobility and stretching", "es": "Movilidad y estiramiento suaves", "zh": "轻度活动与拉伸"},
}
_IMPACT_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def _reason(symptom: dict, language: str) -> str:
    advice = symptom.get("advice", {})
    return advice.get(language.lower(), advice.get("en", ""))


def _localized_substitute(symptom_id: str, language: str) -> str:
    data = SUBSTITUTES.get(symptom_id)
    if not data:
        return ""
    return data.get(language.lower(), data.get("en", ""))


def _gentle_entries(language: str) -> list[dict]:
    from syncfit_contracts import load_exercises, localize

    gentle = []
    for e in load_exercises():
        role = str(getattr(e, "role", "MAIN"))
        if role in ("WARMUP", "ACTIVATION") and str(e.impact) == "LOW":
            gentle.append(
                {
                    "exercise_original": localize(e.name, language),
                    "blocked": False,
                    "block_reason": "",
                    "exercise_substitute": "",
                    "series_adapted": 2,
                    "reps_adapted": 12,
                    "weight_suggested_kg": 0.0,
                    "exercise_id": e.id,
                    "muscle_groups": list(e.muscle_groups),
                    "impact": "LOW",
                    "role": role,
                    "description": (lambda d: {"en": d.en, **(d.model_extra or {})})(e.description),
                    "how_to": (lambda d: {"en": d.en, **(d.model_extra or {})})(e.how_to or e.description),
                    "tips": [{"en": t.en, **(t.model_extra or {})} for t in (e.tips or [])],
                    "image_url": e.image_url,
                    "media_url": e.media_url,
                    "rest_seconds": 30,
                    "estimated_seconds": 66,
                    "sets": [],
                }
            )
            if len(gentle) >= 3:
                break
    return gentle


def apply_symptoms(
    entries: list[dict[str, Any]],
    symptom_ids: list[str],
    language: str = "EN",
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """AI-first: only absolute contraindications stop loading; else no blocking here.

    Keyword-based blocking was removed on purpose. The AI reasons about symptoms
    (see analyze_symptoms). This function only enforces the hard safety stop and
    returns a gentle, still-active routine in that case.
    """
    from syncfit_contracts import get_symptom

    alerts: list[str] = []
    block_training = False
    for symptom_id in symptom_ids:
        symptom = get_symptom(symptom_id)
        if symptom is None:
            continue
        advice = _reason(symptom, language)
        if advice:
            alerts.append(advice)
        if symptom.get("block_training"):
            block_training = True

    if block_training:
        alerts.append("Contraindicacion absoluta: rutina suave de movilidad y estiramientos.")
        return _gentle_entries(language), alerts, True

    # No hard stop: leave the routine as-is; the AI decides adaptations.
    return entries, alerts, False


__all__ = ["apply_symptoms"]
