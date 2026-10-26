import random

import pytest

from app.analytics.alert_heap import AlertHeap, PhysiologicalAlert, Severity, alerts_from_biomarkers


def _alert(severity, label="x"):
    return PhysiologicalAlert("LOW_HRV", severity, 0.0, label)


def test_pops_by_severity_then_arrival():
    heap = AlertHeap()
    heap.push(_alert(Severity.LOW, "a"))
    heap.push(_alert(Severity.CRITICAL, "b"))
    heap.push(_alert(Severity.HIGH, "c"))
    heap.push(_alert(Severity.CRITICAL, "d"))
    assert [a.message for a in heap.drain()] == ["b", "d", "c", "a"]


def test_peek_does_not_remove():
    heap = AlertHeap()
    heap.push(_alert(Severity.MEDIUM, "m"))
    assert heap.peek().message == "m"
    assert len(heap) == 1


def test_empty_heap_raises():
    heap = AlertHeap()
    assert not heap
    with pytest.raises(IndexError):
        heap.pop()
    with pytest.raises(IndexError):
        heap.peek()


def test_drain_respects_limit():
    heap = AlertHeap()
    for severity in (Severity.LOW, Severity.HIGH, Severity.MEDIUM):
        heap.push(_alert(severity))
    assert [a.severity for a in heap.drain(2)] == [Severity.HIGH, Severity.MEDIUM]
    assert len(heap) == 1


def test_random_pushes_come_out_sorted():
    rng = random.Random(7)
    heap = AlertHeap()
    for _ in range(200):
        heap.push(_alert(Severity(rng.randint(1, 4))))
    severities = [a.severity for a in heap.drain()]
    assert severities == sorted(severities, reverse=True)


def test_biomarkers_below_thresholds_raise_nothing():
    assert alerts_from_biomarkers(55.0, 0.2, 5.0) == []


def test_biomarkers_map_to_severities():
    alerts = {a.kind: a.severity for a in alerts_from_biomarkers(18.0, 1.1, 22.0)}
    assert alerts == {
        "LOW_HRV": Severity.CRITICAL,
        "HIGH_TEMPERATURE": Severity.HIGH,
        "FORCE_LOSS": Severity.HIGH,
    }
