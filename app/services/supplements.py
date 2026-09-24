"""Supplement advice and daily macronutrient estimate."""

from __future__ import annotations

from syncfit_contracts import (
    GoalPhase,
    MacroNutrients,
    SupplementAdvice,
    SupplementAdviceItem,
    SupplementRequest,
    load_supplements,
    localize,
    supplements_for,
)

_REASON = {
    "SAFE": {"en": "Suitable for your context.", "es": "Adecuado para tu contexto.", "zh": "适合当前情况。"},
    "CAUTION": {
        "en": "Use with caution and confirm with a clinician.",
        "es": "Usar con precaución y confirmar con un clínico.",
        "zh": "谨慎使用，并咨询医生。",
    },
    "AVOID": {
        "en": "Not recommended in this context.",
        "es": "No recomendado en este contexto.",
        "zh": "此情况下不推荐。",
    },
}
_SAFETY_ORDER = {"SAFE": 0, "CAUTION": 1, "AVOID": 2}
_GOAL_CALORIE_FACTOR = {
    "VOLUME": 1.12,
    "DEFINITION": 0.82,
    "MAINTENANCE": 1.0,
    "STRENGTH_FOCUS": 1.05,
    "RECOVERY": 1.0,
}


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def estimate_daily_macros(request: SupplementRequest) -> MacroNutrients | None:
    """Estimate a daily calorie and macro target (Mifflin-St Jeor, female)."""
    weight = request.weight_kg
    if weight is None:
        if request.daily_calories is None:
            return None
        calories = float(request.daily_calories)
    else:
        height = request.height_cm or 165.0
        age = request.age or 30
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
        activity = 1.4
        base = bmr * activity
        factor = _GOAL_CALORIE_FACTOR.get(_value(request.goal_phase or "MAINTENANCE"), 1.0)
        calories = base * factor
        if request.daily_calories:
            calories = (calories + request.daily_calories) / 2

    gestational = _value(request.modality) == "GESTATIONAL"
    protein_per_kg = 1.5 if gestational else 1.8
    fat_per_kg = 0.9
    protein = (weight or 60.0) * protein_per_kg
    fat = (weight or 60.0) * fat_per_kg
    remaining = max(calories - protein * 4 - fat * 9, 0)
    carbs = remaining / 4
    return MacroNutrients(
        protein_g=round(protein, 1),
        carbs_g=round(carbs, 1),
        fat_g=round(fat, 1),
        kcal=round(calories, 0),
    )


def recommend(request: SupplementRequest) -> SupplementAdvice:
    language = _value(request.language)
    modality = _value(request.modality)
    objective = _value(request.objective) if request.objective else None
    goal_phase = _value(request.goal_phase) if request.goal_phase else None

    items: list[SupplementAdviceItem] = []
    for supplement in supplements_for(objective=objective, modality=modality):
        safety = (
            supplement.safety_pregnancy if modality == "GESTATIONAL" else supplement.safety_general
        )
        reason = _REASON.get(_value(safety), _REASON["SAFE"])
        items.append(
            SupplementAdviceItem(
                supplement_id=supplement.id,
                name=supplement.name,
                category=supplement.category,
                safety=safety,
                dosage=supplement.dosage,
                macros=supplement.macros,
                reason=reason,
                image_url=supplement.image_url,
            )
        )

    # Order: safest first (SAFE, then CAUTION, then AVOID).
    items.sort(key=lambda item: _SAFETY_ORDER.get(_value(item.safety), 3))

    return SupplementAdvice(
        language=language,
        modality=modality,
        objective=objective,
        goal_phase=goal_phase,
        daily_macros=estimate_daily_macros(request),
        items=items,
    )


__all__ = ["recommend", "estimate_daily_macros", "catalog"]


def catalog(language: str = "EN") -> list[dict]:
    """Raw supplement catalog with brands/frequency for reminders."""
    result: list[dict] = []
    for supplement in load_supplements():
        result.append(
            {
                "id": supplement.id,
                "name": localize(supplement.name, language),
                "category": str(supplement.category),
                "dosage": localize(supplement.dosage, language),
                "frequency": str(supplement.frequency) if supplement.frequency else None,
                "is_daily": supplement.is_daily,
                "brand_examples": list(supplement.brand_examples),
                "macros": supplement.macros.model_dump(),
                "safety_general": str(supplement.safety_general),
                "safety_pregnancy": str(supplement.safety_pregnancy),
                "notes": localize(supplement.notes, language),
            }
        )
    return result
