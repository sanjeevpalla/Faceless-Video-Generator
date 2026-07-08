"""
Pipeline API — single-click full-pipeline orchestration.

Endpoints:
  GET  /pipeline/steps/{project_type}     — list step definitions
  POST /pipeline/{project_id}/run         — start pipeline job
  POST /pipeline/{project_id}/cancel      — cancel running pipeline job
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_job_repo, get_project_repo, get_settings_repo
from app.core.exceptions import ProjectNotFoundError
from app.models.job import JobStatus, JobType
from app.models.project import ProjectStatus
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.services.pipeline_service import AI_NEWS_STEPS, DEEP_DIVE_STEPS
from app.services.pipeline_runner import check_comfyui_online, enqueue_pipeline_job
from app.workers.queue_manager import queue_manager as global_queue

router = APIRouter()

_COMFYUI_DEFAULT = "http://127.0.0.1:8188"


# ── GET /pipeline/steps/{project_type} ────────────────────────────────────────

@router.get("/steps/{project_type}")
async def get_pipeline_steps(project_type: str):
    """Return the ordered step list for a given project type."""
    steps = AI_NEWS_STEPS if project_type == "ai_news" else DEEP_DIVE_STEPS
    return {
        "project_type": project_type,
        "steps": [{"name": n, "label": l} for n, l in steps],
    }


# ── POST /pipeline/{project_id}/run ───────────────────────────────────────────

class RunRequest(BaseModel):
    check_comfyui: bool = True


@router.post("/{project_id}/run")
async def run_pipeline(
    project_id: str,
    body: RunRequest = RunRequest(),
    project_repo: ProjectRepository = Depends(get_project_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Start the full generation pipeline for a project."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    if project.status == ProjectStatus.AWAITING_INPUT:
        raise HTTPException(
            status_code=409,
            detail="Project is already awaiting a WhatsApp reply — cannot start a new run "
                   "until that prompt is resolved or cancelled.",
        )

    if body.check_comfyui:
        flux_cfg = await settings_repo.get_flux_settings()
        comfyui_url = flux_cfg.comfyui_url or _COMFYUI_DEFAULT
        if not await check_comfyui_online(comfyui_url):
            raise HTTPException(
                status_code=503,
                detail=f"ComfyUI is offline at {comfyui_url}. "
                       "Start ComfyUI first, then retry.",
            )

    job_id = await enqueue_pipeline_job(project, job_repo, settings_repo)

    return {"job_id": job_id, "status": "queued"}


# ── POST /pipeline/{project_id}/cancel ────────────────────────────────────────

@router.post("/{project_id}/cancel")
async def cancel_pipeline(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
    job_repo: JobRepository = Depends(get_job_repo),
):
    """Cancel the active pipeline job for a project, or clear a stuck awaiting-WhatsApp state."""
    project = await project_repo.get_by_id(project_id)
    if project and project.status == ProjectStatus.AWAITING_INPUT:
        await project_repo.clear_awaiting_whatsapp_reply(project_id)
        return {"project_id": project_id, "status": "cleared_awaiting_input"}

    jobs = await job_repo.get_by_project(project_id, status="running", job_type=JobType.PIPELINE)
    running = jobs[0] if jobs else None
    if not running:
        raise HTTPException(status_code=404, detail="No running pipeline job found")

    cancelled = await global_queue.cancel(running.id)
    if not cancelled:
        await job_repo.update_status(running.id, JobStatus.CANCELLED)

    return {"job_id": running.id, "status": "cancelled"}
