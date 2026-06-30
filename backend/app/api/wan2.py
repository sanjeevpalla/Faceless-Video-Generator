"""
Wan2GP API — animate scene images into video clips via Wan2GP's I2V.

Endpoints:
  GET  /wan2/status                              — check if Wan2GP is running
  GET  /wan2/project/{project_id}                — list generated clips
  GET  /wan2/project/{project_id}/scene/{n}/file — stream a clip
  POST /wan2/project/{project_id}/generate       — queue full animation job
  POST /wan2/project/{project_id}/scene/{n}/animate — queue single-scene job
  DELETE /wan2/project/{project_id}              — delete all clips
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import get_settings
from app.core.dependencies import get_job_repo, get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError, ServiceError
from app.models.job import JobStatus, JobType
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.workers.queue_manager import QueueJob, queue_manager as global_queue

router = APIRouter()

class GenerateRequest(BaseModel):
    selected_scene_ids: Optional[List[int]] = None


def _project_dir(project) -> Path:
    settings = get_settings()
    return Path(project.project_dir) if project.project_dir else (settings.PROJECTS_DIR / project.id)


def _clip_status(
    clips_dir: Path,
    scene_id: int,
    images_dir: Optional[Path] = None,
    clip_type: Optional[str] = None,
) -> Dict[str, Any]:
    filename = f"scene_{scene_id:03d}.mp4"
    path = clips_dir / filename
    if path.exists():
        stat = path.stat()
        image_newer = False
        if images_dir:
            img = images_dir / f"scene_{scene_id:03d}.png"
            image_newer = img.exists() and img.stat().st_mtime > stat.st_mtime
        return {
            "scene_id": scene_id, "filename": filename, "status": "ready",
            "size": stat.st_size, "path": str(path), "image_newer": image_newer,
            "clip_type": clip_type,
        }
    return {
        "scene_id": scene_id, "filename": filename, "status": "missing",
        "size": 0, "path": None, "image_newer": False, "clip_type": None,
    }


# ---------------------------------------------------------------------------
# GET /wan2/status  — probes ComfyUI (port 8188)
# ---------------------------------------------------------------------------
_COMFYUI_URL = "http://localhost:8188"

@router.get("/status")
async def wan2_status():
    """Check if ComfyUI is reachable at port 8188 (needed for LTX-Video clip generation)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_COMFYUI_URL}/system_stats")
            if r.status_code == 200:
                return {"online": True, "mode": "comfyui", "url": _COMFYUI_URL}
    except Exception as exc:
        return {"online": False, "mode": "offline", "url": _COMFYUI_URL, "error": str(exc)}

    return {"online": False, "mode": "offline", "url": _COMFYUI_URL, "error": "unexpected status"}


# ---------------------------------------------------------------------------
# GET /wan2/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def list_clips(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """List all animated clips for a project."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    clips_dir = pdir / "clips"
    images_dir = pdir / "images"

    image_files = sorted(images_dir.glob("scene_*.png"))
    total = len(image_files)
    if total == 0:
        return {"total": 0, "animated": 0, "scenes": []}

    manifest_path = clips_dir / "manifest.json"
    manifest: Optional[Dict] = None
    clip_type_map: Dict[int, str] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for clip in manifest.get("clips", []):
                sid = clip.get("scene_id")
                ctype = clip.get("type")
                if sid is not None and ctype:
                    clip_type_map[int(sid)] = ctype
        except Exception:
            pass

    scenes = []
    for img in image_files:
        scene_id = int(img.stem.split("_")[1])
        status = _clip_status(clips_dir, scene_id, images_dir, clip_type_map.get(scene_id))
        scenes.append(status)

    animated = sum(1 for s in scenes if s["status"] == "ready")
    return {"total": total, "animated": animated, "scenes": scenes, "manifest": manifest}


