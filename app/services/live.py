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


def clear() -> None:
    """Forget the last frame (tests, disconnect)."""
    global _latest
    with _lock:
        _latest = None


__all__ = ["LiveReading", "MAX_AGE_SECONDS", "clear", "latest", "record"]
