"""Turn what the athlete types ("hip thrust con barra", "sentadia bulgara") into
catalog exercises she can swap in, ranked by how well they replace the one in
her routine: same movement pattern first, then same muscles, then the rest.
"""

from __future__ import annotations

import difflib
import unicodedata
from typing import Any

from syncfit_contracts import get_exercise, load_exercises, localize, patterns_of

_REASON = {
    "same_pattern": {
        "es": "Mismo patrón de movimiento: buen reemplazo.",
        "en": "Same movement pattern: a good replacement.",
        "zh": "相同的动作模式：很好的替代。",
    },
    "same_muscles": {
        "es": "Trabaja los mismos músculos, con otro movimiento.",
        "en": "Works the same muscles with a different movement.",
        "zh": "训练相同肌群，但动作不同。",
    },
    "different": {
        "es": "Trabaja otros músculos: cambia el enfoque de la rutina.",
        "en": "Works other muscles: it changes the focus of the routine.",
        "zh": "训练其他肌群：会改变训练重点。",
    },
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).replace("-", " ").strip()


def _names(exercise) -> list[str]:
    names = [exercise.name.en, exercise.id.replace("-", " ")]
    names += [str(v) for v in (exercise.name.model_extra or {}).values() if v]
    return [_norm(n) for n in names]


def _score(query: str, names: list[str]) -> float:
    words = set(query.split())
    best = 0.0
    for name in names:
        ratio = difflib.SequenceMatcher(None, query, name).ratio()
        name_words = set(name.split())
        overlap = len(words & name_words) / max(len(words), 1)
        fuzzy = max(
            (max((difflib.SequenceMatcher(None, w, n).ratio() for n in name_words), default=0) for w in words),
            default=0,
        )
        contains = 1.0 if query and query in name else 0.0
        best = max(best, 0.45 * ratio + 0.35 * overlap + 0.1 * fuzzy + 0.25 * contains)
    return best


def suggest(
    exercise_id: str,
    text: str,
    language: str = "EN",
    exclude_supine: bool = False,
    limit: int = 5,
) -> list[dict[str, Any]]:
    query = _norm(text)
    if len(query) < 2:
        return []
    original = get_exercise(exercise_id)
    pattern = patterns_of(original) if original is not None else None
    muscles = {str(m).split(".")[-1] for m in (original.muscle_groups or [])} if original is not None else set()
    code = language.lower() if language.lower() in ("es", "en", "zh") else "en"

    ranked = []
    for exercise in load_exercises():
        if exercise.id == exercise_id:
            continue
        if exclude_supine and getattr(exercise, "supine", False):
            continue
        role = str(getattr(exercise, "role", "MAIN") or "MAIN").split(".")[-1]
        if role in ("WARMUP", "ACTIVATION"):
            continue
        match = _score(query, _names(exercise))
        if match < 0.42:
            continue
        if pattern and patterns_of(exercise) == pattern:
            fit, bonus = "same_pattern", 0.3
        elif muscles & {str(m).split(".")[-1] for m in (exercise.muscle_groups or [])}:
            fit, bonus = "same_muscles", 0.15
        else:
            fit, bonus = "different", 0.0
        ranked.append((match + bonus, match, fit, exercise))
    ranked.sort(key=lambda row: (-row[0], -row[1]))
    return [
        {
            "id": exercise.id,
            "name": localize(exercise.name, language),
            "image_url": exercise.image_url,
            "fit": fit,
            "reason": _REASON[fit][code],
            "match": round(match, 2),
            "supine": bool(getattr(exercise, "supine", False)),
            "setup": exercise.setup.model_dump() if exercise.setup else None,
            "pregnancy_tip": exercise.pregnancy_tip.model_dump() if exercise.pregnancy_tip else None,
        }
        for _, match, fit, exercise in ranked[:limit]
    ]


__all__ = ["suggest"]
