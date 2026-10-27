from collections import Counter
from datetime import date, timedelta
from types import SimpleNamespace

from app.services.calendar import build_calendar
from app.services.cycles import compute_timeline


def _profile(**overrides):
    base = dict(
        modality="MENSTRUAL_CYCLE",
        last_period_date=None,
        cycle_length_days=28,
        gestation_week=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_timeline_reports_next_phase_and_distance():
    today = date(2026, 9, 10)
    profile = _profile(last_period_date=today - timedelta(days=9))  # cycle day 10
    timeline = compute_timeline(profile, today)
    assert timeline["phase"] == "FOLLICULAR"
    assert timeline["next_phase"] == "OVULATORY"
    assert timeline["days_to_next_phase"] == 4


def test_timeline_last_cycle_phase_wraps_to_menstrual():
    today = date(2026, 9, 10)
    profile = _profile(last_period_date=today - timedelta(days=19))  # cycle day 20
    timeline = compute_timeline(profile, today)
    assert timeline["phase"] == "LUTEAL"
    assert timeline["next_phase"] == "MENSTRUAL"
    assert timeline["days_to_next_phase"] == 9


def test_gestation_timeline_has_no_phase_after_third_trimester():
    profile = _profile(modality="GESTATIONAL", gestation_week=30)
    timeline = compute_timeline(profile, date(2026, 9, 10))
    assert timeline["phase"] == "TRIMESTER_3"
    assert timeline["next_phase"] is None
    assert timeline["weeks_to_next_phase"] is None


def _gestation_week_counts(gestation_week):
    profile = _profile(modality="GESTATIONAL", gestation_week=gestation_week)
    days = build_calendar(profile, date.today().strftime("%Y-%m")).days
    weeks: dict[tuple[int, int], list[str]] = {}
    for day in days:
        current = date.fromisoformat(day.date)
        weeks.setdefault(current.isocalendar()[:2], []).append(day.kind)
    return days, [Counter(week) for week in weeks.values() if len(week) == 7]


def test_calendar_gestation_uses_non_linear_weekly_template():
    days, full_weeks = _gestation_week_counts(35)
    assert {d.phase for d in days} == {"TRIMESTER_3"}
    assert {d.kind for d in days} == {"LOW_IMPACT", "STRENGTH", "REST"}
    for counts in full_weeks:
        assert counts == Counter({"STRENGTH": 1, "LOW_IMPACT": 2, "REST": 4})


def test_calendar_first_and_second_trimester_weekly_splits():
    _, first = _gestation_week_counts(4)
    for counts in first:
        assert counts == Counter({"STRENGTH": 3, "LOW_IMPACT": 2, "REST": 2})
    _, second = _gestation_week_counts(20)
    for counts in second:
        assert counts == Counter({"STRENGTH": 2, "LOW_IMPACT": 2, "REST": 3})


def test_calendar_phases_follow_the_cycle_graph():
    profile = _profile(last_period_date=date(2026, 9, 1))
    days = {d.date: d for d in build_calendar(profile, "2026-09").days}
    assert days["2026-09-01"].phase == "MENSTRUAL" and days["2026-09-01"].kind == "CYCLE"
    assert days["2026-09-14"].phase == "OVULATORY" and days["2026-09-14"].kind == "OVULATION"
    assert days["2026-09-20"].phase == "LUTEAL"
