"""Selectable values of the app, stored in the `app_options` table."""

from __future__ import annotations

from sqlalchemy.orm import Session
from syncfit_database import AppOption

ISOLATED = "muscle_group_isolated"
GENERAL = "muscle_group_general"
OBJECTIVE = "objective"
GOAL_PHASE = "goal_phase"
EQUIPMENT = "equipment"
CATEGORIES = (ISOLATED, GENERAL, OBJECTIVE, GOAL_PHASE, EQUIPMENT)

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
    # Equipment a gym machine can be; the frontend key is value.lower() with "-".
    (EQUIPMENT, "MACHINE", {"en": "Machine", "es": "Máquina", "zh": "固定器械"}),
    (EQUIPMENT, "SMITH", {"en": "Smith", "es": "Smith", "zh": "史密斯机"}),
    (EQUIPMENT, "BARBELL", {"en": "Barbell", "es": "Barra", "zh": "杠铃"}),
    (EQUIPMENT, "DUMBBELL", {"en": "Dumbbells", "es": "Mancuernas", "zh": "哑铃"}),
    (EQUIPMENT, "BENCH", {"en": "Bench", "es": "Banco", "zh": "训练凳"}),
    (EQUIPMENT, "CABLE", {"en": "Cable", "es": "Polea", "zh": "龙门架"}),
    (EQUIPMENT, "PULLUP_BAR", {"en": "Pull-up bar", "es": "Barra de dominadas", "zh": "引体向上杆"}),
    (EQUIPMENT, "DIP_BAR", {"en": "Dip bars", "es": "Paralelas", "zh": "双杠"}),
    (EQUIPMENT, "GHD", {"en": "GHD", "es": "GHD", "zh": "GHD"}),
    (EQUIPMENT, "BOX", {"en": "Box", "es": "Cajón", "zh": "跳箱"}),
    (EQUIPMENT, "BAND", {"en": "Band", "es": "Banda", "zh": "弹力带"}),
    (EQUIPMENT, "NONE", {"en": "Bodyweight", "es": "Peso corporal", "zh": "自重"}),
]

# Parameters the engines read from each option (seeded once, editable in the DB).
# Objective: sets x reps and rest seconds (Schoenfeld 2017/2021, Currier 2023).
# Goal phase: daily calorie factor over maintenance.
DEFAULT_META: dict[tuple[str, str], dict] = {
    (OBJECTIVE, "STRENGTH"): {"sets": 4, "reps": 5, "rest_compound": 180, "rest_iso": 120},
    (OBJECTIVE, "HYPERTROPHY"): {"sets": 3, "reps": 10, "rest_compound": 120, "rest_iso": 75},
    (OBJECTIVE, "PERFORMANCE"): {"sets": 3, "reps": 8, "rest_compound": 120, "rest_iso": 75},
    (OBJECTIVE, "FAT_LOSS"): {"sets": 3, "reps": 14, "rest_compound": 75, "rest_iso": 45},
    (OBJECTIVE, "HEALTH"): {"sets": 3, "reps": 12, "rest_compound": 75, "rest_iso": 45},
    (OBJECTIVE, "RECOVERY"): {"sets": 2, "reps": 12, "rest_compound": 60, "rest_iso": 45},
    (OBJECTIVE, "GESTATIONAL_HEALTH"): {"sets": 3, "reps": 12, "rest_compound": 75, "rest_iso": 60},
    (GOAL_PHASE, "VOLUME"): {"calorie_factor": 1.12},
    (GOAL_PHASE, "DEFINITION"): {"calorie_factor": 0.82},
    (GOAL_PHASE, "MAINTENANCE"): {"calorie_factor": 1.0},
    (GOAL_PHASE, "STRENGTH_FOCUS"): {"calorie_factor": 1.05},
    (GOAL_PHASE, "RECOVERY"): {"calorie_factor": 1.0},
}

for muscles, zones in (
    (("GLUTES", "QUADRICEPS", "HAMSTRINGS", "CALVES"), ("LOWER_BODY", "FULL_LEG")),
    (("ABS", "OBLIQUES"), ("CORE",)),
    (("BACK", "LATS", "CHEST", "SHOULDERS", "BICEPS", "TRICEPS", "FOREARMS"), ("UPPER_BODY",)),
):
    for muscle in muscles:
        DEFAULT_META[ISOLATED, muscle] = {"zones": [*zones, "FULL_BODY"]}

