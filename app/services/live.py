"""Último frame de telemetría recibido del prototipo.

Hay un solo dispositivo físico, así que se guarda el último frame válido en
memoria y `/capture` lo usa si es reciente; si no, cae al simulador. Pensado
para una sola réplica del backend (el prototipo); con varias réplicas haría
falta un almacén compartido (Redis/DB).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

# Un frame más viejo que esto ya no se considera del dispositivo.
MAX_AGE_SECONDS = 300.0

_lock = threading.Lock()
_latest: "LiveReading | None" = None


@dataclass(frozen=True)
class LiveReading:
    frame: dict[str, Any]
    decision: dict[str, Any] | None
    received_at: float  # time.monotonic()

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.received_at)


def record(frame: dict[str, Any], decision: dict[str, Any] | None = None) -> None:
    """Store a frame that already passed validation."""
    global _latest
    with _lock:
        _latest = LiveReading(frame=dict(frame), decision=dict(decision) if decision else None, received_at=time.monotonic())


def latest(max_age_seconds: float = MAX_AGE_SECONDS) -> LiveReading | None:
    """Most recent frame, or None when there is none or it is too old."""
    with _lock:
        reading = _latest
    if reading is None:
        return None
    if reading.age_seconds > max_age_seconds:
        return None
    return reading


# Fast force channel: the prototype sends {"type":"force",...} every ~100 ms so
# the force step does not wait for the 2.56 s telemetry frame.
FORCE_MAX_AGE_SECONDS = 5.0
_latest_force: "ForceReading | None" = None


@dataclass(frozen=True)
class ForceReading:
    force_kg: float
    loss_pct: float | None
    received_at: float

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.received_at)


def record_force(message: dict[str, Any]) -> ForceReading:
    """Store a fast force sample; raises ValueError on a malformed message."""
    global _latest_force
    force = float(message["force_kg"])
    if not -50.0 <= force <= 200.0:
        raise ValueError("force_kg out of range")
    loss_raw = message.get("loss_pct")
    loss = float(loss_raw) if loss_raw is not None else None
    if loss is not None and not -100.0 <= loss <= 100.0:
        raise ValueError("loss_pct out of range")
    reading = ForceReading(force_kg=force, loss_pct=loss, received_at=time.monotonic())
    with _lock:
        _latest_force = reading
    return reading


def latest_force(max_age_seconds: float = FORCE_MAX_AGE_SECONDS) -> ForceReading | None:
    with _lock:
        reading = _latest_force
    if reading is None or reading.age_seconds > max_age_seconds:
        return None
    return reading


def clear() -> None:
    """Forget the last frame and force sample (tests, disconnect)."""
    global _latest, _latest_force
    with _lock:
        _latest = None
        _latest_force = None


__all__ = [
    "ForceReading",
    "LiveReading",
    "MAX_AGE_SECONDS",
    "clear",
    "latest",
    "latest_force",
    "record",
    "record_force",
]