# ---------------------------------------------------------------------------
# GET /wan2/project/{project_id}/scene/{scene_id}/file
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/scene/{scene_id}/file")
async def get_clip_file(
    project_id: str,
    scene_id: int,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "clips" / f"scene_{scene_id:03d}.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Clip for scene {scene_id} not generated yet")

    return FileResponse(str(path), media_type="video/mp4", filename=path.name, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# POST /wan2/project/{project_id}/generate  — generate clips (LTX + animated)
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/generate")
async def generate_all_clips(
    project_id: str,
    body: GenerateRequest = Body(default=None),
    job_repo: JobRepository = Depends(get_job_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    if not list((pdir / "images").glob("scene_*.png")):
        raise HTTPException(status_code=400, detail="No scene images found — generate images first")

    selected_ids: Optional[List[int]] = body.selected_scene_ids if body else None
    flux_settings = await settings_repo.get_flux_settings()
    comfyui_url = flux_settings.comfyui_url or "http://127.0.0.1:8188"

    db_job = await job_repo.create(
        project_id=project_id,
        job_type=JobType.WAN2,
        metadata={"mode": "all", "selected_scene_ids": selected_ids},
    )

    async def progress_cb(progress: float, message: str, data: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_progress(db_job.id, progress)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "wan2", "progress": progress, "message": message, **data},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.ltx_comfy_service import LTXComfyService
        svc = LTXComfyService(
            project_id=project_id,
            project_dir=pdir,
            comfyui_url=comfyui_url,
            progress_callback=progress_cb,
        )
        return svc.animate_all(selected_scene_ids=selected_ids)

    async def on_complete(result: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await ProjectRepository(_session).update_progress(
                project_id,
                "wan2",
                {
                    "status": "completed",
                    "progress": 100,
                    "completed": result.get("animated", 0),
                    "total": result.get("total", 0),
                },
            )
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "wan2_complete",
            {"job_id": db_job.id, "animated": result.get("animated"), "total": result.get("total")},
            job_id=db_job.id,
        )

    async def on_error(exc: Exception):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.FAILED, error_message=str(exc))
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_failed",
            {"job_id": db_job.id, "job_type": "wan2", "error": str(exc)},
            job_id=db_job.id,
        )

    await global_queue.enqueue(QueueJob(
        job_id=db_job.id,
        project_id=project_id,
        job_type="wan2",
        coroutine_factory=make_coro,
        priority=5.0,
        on_complete=on_complete,
        on_error=on_error,
    ))

    return {"job_id": db_job.id, "status": "queued", "message": f"LTX-Video animation job queued for project {project_id}"}


# ---------------------------------------------------------------------------
# POST /wan2/project/{project_id}/scene/{scene_id}/animate
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/scene/{scene_id}/animate")
async def animate_single_scene(
    project_id: str,
    scene_id: int,
    job_repo: JobRepository = Depends(get_job_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    image_path = pdir / "images" / f"scene_{scene_id:03d}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image for scene {scene_id} not found")

    flux_settings = await settings_repo.get_flux_settings()
    comfyui_url = flux_settings.comfyui_url or "http://127.0.0.1:8188"

    db_job = await job_repo.create(
        project_id=project_id,
        job_type=JobType.WAN2,
        metadata={"mode": "single", "scene_id": scene_id},
    )

    async def progress_cb(progress: float, message: str, data: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_progress(db_job.id, progress)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "wan2", "scene_id": scene_id, "progress": progress, "message": message},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.ltx_comfy_service import LTXComfyService
        svc = LTXComfyService(
            project_id=project_id,
            project_dir=pdir,
            comfyui_url=comfyui_url,
            progress_callback=progress_cb,
        )
        prompts = svc._read_prompts()
        scenes_meta = svc._load_scenes_json()
        idx = scene_id - 1
        raw_prompt = prompts[idx] if idx < len(prompts) else ""
        scene_meta = scenes_meta[idx] if idx < len(scenes_meta) else {}
        prompt = svc._build_animation_prompt(raw_prompt, scene_meta)
        duration = svc._wav_duration(scene_id)
        if duration <= 0:
            duration = float(scene_meta.get("duration") or 0)
        num_frames = svc._duration_to_frames(duration)
        clip_path = svc.clips_dir / f"scene_{scene_id:03d}.mp4"
        return svc.animate_scene(scene_id, image_path, prompt, clip_path, num_frames)

    async def on_complete(result: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "wan2_clip_ready",
            {"job_id": db_job.id, "scene_id": scene_id, "filename": result.get("filename")},
            job_id=db_job.id,
        )

    async def on_error(exc: Exception):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.FAILED, error_message=str(exc))
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_failed",
            {"job_id": db_job.id, "job_type": "wan2", "scene_id": scene_id, "error": str(exc)},
            job_id=db_job.id,
        )

    await global_queue.enqueue(QueueJob(
        job_id=db_job.id,
        project_id=project_id,
        job_type="wan2",
        coroutine_factory=make_coro,
        priority=10.0,
        on_complete=on_complete,
        on_error=on_error,
    ))

    return {"job_id": db_job.id, "scene_id": scene_id, "status": "queued", "message": f"Scene {scene_id} animation queued"}


# ---------------------------------------------------------------------------
# DELETE /wan2/project/{project_id}
# ---------------------------------------------------------------------------
@router.delete("/project/{project_id}")
async def delete_clips(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    clips_dir = _project_dir(project) / "clips"
    deleted = 0
    if clips_dir.exists():
        for f in clips_dir.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)
                deleted += 1

    return {"deleted_files": deleted, "message": f"Deleted {deleted} clip files"}


# ---------------------------------------------------------------------------
# PUT /wan2/project/{project_id}/scene/{scene_id}/replace
# ---------------------------------------------------------------------------
@router.put("/project/{project_id}/scene/{scene_id}/replace")
async def replace_clip(
    project_id: str,
    scene_id: int,
    file: UploadFile = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Replace a scene clip with a user-uploaded video file."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    clips_dir = pdir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    dest = clips_dir / f"scene_{scene_id:03d}.mp4"

    contents = await file.read()
    dest.write_bytes(contents)

    return {"scene_id": scene_id, "replaced": True, "filename": dest.name, "size": dest.stat().st_size}
