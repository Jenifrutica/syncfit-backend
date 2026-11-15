"""WebSocket routes for continuous telemetry ingestion."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..analytics.ring_buffer import TelemetryRingBuffer
from ..services.engine import evaluate_frame
from ..services.live import record

router = APIRouter()

# The prototype is a single device: keep its socket so HTTP endpoints can ask
# it to tare or start a set without a second control channel.
_active_socket: WebSocket | None = None


async def send_device_command(action: str) -> bool:
    """Send one command to the connected prototype; False when it is offline."""
    socket = _active_socket
    if socket is None:
        return False
    try:
        await socket.send_json({"type": "command", "action": action})
        return True
    except Exception:
        return False


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    """Receive telemetry frames and reply with the deterministic decision."""
    global _active_socket
    await websocket.accept()
    _active_socket = websocket
    # One buffer per connection: the stream of a device never mixes with another.
    buffer = TelemetryRingBuffer()
    try:
        while True:
            message: Any = await websocket.receive_json()
            frame = message.get("payload", message) if isinstance(message, dict) else message
            try:
                decision = evaluate_frame(frame)
                buffer.extend(frame["ppg_window"]["samples"])
                record(frame, decision)
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
    finally:
        if _active_socket is websocket:
            _active_socket = None


__all__ = ["router", "send_device_command"]
