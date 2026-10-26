"""Range statistics over the biomarkers a user recorded during sessions."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session
from syncfit_database import SessionRecord, TelemetrySample, User

from ..analytics.segment_tree import BiomarkerSegmentTree, DayStats

METRICS = ("rmssd_hrv_ms", "delta_temperature_c", "isometric_force_loss_pct")
MAX_RANGE_DAYS = 366
WINDOW_DAYS = 7


def _stats_payload(stats: DayStats) -> dict:
    return {
        "min": stats.minimum if stats.count else None,
        "max": stats.maximum if stats.count else None,
        "mean": stats.mean,
        "readings": stats.count,
    }


def biomarker_summary(session: Session, user: User, metric: str, start: date, end: date) -> dict:
    """Min / max / mean of `metric` over [start, end] plus one row per 7-day window."""
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}")
    if end < start:
        raise ValueError("end must not be before start")
    span = (end - start).days + 1
    if span > MAX_RANGE_DAYS:
        raise ValueError(f"range is limited to {MAX_RANGE_DAYS} days")

    lower = datetime.combine(start, time.min, tzinfo=timezone.utc)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    samples = (
        session.query(TelemetrySample)
        .join(SessionRecord, TelemetrySample.session_id == SessionRecord.id)
        .filter(
            SessionRecord.user_id == user.id,
            TelemetrySample.timestamp >= lower,
            TelemetrySample.timestamp < upper,
        )
        .all()
    )
    readings: dict[date, list[float]] = defaultdict(list)
    for sample in samples:
        readings[sample.timestamp.date()].append(getattr(sample, metric))

    days = [DayStats.of(readings.get(start + timedelta(days=i), [])) for i in range(span)]
    tree = BiomarkerSegmentTree(start, days)

    windows = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=WINDOW_DAYS - 1), end)
        windows.append(
            {"from": cursor.isoformat(), "to": window_end.isoformat(), **_stats_payload(tree.query(cursor, window_end))}
        )
        cursor = window_end + timedelta(days=1)

    return {
        "metric": metric,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "overall": _stats_payload(tree.query(start, end)),
        "windows": windows,
    }


__all__ = ["biomarker_summary", "METRICS"]
