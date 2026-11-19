"""Sensors drive the routine: strength reference, pulse and temperature."""

import uuid

from fastapi.testclient import TestClient
from syncfit_database import SensorReading, User

from app.db import get_database
from app.main import app
from app.services import readiness as r
from app.services.loads import adjust_entries
from syncfit_contracts import ExerciseLoad
from tests.test_bulk import _athlete

client = TestClient(app)


def _user() -> User:
    with get_database().session_scope() as s:
        user = User(email=f"rd-{uuid.uuid4().hex[:8]}@x.dev", password_hash="x", display_name="R", role="ATHLETE")
        s.add(user)
        s.flush()
        s.expunge(user)
        return user


def _history(user: User, rows: list[tuple[float | None, float | None, float | None]]) -> None:
    with get_database().session_scope() as s:
        for hr, force, temp in rows:
            s.add(SensorReading(user_id=user.id, heart_rate_bpm=hr, peak_force_kg=force, temperature_c=temp))


def _eval(user, hr=None, force=None, temp=None, phase="FOLLICULAR", source="device"):
    with get_database().session_scope() as s:
        return r.evaluate(s, user, r.Readings.clean(hr, force, temp, source), phase, "ES")


def test_first_push_becomes_the_reference_and_keeps_max():
    res = _eval(_user(), force=18.0)
    assert res.keep_max and res.force_factor == 1.0
    assert res.load_multiplier(0.9, 1.0) == 1.0  # max weight even with a cautious k_load
    assert "referencia" in res.reasons[0]


def test_weaker_push_scales_the_weights_proportionally():
    user = _user()
    _history(user, [(70, 20.0, 35.0), (72, 18.0, 35.1)])
    res = _eval(user, force=16.0)
    assert res.strength_reference_kg == 20.0 and res.strength_ratio == 0.8
    assert res.force_factor == 0.8 and not res.keep_max
    assert res.load_multiplier(1.0, 1.0) == 0.8


def test_push_at_or_above_reference_keeps_max_and_flags_record():
    user = _user()
    _history(user, [(70, 20.0, 35.0)])
    assert _eval(user, force=19.5).keep_max  # 97.5 %
    record = _eval(user, force=22.0)
    assert record.keep_max and record.new_strength_record


def test_very_weak_push_is_floored():
    user = _user()
    _history(user, [(70, 30.0, 35.0)])
    assert _eval(user, force=6.0).force_factor == 0.70


def test_pulse_is_judged_against_the_expected_resting_range_not_history():
    user = _user()
    # A history full of bad readings must not make 99 bpm look "usual".
    _history(user, [(150, None, None), (152, None, None), (148, None, None)])
    ok = _eval(user, hr=79)
    assert ok.hr_factor == 1.0 and ok.sets_delta == 0 and ok.hr_baseline == 75.0 and ok.hr_range == (60, 100)
    mild = _eval(user, hr=95)
    assert mild.hr_factor == 0.95 and mild.rest_extra_s == 15 and mild.sets_delta == 0
    high = _eval(user, hr=106)
    assert high.hr_factor == 0.90 and high.sets_delta == 1 and high.rest_extra_s == 30
    very = _eval(user, hr=118)
    assert very.hr_factor == 0.80 and very.sets_delta == 1


def test_expected_resting_hr_by_age_and_pregnancy():
    assert r.expected_resting_hr() == 75.0
    assert r.expected_resting_hr(30) == 74.0
    assert r.expected_resting_hr(30, "GESTATIONAL") == 86.0
    with get_database().session_scope() as s:
        pregnant = r.evaluate(s, _user(), r.Readings.clean(105, None, None), "TRIMESTER_2", "ES", age=30, modality="GESTATIONAL")
    assert pregnant.hr_range == (60, 110) and pregnant.hr_factor == 0.95


def test_temperature_respects_luteal_rise_and_flags_fever():
    user = _user()
    _history(user, [(None, None, 35.0), (None, None, 35.1), (None, None, 34.9)])
    luteal = _eval(user, temp=35.35, phase="LUTEAL")
    assert luteal.temp_factor == 1.0  # +0.35 is expected after ovulation
    follicular = _eval(user, temp=35.35, phase="FOLLICULAR")
    assert follicular.temp_factor == 0.93
    hot = _eval(user, temp=35.6, phase="FOLLICULAR")
    assert hot.temp_factor == 0.85 and hot.impact_cap == "MEDIUM"
    fever = _eval(user, temp=37.8, phase="LUTEAL")
    assert fever.fever and fever.temp_factor == 0.75 and fever.impact_cap == "LOW" and fever.sets_delta == 1


def test_combined_factors_and_floor():
    user = _user()
    _history(user, [(65, 20.0, 35.0)])
    res = _eval(user, hr=115, force=15.0, temp=35.7)
    assert res.factor == round(0.75 * 0.80 * 0.85, 3) or res.factor < 0.6
    assert res.load_multiplier(0.8, 0.88) == r.MIN_MULTIPLIER


def test_out_of_range_readings_are_ignored():
    readings = r.Readings.clean(heart_rate_bpm=0, peak_force_kg=0.1, temperature_c=25.0)
    assert not readings.any()


def test_simulated_checkins_never_become_references():
    user = _user()
    with get_database().session_scope() as s:
        r.record(s, user, r.Readings.clean(70, 25.0, 35.0, "simulated"))
        r.record(s, user, r.Readings.clean(70, 18.0, 35.0, "device"))
    with get_database().session_scope() as s:
        assert [x.peak_force_kg for x in s.query(SensorReading).filter_by(user_id=user.id)] == [18.0]


