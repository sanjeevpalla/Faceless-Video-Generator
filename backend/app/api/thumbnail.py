"""
Thumbnail API — status, file serving, regeneration trigger.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.core.dependencies import get_job_repo, get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError
from app.models.job import JobStatus, JobType
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.workers.queue_manager import QueueJob, queue_manager as global_queue

router = APIRouter()


def _project_dir(project) -> Path:
    settings = get_settings()
    return Path(project.project_dir) if project.project_dir else (settings.PROJECTS_DIR / project.id)


# ---------------------------------------------------------------------------
# GET /thumbnail/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def get_thumbnail_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    thumb_path = pdir / "thumbnail" / "thumbnail.png"

    # Read the prompt used for generation
    prompt = ""
    prompt_file = pdir / "input" / "thumbnail_prompt.txt"
    if prompt_file.exists():
        prompt = prompt_file.read_text(encoding="utf-8").strip()
    if not prompt:
        seo_file = pdir / "input" / "seo.json"
        if seo_file.exists():
            try:
                seo = json.loads(seo_file.read_text(encoding="utf-8"))
                prompt = seo.get("title", "")
            except Exception:
                pass

    if thumb_path.exists():
        stat = thumb_path.stat()
        return {
            "status": "ready",
            "filename": thumb_path.name,
            "size": stat.st_size,
            "prompt": prompt,
        }

    return {"status": "missing", "filename": None, "size": 0, "prompt": prompt}


# ---------------------------------------------------------------------------
# GET /thumbnail/project/{project_id}/file
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/file")
async def get_thumbnail_file(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "thumbnail" / "thumbnail.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not generated yet")

    return FileResponse(str(path), media_type="image/png")


# ---------------------------------------------------------------------------
# POST /thumbnail/project/{project_id}/regenerate
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/regenerate")
async def regenerate_thumbnail(
    project_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    flux_settings = await settings_repo.get_flux_settings()

    db_job = await job_repo.create(project_id=project_id, job_type=JobType.THUMBNAIL)

    async def progress_cb(progress: float, message: str, data: dict):
        from app.database import get_session_factory
        from app.repositories.job_repo import JobRepository
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_progress(db_job.id, progress)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "thumbnail", "progress": progress, "message": message},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.thumbnail_service import ThumbnailGenerationService
        svc = ThumbnailGenerationService(
            project_id=project_id,
            project_dir=pdir,
            comfyui_url=flux_settings.comfyui_url,
            flux_settings=flux_settings.model_dump(),
            progress_callback=progress_cb,
        )
        return svc.generate()

    async def on_complete(result: dict):
        from app.database import get_session_factory
        from app.repositories.job_repo import JobRepository
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_completed",
            {"job_id": db_job.id, "job_type": "thumbnail", "result": result},
            job_id=db_job.id,
        )

    async def on_error(exc: Exception):
        from app.database import get_session_factory
        from app.repositories.job_repo import JobRepository
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.FAILED, error_message=str(exc))
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_failed",
            {"job_id": db_job.id, "job_type": "thumbnail", "error": str(exc)},
            job_id=db_job.id,
        )

    await global_queue.enqueue(
        QueueJob(
            job_id=db_job.id,
            project_id=project_id,
            job_type="thumbnail",
            coroutine_factory=make_coro,
            priority=8.0,
            on_complete=on_complete,
            on_error=on_error,
        )
    )

    return {"job_id": db_job.id, "status": "queued", "message": "Thumbnail regeneration queued"}


# ---------------------------------------------------------------------------
# DELETE /thumbnail/project/{project_id}  — delete generated thumbnail + cache
# ---------------------------------------------------------------------------
@router.delete("/project/{project_id}")
async def delete_thumbnail(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    deleted = 0

    for folder in [pdir / "thumbnail", pdir / "cache" / "thumbnail"]:
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file():
                    f.unlink(missing_ok=True)
                    deleted += 1

    return {"deleted_files": deleted, "message": f"Deleted {deleted} thumbnail files"}
