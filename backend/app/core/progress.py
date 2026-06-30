"""
Centralised progress event emitter.

Services call emit_progress() to broadcast structured events to all WebSocket
clients subscribed to that project.  Every event has a consistent shape so the
frontend can parse it with a single handler.

Event types
-----------
job_progress        — incremental update during a running job
job_completed       — job finished successfully
job_failed          — job finished with an error
job_cancelled       — job was cancelled
scene_image_ready   — a single scene image finished generating
scene_audio_ready   — a single scene audio clip finished generating
log_entry           — a structured log line to stream into the UI log viewer
queue_updated       — the job queue changed (enqueue / dequeue)
project_updated     — project status or progress_state changed
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_progress(
    project_id: str,
    event: str,
    data: Dict[str, Any],
    job_id: Optional[str] = None,
) -> None:
    """Broadcast a progress event to all WebSocket clients for this project."""
    from app.core.events import connection_manager  # lazy import avoids circular deps

    try:
        await connection_manager.broadcast_to_project(
            project_id=project_id,
            event=event,
            data=data,
            job_id=job_id,
        )
    except Exception:
        pass  # never let a WS broadcast crash a service


async def emit_log(
    project_id: str,
    level: str,
    message: str,
    source: Optional[str] = None,
    job_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Push a log line to the project's WebSocket stream."""
    await emit_progress(
        project_id=project_id,
        event="log_entry",
        data={
            "level": level.upper(),
            "message": message,
            "source": source or "",
            "context": context or {},
            "timestamp": _now(),
        },
        job_id=job_id,
    )


async def emit_job_start(project_id: str, job_id: str, job_type: str, total: int = 0) -> None:
    await emit_progress(
        project_id=project_id,
        event="job_started",
        data={"job_type": job_type, "total": total, "progress": 0.0},
        job_id=job_id,
    )


async def emit_job_complete(
    project_id: str,
    job_id: str,
    job_type: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    await emit_progress(
        project_id=project_id,
        event="job_completed",
        data={"job_type": job_type, "result": result or {}},
        job_id=job_id,
    )


async def emit_job_fail(
    project_id: str,
    job_id: str,
    job_type: str,
    error: str,
) -> None:
    await emit_progress(
        project_id=project_id,
        event="job_failed",
        data={"job_type": job_type, "error": error},
        job_id=job_id,
    )


async def emit_scene_image_ready(
    project_id: str,
    job_id: str,
    scene_id: int,
    filename: str,
) -> None:
    await emit_progress(
        project_id=project_id,
        event="scene_image_ready",
        data={"scene_id": scene_id, "filename": filename},
        job_id=job_id,
    )


async def emit_scene_audio_ready(
    project_id: str,
    job_id: str,
    scene_id: int,
    filename: str,
    duration: float = 0.0,
) -> None:
    await emit_progress(
        project_id=project_id,
        event="scene_audio_ready",
        data={"scene_id": scene_id, "filename": filename, "duration": duration},
        job_id=job_id,
    )


async def emit_queue_updated(
    project_id: Optional[str],
    pending: int,
    running: int,
    completed: int,
    failed: int,
) -> None:
    from app.core.events import connection_manager

    data = {
        "pending": pending,
        "running": running,
        "completed": completed,
        "failed": failed,
        "timestamp": _now(),
    }
    try:
        if project_id:
            await connection_manager.broadcast_to_project(project_id, "queue_updated", data)
        else:
            await connection_manager.broadcast_all("queue_updated", data)
    except Exception:
        pass
