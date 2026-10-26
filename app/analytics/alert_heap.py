"""Max-heap that dispatches the most severe physiological alert first."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class PhysiologicalAlert:
    kind: str  # LOW_HRV | HIGH_TEMPERATURE | FORCE_LOSS
    severity: Severity
    value: float
    message: str

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity.name,
            "value": self.value,
            "message": self.message,
        }


class AlertHeap:
    """Array-backed binary max-heap ordered by severity.

    `peek` is O(1); `push` and `pop` are O(log n). Alerts with the same
    severity leave in arrival order, so an old critical alert is not starved
    by a newer one of the same level.
    """

    def __init__(self) -> None:
        self._items: list[tuple[PhysiologicalAlert, int]] = []
        self._arrivals = 0

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def _outranks(self, a: int, b: int) -> bool:
        alert_a, order_a = self._items[a]
        alert_b, order_b = self._items[b]
        if alert_a.severity != alert_b.severity:
            return alert_a.severity > alert_b.severity
        return order_a < order_b

    def _swap(self, a: int, b: int) -> None:
        self._items[a], self._items[b] = self._items[b], self._items[a]

    def push(self, alert: PhysiologicalAlert) -> None:
        self._items.append((alert, self._arrivals))
        self._arrivals += 1
        self._sift_up(len(self._items) - 1)

    def peek(self) -> PhysiologicalAlert:
        if not self._items:
            raise IndexError("no alerts pending")
        return self._items[0][0]

    def pop(self) -> PhysiologicalAlert:
        if not self._items:
            raise IndexError("no alerts pending")
        top = self._items[0][0]
        last = self._items.pop()
        if self._items:
            self._items[0] = last
            self._sift_down(0)
        return top

    def drain(self, limit: int | None = None) -> list[PhysiologicalAlert]:
        """Pop up to `limit` alerts, most severe first."""
        out: list[PhysiologicalAlert] = []
        while self._items and (limit is None or len(out) < limit):
            out.append(self.pop())
        return out

    def _sift_up(self, index: int) -> None:
        while index > 0:
            parent = (index - 1) // 2
            if not self._outranks(index, parent):
                break
            self._swap(index, parent)
            index = parent

    def _sift_down(self, index: int) -> None:
        size = len(self._items)
        while True:
            best = index
            for child in (2 * index + 1, 2 * index + 2):
                if child < size and self._outranks(child, best):
                    best = child
            if best == index:
                return
            self._swap(index, best)
            index = best


# Thresholds are (lower bound of the band, severity), checked from most severe.
HRV_BANDS = ((20.0, Severity.CRITICAL), (30.0, Severity.HIGH), (40.0, Severity.MEDIUM))
TEMPERATURE_BANDS = ((1.5, Severity.CRITICAL), (1.0, Severity.HIGH), (0.7, Severity.MEDIUM))
FORCE_LOSS_BANDS = ((30.0, Severity.CRITICAL), (20.0, Severity.HIGH), (15.0, Severity.MEDIUM))


def _low_hrv(rmssd_ms: float) -> PhysiologicalAlert | None:
    for limit, severity in HRV_BANDS:
        if rmssd_ms < limit:
            return PhysiologicalAlert("LOW_HRV", severity, rmssd_ms, f"RMSSD {rmssd_ms:.1f} ms is below {limit:.0f} ms")
    return None


def _above(kind: str, value: float, bands: tuple, label: str) -> PhysiologicalAlert | None:
    for limit, severity in bands:
        if value >= limit:
            return PhysiologicalAlert(kind, severity, value, f"{label} {value:.1f} reached {limit}")
    return None


def alerts_from_biomarkers(
    rmssd_hrv_ms: float, delta_temperature_c: float, isometric_force_loss_pct: float
) -> list[PhysiologicalAlert]:
    """Turn one frame of biomarkers into the alerts it triggers (possibly none)."""
    found = (
        _low_hrv(rmssd_hrv_ms),
        _above("HIGH_TEMPERATURE", delta_temperature_c, TEMPERATURE_BANDS, "Temperature delta"),
        _above("FORCE_LOSS", isometric_force_loss_pct, FORCE_LOSS_BANDS, "Force loss %"),
    )
    return [alert for alert in found if alert is not None]


__all__ = ["AlertHeap", "PhysiologicalAlert", "Severity", "alerts_from_biomarkers"]
