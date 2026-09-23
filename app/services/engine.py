"""Deterministic core orchestration.

The backend reuses `syncfit-core` directly: it does not recompute biomarkers by
hand. This keeps one implementation of the numerical engine across the project.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from syncfit_contracts import TelemetryFrame
from syncfit_core import SyncFitEngine, train_default_model
from syncfit_core.enums import Modality


@lru_cache(maxsize=1)
def get_engine() -> SyncFitEngine:
    """Build (once) the shared deterministic engine with a trained model."""
    return SyncFitEngine(train_default_model(n_samples=1000, seed=42), window_size=1024)


def evaluate_frame(frame: dict[str, Any]) -> dict[str, Any]:
    """Validate a telemetry frame and return the deterministic decision."""
    validated = TelemetryFrame.model_validate(frame)
    engine = get_engine()
    engine.ingest(validated.ppg_window.samples)
    result = engine.evaluate(
        modality=Modality(validated.modality),
        day_or_week=validated.day_or_week,
        delta_temperature_c=validated.biomarkers.delta_temperature_c,
        isometric_force_loss_pct=validated.biomarkers.isometric_force_loss_pct,
        rmssd_hrv_ms=validated.biomarkers.rmssd_hrv_ms,
    )
    return result.as_dict()


__all__ = ["get_engine", "evaluate_frame"]
