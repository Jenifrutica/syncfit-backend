"""Cycle/gestation calendar service."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from syncfit_contracts import CalendarDay, CalendarKind, CycleCalendar
from syncfit_database import Profile

from ..analytics.phase_graph import build_cycle_graph, build_gestation_graph

KIND_LABELS: dict[str, dict[str, str]] = {
    "CYCLE": {"en": "Period", "es": "Menstruación", "zh": "月经期"},
    "OVULATION": {"en": "Ovulation", "es": "Ovulación", "zh": "排卵期"},
    "STRENGTH": {"en": "Strength day", "es": "Día de fuerza", "zh": "力量日"},
    "LOW_IMPACT": {"en": "Low impact", "es": "Bajo impacto", "zh": "低冲击"},
    "REST": {"en": "Rest", "es": "Descanso", "zh": "休息"},
}
KIND_NOTES: dict[str, dict[str, str]] = {
    "OVULATION": {
        "en": "Avoid high impact and heavy free squats/plyometrics this phase.",
        "es": "Evita alto impacto y sentadillas libres pesadas/pliometría en esta fase.",
        "zh": "此阶段避免高冲击与重负荷深蹲/跳跃。",
    },
    "LOW_IMPACT": {
        "en": "Prioritise stability, controlled tempo and pelvic-floor safety.",
        "es": "Prioriza estabilidad, tempo controlado y suelo pélvico.",
        "zh": "优先稳定、控制节奏与盆底保护。",
    },
}

# Non-linear weekly template per trimester, Monday to Sunday.
# Approved split: T1 3 strength / 2 low impact / 2 rest,
# T2 2/2/3 and T3 1/2/4.
GESTATION_WEEK: dict[str, tuple[str, ...]] = {
    "TRIMESTER_1": (
        "STRENGTH",
        "LOW_IMPACT",
        "STRENGTH",
        "REST",
        "STRENGTH",
        "LOW_IMPACT",
        "REST",
    ),
    "TRIMESTER_2": (
        "STRENGTH",
        "LOW_IMPACT",
        "REST",
        "STRENGTH",
        "LOW_IMPACT",
        "REST",
        "REST",
    ),
    "TRIMESTER_3": (
        "LOW_IMPACT",
        "REST",
        "STRENGTH",
        "REST",
        "LOW_IMPACT",
        "REST",
        "REST",
    ),
}

GESTATION_NOTES: dict[str, dict[str, str]] = {
    "STRENGTH": {
        "en": "Strength day: controlled loads, breathing, no Valsalva.",
        "es": "Día de fuerza: cargas controladas, respiración y sin Valsalva.",
        "zh": "力量日：控制负荷、保持呼吸，避免憋气。",
    },
    "LOW_IMPACT": {
        "en": "Low impact: stability, pelvic floor and comfortable range.",
        "es": "Bajo impacto: estabilidad, suelo pélvico y rango cómodo.",
        "zh": "低冲击：稳定、盆底与舒适幅度。",
    },
    "REST": {
        "en": "Rest day: walk, breathe and recover.",
        "es": "Descanso: camina, respira y recupera.",
        "zh": "休息日：散步、呼吸与恢复。",
    },
}


def _month_bounds(month: str | None) -> tuple[int, int]:
    if month:
        year, mon = month.split("-")
        return int(year), int(mon)
    today = date.today()
    return today.year, today.month


def build_calendar(
    profile: Profile | None, month: str | None = None, language: str = "EN"
) -> CycleCalendar:
    year, mon = _month_bounds(month)
    days_count = monthrange(year, mon)[1]
    code = language.lower()
    days: list[CalendarDay] = []

    modality = profile.modality if profile is not None else None
    lmp = profile.last_period_date if profile is not None else None
    length = (profile.cycle_length_days if profile is not None and profile.cycle_length_days else 28)
    gestation_week = profile.gestation_week if profile is not None else None
    cycle_graph = build_cycle_graph(length)
    gestation_graph = build_gestation_graph()

    for day in range(1, days_count + 1):
        current = date(year, mon, day)
        iso = current.isoformat()
        if modality == "GESTATIONAL":
            if gestation_week is not None:
                week = gestation_week + (current - date.today()).days // 7
            elif lmp is not None:
                week = max(1, (current - lmp).days // 7 + 1)
            else:
                week = None
            node = gestation_graph.phase_for(week or 1)
            weekly = GESTATION_WEEK[node.phase]
            kind = CalendarKind(weekly[current.weekday()])
            days.append(
                CalendarDay(
                    date=iso,
                    kind=kind,
                    phase=node.phase,
                    label=KIND_LABELS[kind.value],
                    note=GESTATION_NOTES[kind.value],
                )
            )
            continue

        if lmp is not None:
            cycle_day = ((current - lmp).days % length) + 1
            phase = cycle_graph.phase_for(cycle_day).phase
            if phase == "MENSTRUAL":
                kind = CalendarKind.CYCLE
            elif phase == "OVULATORY":
                kind = CalendarKind.OVULATION
            else:
                kind = CalendarKind.STRENGTH
            days.append(
                CalendarDay(
                    date=iso,
                    kind=kind,
                    cycle_day=cycle_day,
                    phase=phase,
                    label=KIND_LABELS[kind.value],
                    note=KIND_NOTES.get(kind.value),
                )
            )
        else:
            days.append(CalendarDay(date=iso, kind=CalendarKind.REST, label=KIND_LABELS["REST"]))

    return CycleCalendar(
        month=f"{year:04d}-{mon:02d}",
        modality=modality,
        days=days,
    )


__all__ = ["build_calendar"]
