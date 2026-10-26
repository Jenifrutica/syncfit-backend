import pytest

from app.analytics.ring_buffer import TelemetryRingBuffer


def test_keeps_arrival_order_before_filling():
    buf = TelemetryRingBuffer(capacity=4)
    buf.extend([1, 2, 3])
    assert buf.snapshot() == [1, 2, 3]
    assert len(buf) == 3
    assert not buf.is_full


def test_overwrites_oldest_when_full():
    buf = TelemetryRingBuffer(capacity=3)
    buf.extend([1, 2, 3, 4, 5])
    assert buf.snapshot() == [3, 4, 5]
    assert buf.is_full
    assert buf.dropped == 2


def test_latest_returns_most_recent_in_order():
    buf = TelemetryRingBuffer(capacity=4)
    buf.extend(range(1, 8))  # wraps around
    assert buf.latest(2) == [6, 7]
    assert buf.latest(10) == [4, 5, 6, 7]
    assert buf.latest(0) == []


def test_seconds_buffered_uses_100hz():
    buf = TelemetryRingBuffer(capacity=500)
    buf.extend([0.0] * 250)
    assert buf.seconds_buffered() == 2.5


def test_clear_resets_state():
    buf = TelemetryRingBuffer(capacity=2)
    buf.extend([1, 2, 3])
    buf.clear()
    assert len(buf) == 0 and buf.dropped == 0
    buf.push(9)
    assert buf.snapshot() == [9]


def test_invalid_arguments():
    with pytest.raises(ValueError):
        TelemetryRingBuffer(capacity=0)
    with pytest.raises(ValueError):
        TelemetryRingBuffer(capacity=2).latest(-1)
