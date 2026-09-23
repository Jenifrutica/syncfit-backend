"""REST routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..services.engine import evaluate_frame

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Service health check."""
    return {"status": "ok", "version": settings.version}


@router.post("/telemetry")
def ingest_telemetry(frame: dict[str, Any]) -> dict[str, Any]:
    """Validate a telemetry frame and return the deterministic decision.

    This is the minimal HTTP path used to see the flow end to end; the
    production ingest is the WebSocket endpoint.
    """
    try:
        return {"decision": evaluate_frame(frame)}
    except Exception as exc:  # schema or model failure
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
