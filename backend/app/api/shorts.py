"""
Shorts API — generate and serve YouTube Shorts (1080×1920) rebuilt from scene clips.

POST /shorts/project/{project_id}/generate  — start background generation
GET  /shorts/project/{project_id}           — poll status + list ready clips
GET  /shorts/project/{project_id}/{filename}/file — serve a single short
DELETE /shorts/project/{project_id}         — delete all shorts
"""
import asyncio
import json
import shutil
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.dependencies import get_project_repo
from app.core.exceptions import ProjectNotFoundError
from app.repositories.project_repo import ProjectRepository
from app.services.shorts_service import ShortsService, read_status, SHORTS_DIR, _write_status

router = APIRouter()

# Module-level registry of running generation tasks (keyed by project_id)
_tasks: Dict[str, asyncio.Task] = {}


def _project_dir(project) -> Path:
    cfg = get_settings()
    return Path(project.project_dir) if project.project_dir else (cfg.PROJECTS_DIR / project.id)


class GenerateShortsBody(BaseModel):
    count: int = Field(default=5, ge=1, le=10)


# ---------------------------------------------------------------------------
# GET /shorts/project/{project_id}  — status + clip list
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def get_shorts_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    shorts_dir = pdir / "output" / SHORTS_DIR
    status = read_status(shorts_dir)
    shorts = ShortsService.list_shorts(pdir)

    manifest_path = shorts_dir / "shorts_manifest.json"
    meta: dict = {}
    if manifest_path.exists():
        try:
            meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "state": status.get("state", "idle"),
        "progress": status.get("progress", 0),
        "message": status.get("message", ""),
        "shorts": shorts,
        "count": len(shorts),
        "resolution": meta.get("resolution", "1080x1920"),
    }


# ---------------------------------------------------------------------------
# POST /shorts/project/{project_id}/generate  — kick off background task
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/generate")
async def generate_shorts(
    project_id: str,
    body: GenerateShortsBody,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)

    # Require at least clips or images to build from
    clips_dir = pdir / "clips"
    images_dir = pdir / "images"
    has_clips = clips_dir.exists() and bool(list(clips_dir.glob("scene_*.mp4"))[:1])
    has_images = images_dir.exists() and bool(list(images_dir.glob("scene_*.png"))[:1])

    if not (has_clips or has_images):
        raise HTTPException(
            status_code=400,
            detail="No scene clips or images found — generate images first.",
        )

    # Cancel any already-running task for this project
    existing = _tasks.get(project_id)
    if existing and not existing.done():
        existing.cancel()

    svc = ShortsService(project_id=project_id, project_dir=pdir, count=body.count)

    async def _run():
        try:
            await svc.generate()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            shorts_dir = pdir / "output" / SHORTS_DIR
            shorts_dir.mkdir(parents=True, exist_ok=True)
            _write_status(shorts_dir, "error", 0, str(exc))

    task = asyncio.create_task(_run())
    _tasks[project_id] = task

    return {
        "status": "generating",
        "count": body.count,
        "message": f"Building {body.count} shorts from scene clips in background",
    }


# ---------------------------------------------------------------------------
# GET /shorts/project/{project_id}/{filename}/file  — serve one short
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/{filename}/file")
async def get_short_file(
    project_id: str,
    filename: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = _project_dir(project) / "output" / SHORTS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Short not found: {filename}")

    return FileResponse(
        str(path),
        media_type="video/mp4",
        filename=filename,
        headers={"Accept-Ranges": "bytes"},
    )


# ---------------------------------------------------------------------------
# DELETE /shorts/project/{project_id}  — delete all shorts
# ---------------------------------------------------------------------------
@router.delete("/project/{project_id}")
async def delete_shorts(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    # Cancel in-progress generation and wait a moment for file handles to release
    existing = _tasks.pop(project_id, None)
    if existing and not existing.done():
        existing.cancel()
        await asyncio.sleep(0.5)

    shorts_dir = _project_dir(project) / "output" / SHORTS_DIR
    if not shorts_dir.exists():
        return {"deleted": True, "message": "Nothing to delete"}

    # Fast path: remove the whole directory tree
    try:
        shutil.rmtree(str(shorts_dir))
        return {"deleted": True, "message": "Shorts deleted"}
    except Exception:
        pass

    # Slow path: Windows file-lock on open videos — retry per-file with backoff
    for f in list(shorts_dir.glob("*")):
        for _ in range(6):
            try:
                f.unlink(missing_ok=True)
                break
            except PermissionError:
                await asyncio.sleep(0.4)
            except Exception:
                break

    try:
        shorts_dir.rmdir()
    except Exception:
        pass

    return {"deleted": True, "message": "Shorts deleted"}
