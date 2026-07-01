"""
Pipeline API — single-click full-pipeline orchestration.

Endpoints:
  GET  /pipeline/steps/{project_type}     — list step definitions
  POST /pipeline/{project_id}/run         — start pipeline job
  POST /pipeline/{project_id}/cancel      — cancel running pipeline job
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.core.dependencies import get_job_repo, get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError
from app.models.job import JobStatus, JobType
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.services.pipeline_service import AI_NEWS_STEPS, DEEP_DIVE_STEPS
from app.workers.queue_manager import QueueJob, queue_manager as global_queue

router = APIRouter()

_COMFYUI_DEFAULT = "http://127.0.0.1:8188"


def _project_dir(project) -> Path:
    cfg = get_settings()
    return Path(project.project_dir) if project.project_dir else (cfg.PROJECTS_DIR / project.id)


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

    # Load settings
    flux_cfg    = await settings_repo.get_flux_settings()
    piper_cfg   = await settings_repo.get_piper_settings()
    video_cfg   = await settings_repo.get_video_settings()
    whisper_cfg = await settings_repo.get_whisper_settings()
    gemini_cfg  = await settings_repo.get_gemini_settings()
    app_cfg     = await settings_repo.get_app_settings()

    google_tts_cfg = None
    try:
        google_tts_cfg = await settings_repo.get_google_tts_settings()
    except Exception:
        pass

    comfyui_url = flux_cfg.comfyui_url or _COMFYUI_DEFAULT

    # Warn if ComfyUI offline and project type needs it
    if body.check_comfyui:
        needs_comfyui = project.project_type != "ai_news" or True  # all types may need FLUX
        if needs_comfyui:
            try:
                async with httpx.AsyncClient(timeout=4.0) as cl:
                    r = await cl.get(f"{comfyui_url}/system_stats")
                    comfyui_online = r.status_code == 200
            except Exception:
                comfyui_online = False
        else:
            comfyui_online = True

        if not comfyui_online:
            raise HTTPException(
                status_code=503,
                detail=f"ComfyUI is offline at {comfyui_url}. "
                       "Start ComfyUI first, then retry.",
            )

    pdir = _project_dir(project)

    db_job = await job_repo.create(
        project_id=project_id,
        job_type=JobType.PIPELINE,
        metadata={"project_type": project.project_type},
    )

    async def progress_cb(progress: float, message: str, data: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _sess:
            await JobRepository(_sess).update_progress(db_job.id, progress)
            await _sess.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "pipeline", "progress": progress, "message": message, **data},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.pipeline_service import PipelineService

        class _GeminiProxy:
            pass

        # Build lightweight proxy objects so PipelineService can attribute-access settings
        gemini_proxy = type("G", (), {
            "api_key":          gemini_cfg.api_key if gemini_cfg else "",
            "pro_model":        getattr(gemini_cfg, "pro_model", "gemini-2.0-flash"),
            "script_model":     getattr(gemini_cfg, "script_model", "gemini-2.0-flash"),
            "flash_model":      getattr(gemini_cfg, "flash_model", "gemini-2.0-flash"),
            "search_grounding": getattr(gemini_cfg, "search_grounding", True),
            "image_backend":    getattr(gemini_cfg, "image_backend", "flux"),
        })()

        piper_proxy = type("P", (), {
            "executable": piper_cfg.executable if piper_cfg else "piper",
            "model_path": piper_cfg.model_path if piper_cfg else "",
            "speed":      piper_cfg.speed if piper_cfg else 1.0,
        })()

        video_proxy = video_cfg  # VideoSettings already has all attributes

        google_proxy = type("GT", (), {
            "api_key":       getattr(google_tts_cfg, "api_key", ""),
            "voice_name":    getattr(google_tts_cfg, "voice_name", "en-US-Neural2-D"),
            "language_code": getattr(google_tts_cfg, "language_code", "en-US"),
            "speaking_rate": getattr(google_tts_cfg, "speaking_rate", 1.0),
        })()

        svc = PipelineService(
            project_id=project_id,
            project_dir=pdir,
            project_type=project.project_type or "deep_dive",
            project_language=project.language or "en",
            gemini_settings=gemini_proxy,
            flux_settings=flux_cfg,
            piper_settings=piper_proxy,
            video_settings=video_proxy,
            whisper_model=whisper_cfg.model if whisper_cfg else "base",
            whisper_device=whisper_cfg.device if whisper_cfg else "cpu",
            tts_engine=getattr(app_cfg, "tts_engine", "piper") if app_cfg else "piper",
            google_tts_settings=google_proxy,
            channel_name=getattr(app_cfg, "channel_name", "Deep Dive AI") if app_cfg else "Deep Dive AI",
            comfyui_url=comfyui_url,
            progress_callback=progress_cb,
        )
        return svc.execute()

    queue_job = QueueJob(
        job_id=db_job.id,
        project_id=project_id,
        job_type=JobType.PIPELINE,
        coro_factory=make_coro,
        priority=5.0,
    )
    await global_queue.enqueue(queue_job)

    return {"job_id": db_job.id, "status": "queued"}


# ── POST /pipeline/{project_id}/cancel ────────────────────────────────────────

@router.post("/{project_id}/cancel")
async def cancel_pipeline(
    project_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
):
    """Cancel the active pipeline job for a project."""
    jobs = await job_repo.get_by_project(project_id, status="running", job_type=JobType.PIPELINE)
    running = jobs[0] if jobs else None
    if not running:
        raise HTTPException(status_code=404, detail="No running pipeline job found")

    cancelled = await global_queue.cancel(running.id)
    if not cancelled:
        await job_repo.update_status(running.id, JobStatus.CANCELLED)

    return {"job_id": running.id, "status": "cancelled"}
