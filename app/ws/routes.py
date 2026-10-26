"""WebSocket routes for continuous telemetry ingestion."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..analytics.ring_buffer import TelemetryRingBuffer
from ..services.engine import evaluate_frame

router = APIRouter()


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    """Receive telemetry frames and reply with the deterministic decision."""
    await websocket.accept()
    # One buffer per connection: the stream of a device never mixes with another.
    buffer = TelemetryRingBuffer()
    try:
        while True:
            message: Any = await websocket.receive_json()
            frame = message.get("payload", message) if isinstance(message, dict) else message
            try:
                decision = evaluate_frame(frame)
                buffer.extend(frame["ppg_window"]["samples"])
                decision["buffer"] = {
                    "samples": len(buffer),
                    "seconds": buffer.seconds_buffered(),
                    "dropped": buffer.dropped,
                }
                await websocket.send_json({"type": "prescription", "payload": decision})
            except Exception as exc:  # keep the connection alive on bad frames
                await websocket.send_json({"type": "error", "payload": {"detail": str(exc)}})
    except WebSocketDisconnect:
        return


__all__ = ["router"]
