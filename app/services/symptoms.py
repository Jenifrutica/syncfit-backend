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


def apply_symptoms(
    entries: list[dict[str, Any]],
    symptom_ids: list[str],
    language: str = "EN",
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Return (entries, alerts, block_training)."""
    from syncfit_contracts import get_symptom

    alerts: list[str] = []
    block_training = False
    keywords: list[tuple[str, dict]] = []
    for symptom_id in symptom_ids:
        symptom = get_symptom(symptom_id)
        if symptom is None:
            continue
        advice = _reason(symptom, language)
        if advice:
            alerts.append(advice)
        if symptom.get("block_training"):
            block_training = True
        for kw in symptom.get("avoid_keywords", []):
            keywords.append((kw.lower(), symptom))

    if block_training:
        return [], alerts, True

    adjusted: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        name = str(item.get("exercise_original", "")).lower()
        for keyword, symptom in keywords:
            if keyword and keyword in name and not item.get("blocked"):
                item["blocked"] = True
                item["block_reason"] = _reason(symptom, language)
                item["exercise_substitute"] = item.get("exercise_substitute") or _localized_substitute(
                    symptom["id"], language
                )
                break
        adjusted.append(item)
    return adjusted, alerts, False


__all__ = ["apply_symptoms"]