def test_loads_put_todays_weight_on_every_set():
    entries = [{"exercise_id": "leg-press", "sets": [
        {"type": "APPROXIMATION", "weight_kg": 50.0}, {"type": "APPROXIMATION", "weight_kg": 75.0},
        {"type": "EFFECTIVE", "weight_kg": 100.0}, {"type": "EFFECTIVE", "weight_kg": 100.0}]}]
    out = adjust_entries(entries, [ExerciseLoad(exercise_id="leg-press", weight_kg=100.0)], 1.0, multiplier=0.8)[0]
    assert out["weight_suggested_kg"] == 80.0
    assert [s["weight_kg"] for s in out["sets"]] == [40.0, 60.0, 80.0, 80.0]


def test_readiness_trims_sets_and_adds_rest():
    res = r.Readiness(sets_delta=1, rest_extra_s=30)
    entry = {"role": "MAIN", "series_adapted": 3, "rest_seconds": 90, "sets": [
        {"type": "APPROXIMATION", "rest_seconds": 60, "estimated_seconds": 90},
        {"type": "EFFECTIVE", "rest_seconds": 90, "estimated_seconds": 120},
        {"type": "EFFECTIVE", "rest_seconds": 90, "estimated_seconds": 120},
        {"type": "EFFECTIVE", "rest_seconds": 90, "estimated_seconds": 120}]}
    out = r.apply_to_entries([entry, {"role": "WARMUP", "sets": [{"type": "WARMUP"}]}], res)
    main = out[0]
    assert main["series_adapted"] == 2 and sum(1 for s in main["sets"] if s["type"] == "EFFECTIVE") == 2
    assert all(s["rest_seconds"] == 120 for s in main["sets"] if s["type"] == "EFFECTIVE")
    assert main["rest_seconds"] == 120 and out[1] == {"role": "WARMUP", "sets": [{"type": "WARMUP"}]}


def _capture(h, **params):
    q = {"language": "ES", "muscle_groups": "QUADRICEPS", "use_live": "false", **params}
    resp = client.post("/api/v1/capture", params=q, headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _working_weights(body):
    return {e["exercise_id"]: e["weight_suggested_kg"] for e in body["routine"] if e["weight_suggested_kg"]}


def test_assisted_exercises_get_more_help_on_weaker_days():
    from app.services.loads import assisted_weight, is_assisted

    assert is_assisted("assisted-pull-up") and is_assisted("assisted-dip") and not is_assisted("leg-press")
    # 60 kg athlete, 20 kg counterweight -> 40 kg net. At 80 %: 32 kg net -> 28 kg help.
    assert assisted_weight(20.0, 0.8, 60.0) == 28.0
    assert assisted_weight(20.0, 1.0, 60.0) == 20.0  # full capacity: her usual help
    assert assisted_weight(20.0, 0.8, None) == 25.0   # no body weight: 20 / 0.8
    out = adjust_entries(
        [{"exercise_id": "assisted-pull-up", "sets": [{"type": "APPROXIMATION", "weight_kg": 0}, {"type": "EFFECTIVE", "weight_kg": 0}]}],
        [ExerciseLoad(exercise_id="assisted-pull-up", weight_kg=20.0)], 1.0, multiplier=0.8, body_weight_kg=60.0,
    )[0]
    assert out["assisted"] and out["weight_suggested_kg"] == 28.0
    approach, effective = out["sets"]
    assert effective["weight_kg"] == 28.0 and approach["weight_kg"] > 28.0  # lighter set = more help


def test_capture_end_to_end_strength_pulse_and_temperature():
    h = _athlete()
    ids = [e["exercise_id"] for e in _capture(h)["routine"]]
    loads = [{"exercise_id": i, "weight_kg": 50} for i in ids]
    assert client.put("/api/v1/profile", json={"loads": loads}, headers=h).status_code == 200

    first = _capture(h, hr_bpm=70, force_kg=20, temp_c=35.0)
    assert first["readiness"]["keep_max"] is True and first["readiness"]["load_multiplier"] == 1.0
    full = _working_weights(first)  # base x machine factor at 100 %
    assert full

    weak = _capture(h, hr_bpm=70, force_kg=15, temp_c=35.0)
    assert weak["readiness"]["strength_reference_kg"] == 20.0
    assert weak["readiness"]["force_factor"] == 0.75
    for ex, w in _working_weights(weak).items():
        if ex in full:
            assert w < full[ex]
    assert any("Fuerza" in a for a in weak["alerts"])

    strong = _capture(h, hr_bpm=70, force_kg=20.5, temp_c=35.0)
    assert strong["readiness"]["keep_max"]
    for ex, w in _working_weights(strong).items():
        if ex in full:
            assert w == full[ex]

    tired = _capture(h, hr_bpm=95, force_kg=20.5, temp_c=36.0)
    rd = tired["readiness"]
    assert rd["hr_factor"] < 1 and rd["temp_factor"] < 1 and rd["sets_delta"] == 1 and rd["impact_cap"] == "LOW"
    assert rd["load_multiplier"] < 1
    assert tired["assessment"]["sensor_readiness"]["load_multiplier"] == rd["load_multiplier"]

    simulated = _capture(h, hr_bpm=70, force_kg=99, temp_c=35.0, sensor_source="simulated")
    assert simulated["readiness"]["source"] == "simulated"
    after = _capture(h, hr_bpm=70, force_kg=20.5, temp_c=35.0)
    assert after["readiness"]["strength_reference_kg"] == 20.5  # the simulated 99 kg was not stored
