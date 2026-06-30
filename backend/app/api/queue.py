"""
Queue management API — view queue status, list jobs, pause/resume the worker.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_job_repo, get_project_repo
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.workers.queue_manager import queue_manager

router = APIRouter()


@router.get("/status")
async def get_queue_status():
    """Return real-time queue metrics."""
    statuses = queue_manager.get_all_statuses()

    pending = sum(1 for s in statuses if s and s.get("status") == "pending")
    running = sum(1 for s in statuses if s and s.get("status") == "running")
    completed = sum(1 for s in statuses if s and s.get("status") == "completed")
    failed = sum(1 for s in statuses if s and s.get("status") == "failed")
    cancelled = sum(1 for s in statuses if s and s.get("status") == "cancelled")

    return {
        "queue_length": queue_manager.get_queue_length(),
        "active_count": queue_manager.get_active_count(),
        "pending": pending,
        "running": running,
        "completed": completed,
        "failed": failed,
        "cancelled": cancelled,
        "total": len(statuses),
        "is_running": queue_manager._running,
    }


@router.get("/jobs")
async def list_queue_jobs(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List all jobs tracked by the queue manager (in-memory)."""
    all_jobs = [s for s in queue_manager.get_all_statuses() if s is not None]

    if status:
        all_jobs = [j for j in all_jobs if j.get("status") == status]

    # Most recent first
    all_jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return {"jobs": all_jobs[:limit], "total": len(all_jobs)}


@router.get("/jobs/{job_id}")
async def get_queue_job(job_id: str):
    status = queue_manager.get_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found in queue")
    return status


@router.post("/jobs/{job_id}/cancel")
async def cancel_queue_job(job_id: str):
    cancelled = await queue_manager.cancel(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found or already finished")
    return {"message": f"Job {job_id} cancelled", "job_id": job_id}


@router.post("/pause")
async def pause_queue(job_id: Optional[str] = Query(default=None)):
    """Pause a specific job or the entire queue."""
    if job_id:
        ok = await queue_manager.pause(job_id)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Could not pause job {job_id}")
        return {"message": f"Job {job_id} paused"}
    # Pause all running jobs
    paused = []
    for status_dict in queue_manager.get_all_statuses():
        if status_dict and status_dict.get("status") == "running":
            jid = status_dict["job_id"]
            if await queue_manager.pause(jid):
                paused.append(jid)
    return {"message": f"Paused {len(paused)} job(s)", "paused": paused}


@router.post("/resume")
async def resume_queue(job_id: Optional[str] = Query(default=None)):
    """Resume a specific paused job or all paused jobs."""
    if job_id:
        ok = await queue_manager.resume(job_id)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Could not resume job {job_id}")
        return {"message": f"Job {job_id} resumed"}
    resumed = []
    for status_dict in queue_manager.get_all_statuses():
        if status_dict and status_dict.get("status") == "paused":
            jid = status_dict["job_id"]
            if await queue_manager.resume(jid):
                resumed.append(jid)
    return {"message": f"Resumed {len(resumed)} job(s)", "resumed": resumed}
