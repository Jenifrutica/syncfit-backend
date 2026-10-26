"""Dispatch of physiological alerts raised by telemetry frames."""

from __future__ import annotations

from typing import Any

from ..analytics.alert_heap import AlertHeap, alerts_from_biomarkers

# A burst can raise several alerts at once; the rest wait their turn in the heap.
MAX_ALERTS_PER_FRAME = 3


def dispatch_alerts(heap: AlertHeap, frame: dict[str, Any]) -> dict[str, Any]:
    """Queue the alerts of one frame and release the most severe ones."""
    biomarkers = frame["biomarkers"]
    for alert in alerts_from_biomarkers(
        biomarkers["rmssd_hrv_ms"],
        biomarkers["delta_temperature_c"],
        biomarkers["isometric_force_loss_pct"],
    ):
        heap.push(alert)
    released = heap.drain(MAX_ALERTS_PER_FRAME)
    return {"alerts": [alert.as_dict() for alert in released], "alerts_pending": len(heap)}


__all__ = ["dispatch_alerts", "MAX_ALERTS_PER_FRAME"]