# Goal-phase calorie factors loaded from the database (see sync_engine_options).
_calorie_factors: dict[str, float] = {}


def ensure_default_options(session: Session) -> int:
    """Insert the options that are missing; rows already in the table are never touched.

    That way an edit made directly in the database survives a restart.
    """
    existing = {(o.category, o.value): o for o in session.query(AppOption).all()}
    added = 0
    for order, (category, value, labels) in enumerate(DEFAULT_OPTIONS):
        meta = DEFAULT_META.get((category, value))
        row = existing.get((category, value))
        if row is not None:
            # Only fill parameters that were never set; edits are kept.
            if meta and not row.meta:
                row.meta = dict(meta)
            continue
        session.add(AppOption(category=category, value=value, labels=labels, sort_order=order, meta=meta))
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
        option = {"value": row.value, "label": label, "labels": labels}
        if row.category == ISOLATED:
            option["zones"] = muscle_zones(row.value, row.meta)
        grouped.setdefault(row.category, []).append(option)
    return grouped


def muscle_zones(value: str, meta: dict | None) -> list[str]:
    zones = (meta or DEFAULT_META.get((ISOLATED, value), {})).get("zones", [])
    return [zone for zone in zones if isinstance(zone, str)] if isinstance(zones, list) else []


def incompatible_training_pair(session: Session, groups: list[str]) -> tuple[str, str] | None:
    options = list_options(session)
    if not options:
        muscles = {
            value: muscle_zones(value, None)
            for category, value, _ in DEFAULT_OPTIONS
            if category == ISOLATED
        }
        zones = default_values(GENERAL)
    else:
        muscles = {option["value"]: option["zones"] for option in options.get(ISOLATED, [])}
        zones = {option["value"] for option in options.get(GENERAL, [])}
    selected_zones = zones.intersection(groups)
    for muscle in groups:
        if muscle in muscles:
            for zone in groups:
                if zone in selected_zones and zone not in muscles[muscle]:
                    return muscle, zone
    return None


def capture_default_groups(session: Session) -> list[str]:
    rows = session.query(AppOption).filter(AppOption.category.in_((GENERAL, ISOLATED))).order_by(
        AppOption.sort_order, AppOption.value
    ).all()
    if not rows:
        return [value for category, value, _ in DEFAULT_OPTIONS if category == GENERAL][:3]
    active = [row for row in rows if row.active]
    return ([row.value for row in active if row.category == GENERAL] or [row.value for row in active])[:3]


def active_values(session: Session, category: str) -> set[str]:
    rows = session.query(AppOption.value, AppOption.active).filter(AppOption.category == category).all()
    return {value for value, active in rows if active} if rows else default_values(category)


def default_values(category: str) -> set[str]:
    """Seeded values, used only before the table has been seeded."""
    return {value for cat, value, _ in DEFAULT_OPTIONS if cat == category}


def sync_engine_options(session: Session) -> None:
    """Hand the option parameters stored in the DB to the engines."""
    from syncfit_ai import options as ai_options

    rows = session.query(AppOption).filter(AppOption.category.in_([OBJECTIVE, GOAL_PHASE])).all()
    ai_options.set_objectives(
        [{"value": r.value, "labels": r.labels or {}, "meta": r.meta or {}} for r in rows if r.category == OBJECTIVE and r.active]
    )
    factors: dict[str, float] = {}
    for row in rows:
        value = (row.meta or {}).get("calorie_factor") if row.category == GOAL_PHASE else None
        if isinstance(value, (int, float)) and 0.5 <= float(value) <= 1.5:
            factors[row.value] = float(value)
    _calorie_factors.clear()
    _calorie_factors.update(factors)


def calorie_factor(goal_phase: str | None) -> float | None:
    return _calorie_factors.get(goal_phase or "MAINTENANCE")


__all__ = [
    "CATEGORIES",
    "DEFAULT_META",
    "DEFAULT_OPTIONS",
    "active_values",
    "calorie_factor",
    "default_values",
    "ensure_default_options",
    "list_options",
    "sync_engine_options",
]
