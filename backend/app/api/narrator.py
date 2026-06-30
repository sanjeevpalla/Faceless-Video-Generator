"""
Narrator clip management — list, upload, delete MP4 clips for the per-project
narrator/ folder, plus AI background removal via rembg.
"""
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from app.config import get_settings
from app.core.dependencies import get_project_repo
from app.core.exceptions import ProjectNotFoundError
from app.repositories.project_repo import ProjectRepository

router = APIRouter()

MAX_CLIP_SIZE_MB = 500


def _narrator_dir(project) -> Path:
    settings = get_settings()
    pdir = (
        Path(project.project_dir)
        if project.project_dir
        else (settings.PROJECTS_DIR / project.id)
    )
    return pdir / "narrator"


@router.get("/project/{project_id}")
async def list_narrator_clips(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return the list of narrator .mp4 clips uploaded to this project."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    nar_dir = _narrator_dir(project)
    if not nar_dir.exists():
        return {"clips": [], "count": 0}

    clips = [
        {
            "filename": f.name,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
        }
        for f in sorted(nar_dir.glob("*.mp4"))
    ]
    return {"clips": clips, "count": len(clips)}


@router.post("/project/{project_id}/upload")
async def upload_narrator_clips(
    project_id: str,
    files: List[UploadFile] = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Upload one or more .mp4 clips to the project's narrator/ folder."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    nar_dir = _narrator_dir(project)
    nar_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for file in files:
        fname = file.filename or "narrator.mp4"
        if not fname.lower().endswith(".mp4"):
            raise HTTPException(status_code=400, detail=f"{fname!r} must be an .mp4 file")

        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail=f"{fname!r} is empty")

        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_CLIP_SIZE_MB:
            raise HTTPException(
                status_code=413,
                detail=f"{fname!r} is {size_mb:.0f} MB — limit is {MAX_CLIP_SIZE_MB} MB per clip",
            )

        dest = nar_dir / fname
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)

        uploaded.append({"filename": dest.name, "size_mb": round(size_mb, 2)})

    return {"uploaded": uploaded, "count": len(uploaded)}


@router.delete("/project/{project_id}/{filename}")
async def delete_narrator_clip(
    project_id: str,
    filename: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete a single narrator clip by filename."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    clip_path = _narrator_dir(project) / filename
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail=f"Clip {filename!r} not found")

    clip_path.unlink()
    return {"deleted": filename}


# ---------------------------------------------------------------------------
# Background removal
# ---------------------------------------------------------------------------

def _resolve_clips(clips_dir: Optional[str], project_id: Optional[str], project) -> List[Path]:
    """Find .mp4 clips from either a global dir or a project's narrator/ folder."""
    if clips_dir:
        d = Path(clips_dir)
        if not d.exists():
            raise HTTPException(status_code=404, detail=f"Folder not found: {clips_dir}")
        clips = sorted(d.glob("*.mp4"))
        if not clips:
            raise HTTPException(status_code=404, detail="No .mp4 clips found in folder")
        return clips

    if project:
        nar_dir = _narrator_dir(project)
        if not nar_dir.exists() or not list(nar_dir.glob("*.mp4")):
            raise HTTPException(status_code=404, detail="No narrator clips in project folder")
        return sorted(nar_dir.glob("*.mp4"))

    raise HTTPException(status_code=400, detail="Provide clips_dir or project_id")


@router.get("/bg-status")
async def bg_removal_status(
    clips_dir: Optional[str] = None,
    project_id: Optional[str] = None,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return which clips have already had their background removed."""
    from app.services.narrator_bg_service import NarratorBgRemoveService

    project = await project_repo.get_by_id(project_id) if project_id else None
    clips = _resolve_clips(clips_dir, project_id, project)

    result = [
        {
            "filename": c.name,
            "processed": NarratorBgRemoveService.has_nobg(c),
            "nobg_filename": NarratorBgRemoveService.nobg_path(c).name,
        }
        for c in clips
    ]
    processed = sum(1 for r in result if r["processed"])
    return {"clips": result, "processed": processed, "total": len(result)}


@router.post("/remove-background")
async def remove_background(
    clips_dir: Optional[str] = Body(default=None),
    project_id: Optional[str] = Body(default=None),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Remove background from narrator clips using AI segmentation (rembg u2netp).
    Produces *_nobg.webm with alpha channel alongside each original .mp4.
    Existing processed files are skipped (re-process by deleting *_nobg.webm first).
    """
    try:
        from app.services.narrator_bg_service import NarratorBgRemoveService
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="rembg not installed — run: pip install rembg",
        )

    project = await project_repo.get_by_id(project_id) if project_id else None
    clips = _resolve_clips(clips_dir, project_id, project)

    # Skip clips that already have a processed version
    pending = [c for c in clips if not NarratorBgRemoveService.has_nobg(c)]
    if not pending:
        return {"results": [], "processed": 0, "skipped": len(clips), "message": "All clips already processed"}

    svc = NarratorBgRemoveService()
    results = await svc.process_clips(pending)

    ok    = sum(1 for r in results if r["status"] == "ok")
    error = sum(1 for r in results if r["status"] == "error")
    return {
        "results": results,
        "processed": ok,
        "errors": error,
        "skipped": len(clips) - len(pending),
    }
