"""Symptom context for the reasoning layer.

The AI decides the routine and how to adapt it to the declared symptoms. This
module only prepares that context and, for the deterministic fallback when the
model is unavailable, a conservative pattern policy. It never pre-filters the
catalog the model sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from syncfit_contracts import get_symptom, localize

# Fallback-only policy. The AI receives the raw severity and decides; these
# ranges are used only when the model is down. "0" or no level keeps the full
# catalog list (conservative, same behaviour as before).
_SEVERITY_RULES: dict[str, tuple[tuple[int, tuple[str, ...]], ...]] = {
    "knee_pain": (
        (3, ("plyometric",)),
        (6, ("plyometric", "lunge")),
        (10, ("lunge", "squat", "leg_extension", "plyometric")),
    ),
    "low_back_pain": (
        (3, ("hinge",)),
        (6, ("hinge", "row")),
        (10, ("hinge", "row")),
    ),
}

# Safety impact cap (not a pattern decision): the model still chooses the
# exercises, but it cannot program above what the pain allows.
_IMPACT_CAP: dict[str, tuple[tuple[int, str], ...]] = {
    "knee_pain": ((3, "MEDIUM"), (10, "LOW")),
    "low_back_pain": ((3, "MEDIUM"), (10, "LOW")),
}
_IMPACT_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

_SEVERITY_NOTE = {
    "ES": "{name}: {level}/10. Adapta carga y rango a lo que no duela.",
    "EN": "{name}: {level}/10. Adapt load and range to what stays pain-free.",
    "ZH": "{name}：{level}/10。请根据无痛范围调整负荷和幅度。",
}


@dataclass(frozen=True)
class SymptomContext:
    """What the athlete reports, in a shape the prompt and the fallback can use."""

    ids: tuple[str, ...]
    severities: dict[str, int]
    overall: int
    stop: bool
    notes: str | None
    suggested_patterns: tuple[str, ...]
    advice: tuple[str, ...]
    guidance: dict[str, str]
    impact_cap: str

    def level_for(self, symptom_id: str) -> int:
        return int(self.severities.get(symptom_id, self.overall) or 0)

    def prompt_payload(self) -> dict[str, Any]:
        return {
            "overall_pain": self.overall,
            "symptoms": [
                {
                    "id": symptom_id,
                    "severity": self.level_for(symptom_id),
                    "suggested_avoid_patterns": list(self.suggested_patterns),
                    "guidance": self.guidance.get(symptom_id, ""),
                }
                for symptom_id in self.ids
            ],
            "notes": self.notes,
            "advice": list(self.advice),
            "impact_cap": self.impact_cap,
        }


def _severity_patterns(symptom_id: str, level: int) -> set[str]:
    """Fallback patterns for one symptom at a given pain level."""
    symptom = get_symptom(symptom_id)
    if symptom is None:
        return set()
    rules = _SEVERITY_RULES.get(symptom_id)
    if rules and level >= 1:
        for maximum, patterns in rules:
            if level <= maximum:
                return set(patterns)
    return {str(pattern) for pattern in symptom.get("avoid_patterns", []) or []}


def build_symptom_context(
    *,
    symptom_ids: list[str] | tuple[str, ...] | None,
    pain_levels: dict[str, int] | None,
    notes: str | None = None,
    extra_avoid: list[str] | tuple[str, ...] | None = None,
    language: str = "EN",
) -> SymptomContext:
    ids = tuple(str(symptom_id) for symptom_id in (symptom_ids or []))
    levels = {str(key): int(value) for key, value in (pain_levels or {}).items() if value is not None}
    overall = int(levels.get("OVERALL", 0) or 0)
    stop = False
    suggested: set[str] = set()
    advice: list[str] = []
    symptom_guidance: dict[str, str] = {}
    impact_cap = "HIGH"
    code = language.lower()

    suggested |= {str(pattern) for pattern in (extra_avoid or [])}

    for symptom_id in ids:
        symptom = get_symptom(symptom_id)
        if symptom is None:
            continue
        level = int(levels.get(symptom_id, overall) or 0)
        if symptom.get("block_training"):
            stop = True
        suggested |= _severity_patterns(symptom_id, level)
        for maximum, cap in _IMPACT_CAP.get(symptom_id, ()):
            if level >= 1 and level <= maximum:
                if _IMPACT_RANK[cap] < _IMPACT_RANK[impact_cap]:
                    impact_cap = cap
                break
        if level > 0:
            name = localize(symptom.get("name", {}), language)
            template = _SEVERITY_NOTE.get(language.upper(), _SEVERITY_NOTE["EN"])
            advice.append(template.format(name=name, level=level))
        symptom_guidance[symptom_id] = (
            (symptom.get("advice") or {}).get(code) or (symptom.get("advice") or {}).get("en") or ""
        )

    return SymptomContext(
        ids=ids,
        severities={symptom_id: int(levels.get(symptom_id, overall) or 0) for symptom_id in ids},
        overall=overall,
        stop=stop,
        notes=(notes or "").strip() or None,
        suggested_patterns=tuple(sorted(suggested)),
        advice=tuple(advice),
        guidance={symptom_id: text for symptom_id, text in symptom_guidance.items() if text},
        impact_cap=impact_cap,
    )


def hard_patterns(context: SymptomContext) -> tuple[str, ...]:
    """Patterns that must never be programmed, regardless of the AI.

    Mild or moderate pain is a decision for the model. Only absolute red flags
    (``block_training``) stop loading, and that is handled separately.
    """
    return ()


def fallback_patterns(context: SymptomContext) -> tuple[str, ...]:
    """Conservative patterns for the deterministic engine when the AI is down."""
    if context.stop:
        return ()
    return context.suggested_patterns


__all__ = [
    "SymptomContext",
    "build_symptom_context",
    "fallback_patterns",
    "hard_patterns",
]
