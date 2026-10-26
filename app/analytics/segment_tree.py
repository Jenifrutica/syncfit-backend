"""Segment tree over daily biomarker aggregates (range min / max / mean)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DayStats:
    """Aggregate of every reading taken on one day."""

    minimum: float
    maximum: float
    total: float
    count: int

    @classmethod
    def of(cls, readings: list[float]) -> "DayStats":
        if not readings:
            return EMPTY_DAY
        return cls(min(readings), max(readings), sum(readings), len(readings))

    def merge(self, other: "DayStats") -> "DayStats":
        if self.count == 0:
            return other
        if other.count == 0:
            return self
        return DayStats(
            min(self.minimum, other.minimum),
            max(self.maximum, other.maximum),
            self.total + other.total,
            self.count + other.count,
        )

    @property
    def mean(self) -> float | None:
        return self.total / self.count if self.count else None


EMPTY_DAY = DayStats(0.0, 0.0, 0.0, 0)


class BiomarkerSegmentTree:
    """Answers min / max / mean of a biomarker between two dates in O(log n).

    Leaves are consecutive calendar days starting at `first_day`; every inner
    node holds the merged `DayStats` of its two children. Days without readings
    are empty leaves that do not affect the result.
    """

    def __init__(self, first_day: date, days: list[DayStats]) -> None:
        if not days:
            raise ValueError("at least one day is required")
        self.first_day = first_day
        self._size = len(days)
        self._tree: list[DayStats] = [EMPTY_DAY] * (4 * self._size)
        self._build(1, 0, self._size - 1, days)

    @property
    def last_day(self) -> date:
        return self.first_day + timedelta(days=self._size - 1)

    def _build(self, node: int, lo: int, hi: int, days: list[DayStats]) -> None:
        if lo == hi:
            self._tree[node] = days[lo]
            return
        mid = (lo + hi) // 2
        self._build(2 * node, lo, mid, days)
        self._build(2 * node + 1, mid + 1, hi, days)
        self._tree[node] = self._tree[2 * node].merge(self._tree[2 * node + 1])

    def _index(self, day: date) -> int:
        index = (day - self.first_day).days
        if not 0 <= index < self._size:
            raise ValueError(f"{day} is outside {self.first_day}..{self.last_day}")
        return index

    def query(self, start: date, end: date) -> DayStats:
        """Merged stats for the inclusive range [start, end]."""
        if end < start:
            raise ValueError("end must not be before start")
        return self._query(1, 0, self._size - 1, self._index(start), self._index(end))

    def _query(self, node: int, lo: int, hi: int, left: int, right: int) -> DayStats:
        if right < lo or hi < left:
            return EMPTY_DAY
        if left <= lo and hi <= right:
            return self._tree[node]
        mid = (lo + hi) // 2
        return self._query(2 * node, lo, mid, left, right).merge(
            self._query(2 * node + 1, mid + 1, hi, left, right)
        )

    def update(self, day: date, stats: DayStats) -> None:
        """Replace one day's aggregate (a new reading arrived) in O(log n)."""
        self._update(1, 0, self._size - 1, self._index(day), stats)

    def _update(self, node: int, lo: int, hi: int, index: int, stats: DayStats) -> None:
        if lo == hi:
            self._tree[node] = stats
            return
        mid = (lo + hi) // 2
        if index <= mid:
            self._update(2 * node, lo, mid, index, stats)
        else:
            self._update(2 * node + 1, mid + 1, hi, index, stats)
        self._tree[node] = self._tree[2 * node].merge(self._tree[2 * node + 1])


__all__ = ["BiomarkerSegmentTree", "DayStats", "EMPTY_DAY"]
