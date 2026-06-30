"""
WebSocket endpoints.

/ws/{project_id}  — per-project stream (job progress, log entries, scene events)
/ws               — global stream (queue updates, system events)

On connect the server sends an initial state snapshot so the client can
bootstrap its UI without waiting for the first event.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.core.events import connection_manager
from app.core.logging import get_logger
from app.workers.queue_manager import queue_manager

logger = get_logger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _initial_snapshot(project_id: Optional[str] = None) -> dict:
    """Build the connection-handshake payload with current queue state."""
    statuses = queue_manager.get_all_statuses()
    active = [s for s in statuses if s and s.get("status") in ("running", "pending")]
    if project_id:
        active = [s for s in active if s and s.get("project_id") == project_id]

    return {
        "event": "connected",
        "project_id": project_id,
        "timestamp": _now(),
        "data": {
            "active_jobs": active,
            "queue_length": queue_manager.get_queue_length(),
            "active_count": queue_manager.get_active_count(),
        },
    }


# ---------------------------------------------------------------------------
# Per-project WebSocket
# ---------------------------------------------------------------------------
@router.websocket("/ws/{project_id}")
async def websocket_project(websocket: WebSocket, project_id: str):
    await connection_manager.connect(websocket, project_id=project_id)
    logger.info(f"WS connected: project={project_id}")

    try:
        # Send initial snapshot so the frontend can restore state immediately
        snapshot = await _initial_snapshot(project_id)
        await websocket.send_text(json.dumps(snapshot))

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "project_id": project_id, "timestamp": _now()})

                elif msg_type == "get_status":
                    snapshot = await _initial_snapshot(project_id)
                    await websocket.send_text(json.dumps(snapshot))

                elif msg_type == "cancel_job":
                    job_id = msg.get("job_id")
                    if job_id:
                        cancelled = await queue_manager.cancel(job_id)
                        await websocket.send_json({
                            "type": "cancel_ack",
                            "job_id": job_id,
                            "success": cancelled,
                            "timestamp": _now(),
                        })

                elif msg_type == "pause_job":
                    job_id = msg.get("job_id")
                    if job_id:
                        ok = await queue_manager.pause(job_id)
                        await websocket.send_json({"type": "pause_ack", "job_id": job_id, "success": ok})

                elif msg_type == "resume_job":
                    job_id = msg.get("job_id")
                    if job_id:
                        ok = await queue_manager.resume(job_id)
                        await websocket.send_json({"type": "resume_ack", "job_id": job_id, "success": ok})

            except (json.JSONDecodeError, KeyError):
                pass

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: project={project_id}")
    except Exception as exc:
        logger.error(f"WS error project={project_id}: {exc}")
    finally:
        await connection_manager.disconnect(websocket, project_id=project_id)


# ---------------------------------------------------------------------------
# Global WebSocket (receives all project events + system events)
# ---------------------------------------------------------------------------
@router.websocket("/ws")
async def websocket_global(websocket: WebSocket):
    await connection_manager.connect(websocket, project_id=None)
    logger.info("Global WS connected")

    try:
        snapshot = await _initial_snapshot()
        await websocket.send_text(json.dumps(snapshot))

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": _now()})
                elif msg.get("type") == "get_status":
                    snapshot = await _initial_snapshot()
                    await websocket.send_text(json.dumps(snapshot))
            except (json.JSONDecodeError, KeyError):
                pass

    except WebSocketDisconnect:
        logger.info("Global WS disconnected")
    except Exception as exc:
        logger.error(f"Global WS error: {exc}")
    finally:
        await connection_manager.disconnect(websocket, project_id=None)
