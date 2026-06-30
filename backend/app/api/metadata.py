"""
Metadata API — read seo.json, generate & serve youtube_metadata.json,
allow inline editing, and provide copy-ready text output.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.core.dependencies import get_job_repo, get_project_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError
from app.models.job import JobStatus, JobType
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.workers.queue_manager import QueueJob, queue_manager as global_queue

router = APIRouter()


def _project_dir(project) -> Path:
    settings = get_settings()
    return Path(project.project_dir) if project.project_dir else (settings.PROJECTS_DIR / project.id)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# GET /metadata/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def get_metadata_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return a summary of all metadata files for this project."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    seo_path = pdir / "input" / "seo.json"
    yt_path = pdir / "output" / "youtube_metadata.json"
    desc_path = pdir / "output" / "description.txt"

    seo = _read_json(seo_path)
    yt = _read_json(yt_path)

    return {
        "seo_available": seo is not None,
        "youtube_metadata_available": yt is not None,
        "description_available": desc_path.exists(),
        "title": (yt or seo or {}).get("title", ""),
        "tag_count": len((yt or seo or {}).get("tags", [])),
        "description_length": len((yt or seo or {}).get("description", "")),
    }


# ---------------------------------------------------------------------------
# GET /metadata/project/{project_id}/seo
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/seo")
async def get_seo(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "input" / "seo.json"
    data = _read_json(path)
    if data is None:
        raise HTTPException(status_code=404, detail="seo.json not found — upload it on the Project page")
    return data


# ---------------------------------------------------------------------------
# GET /metadata/project/{project_id}/youtube
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/youtube")
async def get_youtube_metadata(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "output" / "youtube_metadata.json"
    data = _read_json(path)
    if data is None:
        raise HTTPException(status_code=404, detail="YouTube metadata not generated yet — trigger the metadata job first")
    return data


# ---------------------------------------------------------------------------
# PUT /metadata/project/{project_id}/youtube — update generated metadata
# ---------------------------------------------------------------------------
class MetadataUpdatePayload(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    privacy_status: Optional[str] = None


@router.put("/project/{project_id}/youtube")
async def update_youtube_metadata(
    project_id: str,
    payload: MetadataUpdatePayload,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    path = pdir / "output" / "youtube_metadata.json"
    data = _read_json(path) or {}

    if payload.title is not None:
        data["title"] = payload.title[:100]
    if payload.description is not None:
        data["description"] = payload.description[:5000]
    if payload.tags is not None:
        data["tags"] = payload.tags[:500]
    if payload.privacy_status is not None:
        data["privacy_status"] = payload.privacy_status

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also update description.txt
    desc_path = pdir / "output" / "description.txt"
    lines = [
        f"TITLE: {data.get('title', '')}",
        "",
        "DESCRIPTION:",
        data.get("description", ""),
        "",
        f"TAGS: {', '.join(data.get('tags', []))}",
    ]
    desc_path.write_text("\n".join(lines), encoding="utf-8")

    return data


# ---------------------------------------------------------------------------
# GET /metadata/project/{project_id}/copy  — formatted text for clipboard
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/copy")
async def get_copy_text(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return a structured text block ready to paste into YouTube Studio."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    yt = _read_json(pdir / "output" / "youtube_metadata.json")
    if not yt:
        raise HTTPException(status_code=404, detail="YouTube metadata not generated yet")

    chapters = yt.get("chapters", [])
    chapter_text = ""
    if chapters:
        chapter_text = "\n\n--- CHAPTERS ---\n"
        for ch in chapters:
            if isinstance(ch, dict):
                chapter_text += f"{ch.get('timestamp', '00:00')} {ch.get('title', '')}\n"
            elif isinstance(ch, str):
                parts = ch.split(" ", 1)
                ts = parts[0] if len(parts) > 1 and ":" in parts[0] else "00:00"
                name = parts[1] if len(parts) > 1 and ":" in parts[0] else ch
                chapter_text += f"{ts} {name}\n"

    hashtags = " ".join(yt.get("hashtags", []) or [])
    tags_str = ", ".join(yt.get("tags", []))

    copy_block = (
        f"=== TITLE ===\n{yt.get('title', '')}\n\n"
        f"=== DESCRIPTION ===\n{yt.get('description', '')}{chapter_text}\n\n"
        f"=== HASHTAGS ===\n{hashtags}\n\n"
        f"=== TAGS ===\n{tags_str}\n"
    )

    return {"text": copy_block, "title": yt.get("title", ""), "char_count": len(copy_block)}


# ---------------------------------------------------------------------------
# POST /metadata/project/{project_id}/generate — trigger metadata generation job
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/generate")
async def generate_metadata(
    project_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    db_job = await job_repo.create(project_id=project_id, job_type=JobType.METADATA)

    async def progress_cb(progress: float, message: str, data: dict):
        from app.database import get_session_factory
        from app.repositories.job_repo import JobRepository
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_progress(db_job.id, progress)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "metadata", "progress": progress, "message": message},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.metadata_service import MetadataService
        svc = MetadataService(
            project_id=project_id,
            project_dir=pdir,
            progress_callback=progress_cb,
        )
        return svc.execute()

    async def on_complete(result: dict):
        from app.database import get_session_factory
        from app.repositories.job_repo import JobRepository
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_completed",
            {"job_id": db_job.id, "job_type": "metadata", "result": result},
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
            {"job_id": db_job.id, "job_type": "metadata", "error": str(exc)},
            job_id=db_job.id,
        )

    await global_queue.enqueue(
        QueueJob(
            job_id=db_job.id,
            project_id=project_id,
            job_type="metadata",
            coroutine_factory=make_coro,
            priority=5.0,
            on_complete=on_complete,
            on_error=on_error,
        )
    )

    return {"job_id": db_job.id, "status": "queued", "message": "Metadata generation queued"}
