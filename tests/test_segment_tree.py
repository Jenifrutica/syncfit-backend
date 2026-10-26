import random
from datetime import date, timedelta

import pytest

from app.analytics.segment_tree import EMPTY_DAY, BiomarkerSegmentTree, DayStats

FIRST = date(2026, 9, 1)


def _tree(values_per_day):
    return BiomarkerSegmentTree(FIRST, [DayStats.of(v) for v in values_per_day])


def test_single_day_query():
    tree = _tree([[40.0, 50.0], [30.0]])
    stats = tree.query(FIRST, FIRST)
    assert (stats.minimum, stats.maximum, stats.mean) == (40.0, 50.0, 45.0)


def test_range_merges_days():
    tree = _tree([[40.0], [20.0, 60.0], [50.0]])
    stats = tree.query(FIRST, FIRST + timedelta(days=2))
    assert (stats.minimum, stats.maximum, stats.count) == (20.0, 60.0, 4)
    assert stats.mean == 42.5


def test_days_without_readings_are_ignored():
    tree = _tree([[], [30.0], [], []])
    stats = tree.query(FIRST, FIRST + timedelta(days=3))
    assert (stats.minimum, stats.maximum, stats.count) == (30.0, 30.0, 1)
    assert tree.query(FIRST, FIRST) is EMPTY_DAY
    assert EMPTY_DAY.mean is None


def test_update_changes_later_queries():
    tree = _tree([[10.0], [20.0], [30.0]])
    tree.update(FIRST + timedelta(days=1), DayStats.of([90.0]))
    assert tree.query(FIRST, FIRST + timedelta(days=2)).maximum == 90.0


def test_matches_brute_force_on_random_ranges():
    rng = random.Random(3)
    days = [[rng.uniform(10, 90) for _ in range(rng.randint(0, 4))] for _ in range(37)]
    tree = _tree(days)
    for _ in range(100):
        a, b = sorted(rng.sample(range(37), 2))
        flat = [x for day in days[a : b + 1] for x in day]
        stats = tree.query(FIRST + timedelta(days=a), FIRST + timedelta(days=b))
        if not flat:
            assert stats.count == 0
            continue
        assert stats.minimum == min(flat)
        assert stats.maximum == max(flat)
        assert stats.mean == pytest.approx(sum(flat) / len(flat))


def test_rejects_bad_ranges():
    tree = _tree([[1.0], [2.0]])
    with pytest.raises(ValueError):
        tree.query(FIRST + timedelta(days=1), FIRST)
    with pytest.raises(ValueError):
        tree.query(FIRST, FIRST + timedelta(days=5))
    with pytest.raises(ValueError):
        BiomarkerSegmentTree(FIRST, [])
