"""Streak days follow the app's time zone, not UTC."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services import stats


class _Query:
    def __init__(self, records):
        self._records = records

    def filter_by(self, **_):
        return self

    def all(self):
        return self._records


class _Session:
    def __init__(self, records):
        self._records = records

    def query(self, _model):
        return _Query(self._records)


def _record(moment: datetime):
    return SimpleNamespace(started_at=moment)


def test_evening_session_in_bogota_counts_on_its_local_day():
    # 21:00 in Bogotá on Nov 18 is 02:00 UTC on Nov 19.
    evening = datetime(2026, 11, 19, 2, 0, tzinfo=timezone.utc)
    result = stats.compute_stats(_Session([_record(evening)]), SimpleNamespace(id="u1"), None, today=date(2026, 11, 18))
    assert result["training_dates"] == ["2026-11-18"]
    assert result["today_trained"] is True


def test_naive_timestamps_are_read_as_utc():
    naive = datetime(2026, 11, 19, 2, 0)
    assert stats._local_date(naive) == date(2026, 11, 18)


def test_time_zone_is_configurable(monkeypatch):
    # Settings is frozen; APP_TIMEZONE feeds _zone(), so swap that.
    monkeypatch.setattr(stats, "_zone", lambda: stats.ZoneInfo("UTC"))
    assert stats._local_date(datetime(2026, 11, 19, 2, 0, tzinfo=timezone.utc)) == date(2026, 11, 19)
