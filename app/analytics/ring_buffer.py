"""Fixed-capacity ring buffer for the incoming PPG stream (100 Hz)."""

from __future__ import annotations

from collections.abc import Iterable

SAMPLE_RATE_HZ = 100
DEFAULT_SECONDS = 10


class TelemetryRingBuffer:
    """Keeps the most recent PPG samples of one device connection.

    Pushing is O(1): when the buffer is full the oldest sample is overwritten
    instead of shifting the rest. `dropped` counts how many samples were lost
    that way, so the caller can tell the consumer is slower than the stream.
    """

    def __init__(self, capacity: int = SAMPLE_RATE_HZ * DEFAULT_SECONDS) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._slots: list[float] = [0.0] * capacity
        self._head = 0  # index of the oldest sample
        self._size = 0
        self.dropped = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return self._size

    @property
    def is_full(self) -> bool:
        return self._size == self._capacity

    def push(self, sample: float) -> None:
        if self.is_full:
            # Overwrite the oldest slot and move the head one step forward.
            self._slots[self._head] = sample
            self._head = (self._head + 1) % self._capacity
            self.dropped += 1
            return
        self._slots[(self._head + self._size) % self._capacity] = sample
        self._size += 1

    def extend(self, samples: Iterable[float]) -> None:
        for sample in samples:
            self.push(sample)

    def snapshot(self) -> list[float]:
        """Samples in arrival order, oldest first."""
        return [self._slots[(self._head + i) % self._capacity] for i in range(self._size)]

    def latest(self, count: int) -> list[float]:
        """The `count` most recent samples, oldest first."""
        if count < 0:
            raise ValueError("count must not be negative")
        count = min(count, self._size)
        start = self._size - count
        return [self._slots[(self._head + start + i) % self._capacity] for i in range(count)]

    def seconds_buffered(self) -> float:
        return self._size / SAMPLE_RATE_HZ

    def clear(self) -> None:
        self._head = 0
        self._size = 0
        self.dropped = 0


__all__ = ["TelemetryRingBuffer", "SAMPLE_RATE_HZ"]
