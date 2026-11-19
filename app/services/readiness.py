"""Today's readiness from the prototype: pulse, temperature and isometric strength.

Each check-in is compared with the athlete's OWN references, kept in
`sensor_readings` (real device readings only):

- **Strength** (peak isometric push, kg): her best push is the strength
  reference. Today's push / reference scales the weights of her registered
  loads. At >= 97 % of the reference she keeps her maximum weight; a better
  push becomes the new reference.
- **Pulse** (resting bpm): compared with the median of her recent readings.
  An elevated resting pulse means incomplete recovery: lighter loads, one set
  less and longer rests.
- **Temperature** (ocular IR, degC): compared with her recent median, allowing
  the normal post-ovulation rise (luteal / ovulatory phase). A clear rise
  lowers load and impact; a fever-like value advises against training hard.

The result multiplies the athlete's loads (on top of `k_load` and energy),
changes volume and rest, caps impact, and is handed to the routine model as
part of the assessment.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from syncfit_database import SensorReading, User

# How many recent readings define the usual pulse / temperature.
BASELINE_READINGS = 10
# The strength reference is the best push in this window.
STRENGTH_WINDOW = timedelta(days=60)
KEEP_MAX_RATIO = 0.97
MIN_MULTIPLIER = 0.55
# Plausible ranges: anything outside is a bad contact, not a physiology signal.
HR_RANGE = (35.0, 210.0)
FORCE_RANGE = (0.5, 200.0)
TEMP_RANGE = (30.0, 42.0)
FEVER_C = 37.5
_IMPACT_ORDER = ["LOW", "MEDIUM", "HIGH"]

_TEXT = {
    "force_first": {
        "es": "Fuerza: {today:.1f} kg. Es tu primera medición: queda como tu referencia.",
        "en": "Strength: {today:.1f} kg. First reading: it becomes your reference.",
        "zh": "力量：{today:.1f} kg。这是第一次测量，将作为你的基准。",
    },
    "force_max": {
        "es": "Fuerza: {today:.1f} kg ({pct:.0f} % de tu mejor marca, {ref:.1f} kg). Mantienes tu peso máximo.",
        "en": "Strength: {today:.1f} kg ({pct:.0f} % of your best, {ref:.1f} kg). You keep your maximum weight.",
        "zh": "力量：{today:.1f} kg（最佳 {ref:.1f} kg 的 {pct:.0f}%）。保持你的最大重量。",
    },
    "force_record": {
        "es": "Fuerza: {today:.1f} kg, ¡nuevo récord! (antes {ref:.1f} kg). Mantienes tu peso máximo.",
        "en": "Strength: {today:.1f} kg, a new best! (was {ref:.1f} kg). You keep your maximum weight.",
        "zh": "力量：{today:.1f} kg，新纪录！（之前 {ref:.1f} kg）。保持你的最大重量。",
    },
    "force_low": {
        "es": "Fuerza: {today:.1f} kg ({pct:.0f} % de tu mejor marca, {ref:.1f} kg). Pesos al {factor:.0f} %.",
        "en": "Strength: {today:.1f} kg ({pct:.0f} % of your best, {ref:.1f} kg). Weights at {factor:.0f} %.",
        "zh": "力量：{today:.1f} kg（最佳 {ref:.1f} kg 的 {pct:.0f}%）。重量调整为 {factor:.0f}%。",
    },
    "hr_ok": {
        "es": "Pulso: {today:.0f} bpm, dentro de lo esperado en reposo ({low}–{high}, típico ≈{base:.0f}).",
        "en": "Pulse: {today:.0f} bpm, within the expected resting range ({low}–{high}, typical ≈{base:.0f}).",
        "zh": "脉搏：{today:.0f} bpm，处于静息正常范围（{low}–{high}，典型约 {base:.0f}）。",
    },
    "hr_high": {
        "es": "Pulso: {today:.0f} bpm, alto para estar en reposo (esperado {low}–{high}): recuperación incompleta. Menos carga{extra}.",
        "en": "Pulse: {today:.0f} bpm, high for rest (expected {low}–{high}): incomplete recovery. Lighter loads{extra}.",
        "zh": "脉搏：{today:.0f} bpm，静息时偏高（正常 {low}–{high}）：恢复不足。降低负荷{extra}。",
    },
    "temp_ok": {
        "es": "Temperatura: {today:.1f} °C, normal para ti ({base:.1f} °C).",
        "en": "Temperature: {today:.1f} °C, normal for you ({base:.1f} °C).",
        "zh": "体温：{today:.1f} °C，对你来说正常（{base:.1f} °C）。",
    },
    "temp_phase": {
        "es": "Temperatura: {today:.1f} °C ({delta:+.1f} °C), esperable en tu fase {phase}.",
        "en": "Temperature: {today:.1f} °C ({delta:+.1f} °C), expected in your {phase} phase.",
        "zh": "体温：{today:.1f} °C（{delta:+.1f} °C），符合你的{phase}期。",
    },
    "temp_high": {
        "es": "Temperatura: {today:.1f} °C ({delta:+.1f} °C sobre tu habitual). Menos carga e impacto{extra}.",
        "en": "Temperature: {today:.1f} °C ({delta:+.1f} °C above your usual). Lighter loads and impact{extra}.",
        "zh": "体温：{today:.1f} °C（比平时高 {delta:+.1f} °C）。降低负荷和冲击{extra}。",
    },
    "fever": {
        "es": "Temperatura de {today:.1f} °C: posible fiebre. Hoy mejor descansar o hacer algo muy suave.",
        "en": "Temperature {today:.1f} °C: possible fever. Better rest today or keep it very light.",
        "zh": "体温 {today:.1f} °C：可能发烧。今天最好休息或只做轻度活动。",
    },
    "less_sets": {"es": ", una serie menos y más descanso", "en": ", one set less and longer rests", "zh": "，少一组并延长休息"},
    "more_rest": {"es": " y más descanso", "en": " and longer rests", "zh": "并延长休息"},
    "summary_keep": {
        "es": "Carga de hoy: tus pesos máximos (100 %).",
        "en": "Today's load: your maximum weights (100 %).",
        "zh": "今日负荷：你的最大重量（100%）。",
    },
    "summary": {
        "es": "Carga de hoy: {pct:.0f} % de tus pesos registrados.",
        "en": "Today's load: {pct:.0f} % of your registered weights.",
        "zh": "今日负荷：你登记重量的 {pct:.0f}%。",
    },
}

_PHASE_NAMES = {
    "es": {"LUTEAL": "lútea", "OVULATORY": "ovulatoria"},
    "en": {"LUTEAL": "luteal", "OVULATORY": "ovulatory"},
    "zh": {"LUTEAL": "黄体", "OVULATORY": "排卵"},
}


def _t(key: str, language: str, **values: Any) -> str:
    table = _TEXT[key]
    return table.get(language.lower(), table["en"]).format(**values)


def _in(value: float | None, bounds: tuple[float, float]) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if bounds[0] <= number <= bounds[1] else None


@dataclass
class Readings:
    heart_rate_bpm: float | None = None
    peak_force_kg: float | None = None
    temperature_c: float | None = None
    source: str = "device"  # device | simulated

    @classmethod
    def clean(cls, heart_rate_bpm: Any = None, peak_force_kg: Any = None, temperature_c: Any = None, source: str = "device") -> "Readings":
        return cls(
            heart_rate_bpm=_in(heart_rate_bpm, HR_RANGE),
            peak_force_kg=_in(peak_force_kg, FORCE_RANGE),
            temperature_c=_in(temperature_c, TEMP_RANGE),
            source="simulated" if source == "simulated" else "device",
        )

    def any(self) -> bool:
        return any(v is not None for v in (self.heart_rate_bpm, self.peak_force_kg, self.temperature_c))


@dataclass
class Readiness:
    force_factor: float = 1.0
    hr_factor: float = 1.0
    temp_factor: float = 1.0
    keep_max: bool = False
    sets_delta: int = 0
    rest_extra_s: int = 0
    impact_cap: str | None = None
    fever: bool = False
    reasons: list[str] = field(default_factory=list)
    strength_reference_kg: float | None = None
    strength_ratio: float | None = None
    new_strength_record: bool = False
    hr_baseline: float | None = None
    hr_range: tuple[int, int] | None = None
    temp_baseline: float | None = None
    readings: Readings = field(default_factory=Readings)

    @property
    def factor(self) -> float:
        return round(self.force_factor * self.hr_factor * self.temp_factor, 3)

    def load_multiplier(self, k_load: float | None, energy_factor: float) -> float:
        """Final multiplier of the registered loads for today."""
        if self.keep_max and self.hr_factor == 1.0 and self.temp_factor == 1.0:
            # Her push reached her best: the strength test is direct evidence,
            # so keep the maximum weight (only subjective energy can lower it).
            return round(max(min(energy_factor, 1.0), 0.9), 3)
        base = float(k_load) if k_load is not None else 1.0
        return round(min(max(base * energy_factor * self.factor, MIN_MULTIPLIER), 1.0), 3)

    def as_dict(self, k_load: float | None, energy_factor: float, language: str) -> dict[str, Any]:
        multiplier = self.load_multiplier(k_load, energy_factor)
        summary = _t("summary_keep", language) if multiplier >= 1.0 else _t("summary", language, pct=multiplier * 100)
        return {
            "source": self.readings.source,
            "heart_rate_bpm": self.readings.heart_rate_bpm,
            "peak_force_kg": self.readings.peak_force_kg,
            "temperature_c": self.readings.temperature_c,
            "hr_baseline_bpm": self.hr_baseline,
            "hr_range_bpm": list(self.hr_range) if self.hr_range else None,
            "temp_baseline_c": self.temp_baseline,
            "strength_reference_kg": self.strength_reference_kg,
            "strength_ratio": self.strength_ratio,
            "new_strength_record": self.new_strength_record,
            "force_factor": round(self.force_factor, 3),
            "hr_factor": round(self.hr_factor, 3),
            "temp_factor": round(self.temp_factor, 3),
            "load_multiplier": multiplier,
            "keep_max": self.keep_max and multiplier >= 1.0,
            "sets_delta": self.sets_delta,
            "rest_extra_s": self.rest_extra_s,
            "impact_cap": self.impact_cap,
            "fever": self.fever,
            "reasons": self.reasons,
            "summary": summary,
        }


def _history(session: Session, user: User) -> list[SensorReading]:
    return (
        session.query(SensorReading)
        .filter(SensorReading.user_id == user.id, SensorReading.source == "device")
        .order_by(SensorReading.created_at.desc())
        .limit(200)
        .all()
    )


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


HR_NORMAL_RANGE = (60, 100)
# Average resting pulse of adult women by age (AHA reference tables).
_HR_BY_AGE = [(25, 76), (35, 74), (45, 76), (55, 75), (65, 75), (200, 74)]


def expected_resting_hr(age: int | None = None, modality: str | None = None) -> float:
    value = 75.0
    if age:
        value = float(next(avg for limit, avg in _HR_BY_AGE if age <= limit))
    if (modality or "").upper() == "GESTATIONAL":
        value += 12.0
    return value


def evaluate(
    session: Session,
    user: User,
    readings: Readings,
    phase: str | None,
    language: str = "EN",
    age: int | None = None,
    modality: str | None = None,
) -> Readiness:
    """Compare today's readings with the athlete's references (no writes)."""
    history = _history(session, user)
    now = datetime.now(timezone.utc)
    result = Readiness(readings=readings)

    # --- Strength: best push of the last 60 days ---------------------------
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    pushes = [r.peak_force_kg for r in history if r.peak_force_kg and _aware(r.created_at) >= now - STRENGTH_WINDOW]
    reference = max(pushes) if pushes else None
    result.strength_reference_kg = reference
    today = readings.peak_force_kg
    if today is not None:
        if reference is None:
            result.keep_max = True
            result.reasons.append(_t("force_first", language, today=today))
        else:
            ratio = today / reference
            result.strength_ratio = round(ratio, 3)
            if ratio > 1.0:
                result.keep_max = True
                result.new_strength_record = True
                result.reasons.append(_t("force_record", language, today=today, ref=reference))
            elif ratio >= KEEP_MAX_RATIO:
                result.keep_max = True
                result.reasons.append(_t("force_max", language, today=today, ref=reference, pct=ratio * 100))
            else:
                result.force_factor = round(max(ratio, 0.70), 3)
                result.reasons.append(
                    _t("force_low", language, today=today, ref=reference, pct=ratio * 100, factor=result.force_factor * 100)
                )

    # --- Pulse: EXPECTED resting pulse (not her history) -------------------
    # A device history can hold bad readings (finger moving), so the reference
    # is the normal adult resting range, 60-100 bpm, centred on the average for
    # her age; pregnancy raises the resting pulse ~10-15 bpm.
    expected = expected_resting_hr(age, modality)
    low, high = HR_NORMAL_RANGE
    if (modality or "").upper() == "GESTATIONAL":
        high += 10
    result.hr_baseline = expected
    result.hr_range = (low, high)
    hr = readings.heart_rate_bpm
    if hr is not None:
        over = hr - high
        if over > 10:
            result.hr_factor, result.sets_delta, result.rest_extra_s = 0.80, max(result.sets_delta, 1), max(result.rest_extra_s, 45)
            extra = _t("less_sets", language)
        elif over > 0:
            result.hr_factor, result.sets_delta, result.rest_extra_s = 0.90, max(result.sets_delta, 1), max(result.rest_extra_s, 30)
            extra = _t("less_sets", language)
        elif hr > high - 10:
            result.hr_factor, result.rest_extra_s = 0.95, max(result.rest_extra_s, 15)
            extra = _t("more_rest", language)
        else:
            extra = None
        result.reasons.append(
            _t("hr_ok", language, today=hr, low=low, high=high, base=expected)
            if extra is None
            else _t("hr_high", language, today=hr, low=low, high=high, base=expected, extra=extra)
        )

    # --- Temperature: usual ocular temperature, phase-aware ----------------
    temps = [r.temperature_c for r in history if r.temperature_c][:BASELINE_READINGS]
    result.temp_baseline = _median(temps)
    temp = readings.temperature_c
    if temp is not None:
        base = result.temp_baseline if result.temp_baseline is not None else temp
        result.temp_baseline = round(base, 2)
        delta = temp - base
        allowance = 0.4 if (phase or "").upper() in {"LUTEAL", "OVULATORY"} else 0.2
        excess = delta - allowance
        if temp >= FEVER_C or excess > 0.6:
            result.fever = temp >= FEVER_C
            result.temp_factor, result.sets_delta, result.rest_extra_s = 0.75, max(result.sets_delta, 1), max(result.rest_extra_s, 45)
            result.impact_cap = "LOW"
            result.reasons.append(
                _t("fever", language, today=temp)
                if result.fever
                else _t("temp_high", language, today=temp, delta=delta, extra=_t("less_sets", language))
            )
        elif excess > 0.3:
            result.temp_factor, result.rest_extra_s = 0.85, max(result.rest_extra_s, 30)
            result.impact_cap = result.impact_cap or "MEDIUM"
            result.reasons.append(_t("temp_high", language, today=temp, delta=delta, extra=_t("more_rest", language)))
        elif excess > 0.0:
            result.temp_factor = 0.93
            result.reasons.append(_t("temp_high", language, today=temp, delta=delta, extra=""))
        elif delta > 0.15 and allowance > 0.2:
            phase_name = _PHASE_NAMES.get(language.lower(), _PHASE_NAMES["en"]).get((phase or "").upper(), phase or "")
            result.reasons.append(_t("temp_phase", language, today=temp, delta=delta, phase=phase_name))
        else:
            result.reasons.append(_t("temp_ok", language, today=temp, base=base))

    return result


def record(session: Session, user: User, readings: Readings) -> None:
    """Store a real device reading (simulated check-ins never set references)."""
    if readings.source != "device" or not readings.any():
        return
    session.add(
        SensorReading(
            user_id=user.id,
            source="device",
            heart_rate_bpm=readings.heart_rate_bpm,
            peak_force_kg=readings.peak_force_kg,
            temperature_c=readings.temperature_c,
        )
    )


def stricter_impact(*caps: str | None) -> str | None:
    present = [c for c in caps if c in _IMPACT_ORDER]
    return min(present, key=_IMPACT_ORDER.index) if present else None


def apply_to_entries(entries: list[dict[str, Any]], readiness: Readiness) -> list[dict[str, Any]]:
    """Fewer working sets and longer rests when pulse or temperature say so."""
    if not readiness.sets_delta and not readiness.rest_extra_s:
        return entries
    adjusted = []
    for entry in entries:
        item = dict(entry)
        if item.get("role") in ("WARMUP", "ACTIVATION"):
            adjusted.append(item)
            continue
        sets = [dict(s) for s in item.get("sets") or []]
        if readiness.sets_delta:
            effective = [i for i, s in enumerate(sets) if s.get("type") == "EFFECTIVE"]
            for index in reversed(effective[-readiness.sets_delta:] if len(effective) > 2 else []):
                sets.pop(index)
            if "series_adapted" in item and item["series_adapted"] and item["series_adapted"] > 2:
                item["series_adapted"] = int(item["series_adapted"]) - readiness.sets_delta
        if readiness.rest_extra_s:
            for s in sets:
                if s.get("type") == "EFFECTIVE":
                    s["rest_seconds"] = int(s.get("rest_seconds") or 0) + readiness.rest_extra_s
            if item.get("rest_seconds") is not None:
                item["rest_seconds"] = int(item["rest_seconds"]) + readiness.rest_extra_s
        if sets:
            item["sets"] = sets
            item["estimated_seconds"] = sum(int(s.get("estimated_seconds") or 0) + (readiness.rest_extra_s if s.get("type") == "EFFECTIVE" else 0) for s in sets)
        adjusted.append(item)
    return adjusted


__all__ = ["Readiness", "Readings", "apply_to_entries", "evaluate", "record", "stricter_impact"]
