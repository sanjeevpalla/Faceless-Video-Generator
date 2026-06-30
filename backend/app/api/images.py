"""
Images API — list generated scene images, serve them, trigger per-scene regeneration,
and expose ComfyUI status for the frontend.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

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


def _project_dir(project) -> Path:
    settings = get_settings()
    return Path(project.project_dir) if project.project_dir else (settings.PROJECTS_DIR / project.id)


def _read_prompts(project_dir: Path) -> List[str]:
    f = project_dir / "input" / "image_prompts.txt"
    if not f.exists():
        return []
    content = f.read_text(encoding="utf-8")
    # Structured format: extract only "PROMPT: ..." lines
    prompts = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("PROMPT:"):
            prompt = stripped[7:].strip()
            if prompt:
                prompts.append(prompt)
    # Fallback: plain one-prompt-per-line format (no PROMPT: prefix)
    if not prompts:
        prompts = [ln.strip() for ln in content.splitlines() if ln.strip()]
    return prompts


def _read_scenes(project_dir: Path) -> List[Dict[str, Any]]:
    f = project_dir / "input" / "scenes.json"
    if not f.exists():
        return []
    try:
        _d = json.loads(f.read_text(encoding="utf-8"))
        return _d if isinstance(_d, list) else _d.get("scenes", [])
    except Exception:
        return []


def _image_status(images_dir: Path, scene_id: int) -> Dict[str, Any]:
    filename = f"scene_{scene_id:03d}.png"
    path = images_dir / filename
    if path.exists():
        stat = path.stat()
        return {
            "scene_id": scene_id,
            "filename": filename,
            "status": "ready",
            "size": stat.st_size,
            "path": str(path),
        }
    return {"scene_id": scene_id, "filename": filename, "status": "missing", "size": 0, "path": None}


# ---------------------------------------------------------------------------
# GET /images/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def list_images(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    images_dir = pdir / "images"
    prompts = _read_prompts(pdir)
    scenes = _read_scenes(pdir)

    total = max(len(prompts), len(scenes))
    if total == 0:
        return {"total": 0, "generated": 0, "scenes": []}

    result_scenes = []
    for i in range(total):
        scene_id = i + 1
        status = _image_status(images_dir, scene_id)
        status["prompt"] = prompts[i] if i < len(prompts) else ""
        status["scene_title"] = scenes[i].get("title", f"Scene {scene_id}") if i < len(scenes) else f"Scene {scene_id}"
        result_scenes.append(status)

    generated = sum(1 for s in result_scenes if s["status"] == "ready")
    return {"total": total, "generated": generated, "scenes": result_scenes}


# ---------------------------------------------------------------------------
# GET /images/project/{project_id}/scene/{scene_id}/file  — serve image binary
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/scene/{scene_id}/file")
async def get_scene_image(
    project_id: str,
    scene_id: int,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    path = pdir / "images" / f"scene_{scene_id:03d}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Image for scene {scene_id} not generated yet")

    return FileResponse(str(path), media_type="image/png", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# GET /images/project/{project_id}/prompts
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/prompts")
async def get_prompts(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    prompts = _read_prompts(_project_dir(project))
    return {"prompts": prompts, "count": len(prompts)}


# ---------------------------------------------------------------------------
# POST /images/project/{project_id}/scene/{scene_id}/regenerate
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/scene/{scene_id}/regenerate")
async def regenerate_scene(
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
    prompts = _read_prompts(pdir)
    if scene_id < 1 or scene_id > len(prompts):
        raise HTTPException(status_code=400, detail=f"Scene {scene_id} out of range (1–{len(prompts)})")

    prompt = prompts[scene_id - 1]
    flux_settings = await settings_repo.get_flux_settings()

    db_job = await job_repo.create(
        project_id=project_id,
        job_type=JobType.IMAGE,
        metadata={"scene_id": scene_id, "single_scene": True},
    )

    async def progress_cb(progress: float, message: str, data: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_progress(db_job.id, progress)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "image", "scene_id": scene_id, "progress": progress, "message": message},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.image_service import ImageGenerationService
        svc = ImageGenerationService(
            project_id=project_id,
            project_dir=pdir,
            comfyui_url=flux_settings.comfyui_url,
            flux_settings=flux_settings.model_dump(),
            progress_callback=progress_cb,
        )
        return svc.generate_scene(scene_id, prompt)

    async def on_complete(result: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "scene_image_ready",
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
            {"job_id": db_job.id, "job_type": "image", "scene_id": scene_id, "error": str(exc)},
            job_id=db_job.id,
        )

    queue_job = QueueJob(
        job_id=db_job.id,
        project_id=project_id,
        job_type="image",
        coroutine_factory=make_coro,
        priority=10.0,  # single-scene regenerations get higher priority
        on_complete=on_complete,
        on_error=on_error,
    )
    await global_queue.enqueue(queue_job)

    return {
        "job_id": db_job.id,
        "scene_id": scene_id,
        "status": "queued",
        "message": f"Regeneration of scene {scene_id} queued",
    }


# ---------------------------------------------------------------------------
# GET /images/comfyui/status  — check if ComfyUI is reachable
# ---------------------------------------------------------------------------
@router.get("/comfyui/status")
async def comfyui_status(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    import httpx
    flux = await settings_repo.get_flux_settings()
    url = flux.comfyui_url.rstrip("/")
    async with httpx.AsyncClient(timeout=8.0) as client:
        # Try /system_stats first for VRAM info
        try:
            r = await client.get(f"{url}/system_stats")
            if r.status_code == 200:
                data = r.json()
                return {
                    "online": True,
                    "url": url,
                    "gpu_vram_total": data.get("system", {}).get("vram_total", 0),
                    "gpu_vram_free": data.get("system", {}).get("vram_free", 0),
                }
        except Exception:
            pass
        # Fallback: /queue is lightweight and responds even under heavy GPU load
        try:
            r = await client.get(f"{url}/queue", timeout=4.0)
            if r.status_code == 200:
                return {"online": True, "url": url}
        except Exception:
            pass
    return {"online": False, "url": url}


# ---------------------------------------------------------------------------
# POST /images/project/{project_id}/generate-gemini  — batch Gemini image gen
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/generate-gemini")
async def generate_images_gemini(
    project_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Batch-generate all scene images via gemini-3.1-flash-image (alternative to FLUX)."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    prompts = _read_prompts(pdir)
    if not prompts:
        raise HTTPException(status_code=400, detail="No image prompts found. Run Step 5 (Image Prompts) first.")

    gemini = await settings_repo.get_gemini_settings()
    if not gemini.api_key:
        raise HTTPException(status_code=400, detail="Gemini API key not configured. Go to Settings → Gemini AI.")

    db_job = await job_repo.create(
        project_id=project_id,
        job_type=JobType.IMAGE,
        metadata={"backend": "gemini", "total_scenes": len(prompts)},
    )

    async def progress_cb(progress: float, message: str, data: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_progress(db_job.id, progress)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": "image", "progress": progress, "message": message, **data},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.gemini_image_service import GeminiImageService
        svc = GeminiImageService(
            project_id=project_id,
            project_dir=pdir,
            api_key=gemini.api_key,
            model=gemini.image_model,
            progress_callback=progress_cb,
        )
        return svc.generate_all(prompts)

    async def on_complete(result: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_completed",
            {
                "job_id": db_job.id,
                "job_type": "image",
                "generated": result.get("generated", 0),
                "total": result.get("total", 0),
                "errors": result.get("errors", []),
            },
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
            {"job_id": db_job.id, "job_type": "image", "error": str(exc)},
            job_id=db_job.id,
        )

    queue_job = QueueJob(
        job_id=db_job.id,
        project_id=project_id,
        job_type="image",
        coroutine_factory=make_coro,
        priority=5.0,
        on_complete=on_complete,
        on_error=on_error,
    )
    await global_queue.enqueue(queue_job)

    return {
        "job_id": db_job.id,
        "total_scenes": len(prompts),
        "status": "queued",
        "message": f"Gemini image generation queued for {len(prompts)} scenes (4s/image rate limit)",
    }


# ---------------------------------------------------------------------------
# DELETE /images/project/{project_id}  — delete all generated images + cache
# ---------------------------------------------------------------------------
@router.delete("/project/{project_id}")
async def delete_images(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    deleted = 0

    for folder in [pdir / "images", pdir / "cache" / "images"]:
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file():
                    f.unlink(missing_ok=True)
                    deleted += 1

    return {"deleted_files": deleted, "message": f"Deleted {deleted} image files"}


# ---------------------------------------------------------------------------
# PUT /images/project/{project_id}/scene/{scene_id}/replace
# ---------------------------------------------------------------------------
@router.put("/project/{project_id}/scene/{scene_id}/replace")
async def replace_scene_image(
    project_id: str,
    scene_id: int,
    file: UploadFile = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Replace a scene image with a user-uploaded file. Converts to PNG automatically."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    images_dir = pdir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / f"scene_{scene_id:03d}.png"

    contents = await file.read()

    # Convert to PNG via Pillow so the file is always a valid PNG regardless of input format
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(contents)).convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PNG")
        dest.write_bytes(buf.getvalue())
    except Exception:
        dest.write_bytes(contents)

    return {"scene_id": scene_id, "replaced": True, "filename": dest.name, "size": dest.stat().st_size}
