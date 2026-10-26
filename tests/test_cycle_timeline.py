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


def test_calendar_marks_third_trimester_as_low_impact():
    profile = _profile(modality="GESTATIONAL", gestation_week=35)
    days = build_calendar(profile, date.today().strftime("%Y-%m")).days
    assert {d.kind for d in days} == {"LOW_IMPACT"}
    assert {d.phase for d in days} == {"TRIMESTER_3"}


def test_calendar_phases_follow_the_cycle_graph():
    profile = _profile(last_period_date=date(2026, 9, 1))
    days = {d.date: d for d in build_calendar(profile, "2026-09").days}
    assert days["2026-09-01"].phase == "MENSTRUAL" and days["2026-09-01"].kind == "CYCLE"
    assert days["2026-09-14"].phase == "OVULATORY" and days["2026-09-14"].kind == "OVULATION"
    assert days["2026-09-20"].phase == "LUTEAL"
