"""WebSocket routes for continuous telemetry ingestion."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.engine import evaluate_frame

router = APIRouter()


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    """Receive telemetry frames and reply with the deterministic decision."""
    await websocket.accept()
    try:
        while True:
            message: Any = await websocket.receive_json()
            frame = message.get("payload", message) if isinstance(message, dict) else message
            try:
                decision = evaluate_frame(frame)
                await websocket.send_json({"type": "prescription", "payload": decision})
            except Exception as exc:  # keep the connection alive on bad frames
                await websocket.send_json({"type": "error", "payload": {"detail": str(exc)}})
    except WebSocketDisconnect:
        return


__all__ = ["router"]
