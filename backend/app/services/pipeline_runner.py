"""
Shared pipeline-launch helper.

Extracted from the POST /pipeline/{project_id}/run handler so the exact same
job-building logic can be reused by:
  - the manual HTTP endpoint (backend/app/api/pipeline.py)
  - the WhatsApp webhook resume handler (backend/app/api/webhooks.py)
  - the automation scheduler (backend/app/services/automation_service.py)
without drift between the three call sites.
"""
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.events import connection_manager
from app.models.job import JobType
from app.models.project import Project
from app.repositories.job_repo import JobRepository
from app.repositories.settings_repo import SettingsRepository
from app.workers.queue_manager import QueueJob, queue_manager as global_queue

_COMFYUI_DEFAULT = "http://127.0.0.1:8188"


def project_dir_for(project: Project) -> Path:
    cfg = get_settings()
    return Path(project.project_dir) if project.project_dir else (cfg.PROJECTS_DIR / project.id)


async def enqueue_pipeline_job(
    project: Project,
    job_repo: JobRepository,
    settings_repo: SettingsRepository,
) -> str:
    """Build a PipelineService for `project` and enqueue it on the global queue.

    Returns the newly created DB job id.
    """
    flux_cfg    = await settings_repo.get_flux_settings()
    piper_cfg   = await settings_repo.get_piper_settings()
    video_cfg   = await settings_repo.get_video_settings()
    gemini_cfg  = await settings_repo.get_gemini_settings()
    whisper_model = await settings_repo.get_by_key("whisper.model") or "base"
    whisper_device = await settings_repo.get_by_key("whisper.device") or "cpu"
    tts_engine    = await settings_repo.get_by_key("tts.engine") or "piper"
    channel_name  = (await settings_repo.get_by_key("channel.name")) or "Deep Dive AI"

    google_tts_cfg = None
    try:
        google_tts_cfg = await settings_repo.get_google_tts_settings()
    except Exception:
        pass

    comfyui_url = flux_cfg.comfyui_url or _COMFYUI_DEFAULT
    pdir = project_dir_for(project)

    db_job = await job_repo.create(
        project_id=project.id,
        job_type=JobType.PIPELINE,
        metadata={"project_type": project.project_type},
    )

    async def progress_cb(progress: float, message: str, data: dict) -> None:
        from app.database import get_session_factory
        async with get_session_factory()() as _sess:
            await JobRepository(_sess).update_progress(db_job.id, progress)
            await _sess.commit()
        await connection_manager.broadcast_to_project(
            project.id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "pipeline", "progress": progress, "message": message, **data},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.pipeline_service import PipelineService

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
            project_id=project.id,
            project_dir=pdir,
            project_type=project.project_type or "deep_dive",
            project_language=project.language or "en",
            gemini_settings=gemini_proxy,
            flux_settings=flux_cfg,
            piper_settings=piper_proxy,
            video_settings=video_proxy,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
            tts_engine=tts_engine,
            google_tts_settings=google_proxy,
            channel_name=channel_name,
            comfyui_url=comfyui_url,
            progress_callback=progress_cb,
        )
        return svc.execute()

    async def on_complete(result: Any) -> None:
        from app.database import get_session_factory
        from app.models.job import JobStatus
        status = JobStatus.PAUSED if isinstance(result, dict) and result.get("status") == "awaiting_input" else JobStatus.COMPLETED
        async with get_session_factory()() as _sess:
            await JobRepository(_sess).update_status(db_job.id, status)
            await _sess.commit()

    queue_job = QueueJob(
        job_id=db_job.id,
        project_id=project.id,
        job_type=JobType.PIPELINE,
        coroutine_factory=make_coro,
        priority=5.0,
        on_complete=on_complete,
    )
    await global_queue.enqueue(queue_job)

    return db_job.id


async def check_comfyui_online(comfyui_url: str) -> bool:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=4.0) as cl:
            r = await cl.get(f"{comfyui_url}/system_stats")
            return r.status_code == 200
    except Exception:
        return False
