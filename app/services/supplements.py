"""Supplement advice for a context, from the shared catalog."""

from __future__ import annotations

from syncfit_contracts import (
    SupplementAdvice,
    SupplementAdviceItem,
    SupplementRequest,
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


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def recommend(request: SupplementRequest) -> SupplementAdvice:
    language = _value(request.language)
    modality = _value(request.modality)
    objective = _value(request.objective) if request.objective else None

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
    return SupplementAdvice(
        language=language,
        modality=modality,
        objective=objective,
        items=items,
    )


__all__ = ["recommend"]
