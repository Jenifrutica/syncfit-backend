"""Selectable values of the app, stored in the `app_options` table."""

from __future__ import annotations

from sqlalchemy.orm import Session
from syncfit_database import AppOption

ISOLATED = "muscle_group_isolated"
GENERAL = "muscle_group_general"
OBJECTIVE = "objective"
GOAL_PHASE = "goal_phase"

# (category, value, labels). The order of the list is the display order.
DEFAULT_OPTIONS: list[tuple[str, str, dict[str, str]]] = [
    (ISOLATED, "GLUTES", {"en": "Glutes", "es": "Glúteos", "zh": "臀肌"}),
    (ISOLATED, "QUADRICEPS", {"en": "Quadriceps", "es": "Cuádriceps", "zh": "股四头肌"}),
    (ISOLATED, "HAMSTRINGS", {"en": "Hamstrings", "es": "Isquiotibiales", "zh": "腘绳肌"}),
    (ISOLATED, "CALVES", {"en": "Calves", "es": "Gemelos", "zh": "小腿"}),
    (ISOLATED, "ABS", {"en": "Abs", "es": "Abdomen", "zh": "腹肌"}),
    (ISOLATED, "OBLIQUES", {"en": "Obliques", "es": "Oblicuos", "zh": "腹斜肌"}),
    (ISOLATED, "BACK", {"en": "Back", "es": "Espalda", "zh": "背部"}),
    (ISOLATED, "LATS", {"en": "Lats", "es": "Dorsales", "zh": "背阔肌"}),
    (ISOLATED, "CHEST", {"en": "Chest", "es": "Pecho", "zh": "胸部"}),
    (ISOLATED, "SHOULDERS", {"en": "Shoulders", "es": "Hombros", "zh": "肩部"}),
    (ISOLATED, "BICEPS", {"en": "Biceps", "es": "Bíceps", "zh": "肱二头肌"}),
    (ISOLATED, "TRICEPS", {"en": "Triceps", "es": "Tríceps", "zh": "肱三头肌"}),
    (ISOLATED, "FOREARMS", {"en": "Forearms", "es": "Antebrazos", "zh": "前臂"}),
    (GENERAL, "UPPER_BODY", {"en": "Upper body", "es": "Tren superior", "zh": "上肢"}),
    (GENERAL, "LOWER_BODY", {"en": "Lower body", "es": "Tren inferior", "zh": "下肢"}),
    (GENERAL, "FULL_BODY", {"en": "Full body", "es": "Cuerpo completo", "zh": "全身"}),
    (GENERAL, "CORE", {"en": "Core", "es": "Core", "zh": "核心"}),
    (GENERAL, "FULL_LEG", {"en": "Full leg", "es": "Pierna completa", "zh": "全腿"}),
    (OBJECTIVE, "STRENGTH", {"en": "Strength", "es": "Fuerza", "zh": "力量"}),
    (OBJECTIVE, "HYPERTROPHY", {"en": "Hypertrophy", "es": "Hipertrofia", "zh": "增肌"}),
    (OBJECTIVE, "FAT_LOSS", {"en": "Fat loss", "es": "Pérdida de grasa", "zh": "减脂"}),
    (OBJECTIVE, "HEALTH", {"en": "Health", "es": "Salud", "zh": "健康"}),
    (OBJECTIVE, "RECOVERY", {"en": "Recovery", "es": "Recuperación", "zh": "恢复"}),
    (OBJECTIVE, "PERFORMANCE", {"en": "Performance", "es": "Rendimiento", "zh": "运动表现"}),
    (OBJECTIVE, "GESTATIONAL_HEALTH", {"en": "Gestational health", "es": "Salud gestacional", "zh": "孕期健康"}),
    (GOAL_PHASE, "VOLUME", {"en": "Volume (bulk)", "es": "Volumen", "zh": "增肌期"}),
    (GOAL_PHASE, "DEFINITION", {"en": "Definition (cut)", "es": "Definición", "zh": "减脂期"}),
    (GOAL_PHASE, "MAINTENANCE", {"en": "Maintenance", "es": "Mantenimiento", "zh": "维持"}),
    (GOAL_PHASE, "STRENGTH_FOCUS", {"en": "Strength focus", "es": "Enfoque fuerza", "zh": "力量优先"}),
    (GOAL_PHASE, "RECOVERY", {"en": "Recovery", "es": "Recuperación", "zh": "恢复期"}),
]


def ensure_default_options(session: Session) -> int:
    """Insert the options that are missing; rows already in the table are never touched.

    That way an edit made directly in the database survives a restart.
    """
    existing = {(o.category, o.value) for o in session.query(AppOption).all()}
    added = 0
    for order, (category, value, labels) in enumerate(DEFAULT_OPTIONS):
        if (category, value) in existing:
            continue
        session.add(AppOption(category=category, value=value, labels=labels, sort_order=order))
        added += 1
    session.flush()
    return added


def list_options(session: Session, language: str = "EN") -> dict[str, list[dict]]:
    """Active options grouped by category, in display order, with the label in `language`."""
    code = language.lower()
    rows = (
        session.query(AppOption)
        .filter(AppOption.active.is_(True))
        .order_by(AppOption.category, AppOption.sort_order)
        .all()
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        labels = row.labels or {}
        label = labels.get(code) or labels.get("en") or row.value.replace("_", " ").title()
        grouped.setdefault(row.category, []).append({"value": row.value, "label": label, "labels": labels})
    return grouped


__all__ = ["DEFAULT_OPTIONS", "ensure_default_options", "list_options"]
