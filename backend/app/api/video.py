"""
Video API — status, file serving, render info, FFmpeg check.
Actual render is triggered via POST /jobs/trigger/{project_id}/video.
"""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.core.dependencies import get_project_repo, get_settings_repo
from app.core.exceptions import ProjectNotFoundError
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository

router = APIRouter()


async def _unlink_with_retry(path: Path, retries: int = 6, delay: float = 0.5) -> bool:
    for attempt in range(retries):
        try:
            path.unlink(missing_ok=True)
            return True
        except PermissionError:
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    return False


def _project_dir(project) -> Path:
    settings = get_settings()
    return Path(project.project_dir) if project.project_dir else (settings.PROJECTS_DIR / project.id)


def _read_manifest(output_dir: Path) -> Optional[Dict[str, Any]]:
    p = output_dir / "manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# GET /video/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def get_video_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    output_dir = pdir / "output"
    final_path = output_dir / "video_final.mp4"
    manifest = _read_manifest(output_dir)

    if final_path.exists():
        stat = final_path.stat()
        size_mb = round(stat.st_size / (1024 * 1024), 2)
        return {
            "status": "ready",
            "filename": final_path.name,
            "size_mb": size_mb,
            "path": str(final_path),
            "manifest": manifest,
        }

    return {"status": "missing", "filename": None, "size_mb": 0, "path": None, "manifest": None}


# ---------------------------------------------------------------------------
# GET /video/project/{project_id}/file  — serve the video
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/file")
async def get_video_file(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "output" / "video_final.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Final video not rendered yet")

    return FileResponse(
        str(path),
        media_type="video/mp4",
        filename=f"{project.name}.mp4",
        headers={"Accept-Ranges": "bytes"},
    )


# ---------------------------------------------------------------------------
# GET /video/project/{project_id}/assets  — what's available for rendering
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/assets")
async def get_render_assets(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    project_type = getattr(project, "project_type", None) or "deep_dive"

    music_files = list((pdir / "input").glob("*.mp3")) + list((pdir / "input").glob("*.wav"))
    srt_exists = (pdir / "subtitles" / "subtitles.srt").exists()

    if project_type == "ai_news":
        # AI news images live in images/sections/{label}/scene_*.png
        section_images = list((pdir / "images" / "sections").glob("*/scene_*.png"))
        images_ready = len(section_images)
        # Check that at least one section has narration.wav
        audio_sections_dir = pdir / "audio" / "sections"
        voice_sections = 0
        if audio_sections_dir.exists():
            voice_sections = sum(
                1 for d in audio_sections_dir.iterdir()
                if d.is_dir() and (d / "narration.wav").exists()
            )
        audio_merged = voice_sections > 0
        can_render = images_ready > 0 and voice_sections > 0
        total_dur = 0.0
    else:
        images = sorted((pdir / "images").glob("scene_*.png"))
        images_ready = len(images)
        audio_merged = (pdir / "audio" / "narration_merged.wav").exists()
        can_render = images_ready > 0

        # Estimate total duration from scenes.json
        total_dur = 0.0
        scenes_file = pdir / "input" / "scenes.json"
        if scenes_file.exists():
            try:
                _d = json.loads(scenes_file.read_text(encoding="utf-8"))
                scenes = _d if isinstance(_d, list) else _d.get("scenes", [])
                total_dur = sum(float(s.get("duration", 5)) for s in scenes)
            except Exception:
                pass

    return {
        "images_ready": images_ready,
        "narration_ready": audio_merged,
        "music_file": music_files[0].name if music_files else None,
        "subtitles_ready": srt_exists,
        "estimated_duration": round(total_dur, 1),
        "can_render": can_render,
    }


# ---------------------------------------------------------------------------
# GET /video/ffmpeg/status
# ---------------------------------------------------------------------------
@router.get("/ffmpeg/status")
async def ffmpeg_status():
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    version = None
    if ffmpeg_path:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            first_line = result.stdout.split("\n")[0] if result.stdout else ""
            version = first_line[:80]
        except Exception:
            pass

    return {
        "ffmpeg_found": ffmpeg_path is not None,
        "ffprobe_found": ffprobe_path is not None,
        "ffmpeg_path": ffmpeg_path,
        "version": version,
        "ready": ffmpeg_path is not None,
    }


# ---------------------------------------------------------------------------
# GET /video/templates  — return all available templates
# ---------------------------------------------------------------------------
@router.get("/templates")
async def get_templates():
    from app.services.video_service import TEMPLATES

    def _motion_label(anims: list) -> str:
        if not anims or anims == ["none"]:
            return "none"
        labels = [a.replace("_", " ") for a in anims[:3]]
        if len(anims) > 3:
            labels.append("…")
        return ", ".join(labels)

    return {
        "templates": [
            {
                "id": key,
                "label": key.capitalize(),
                "transition": cfg["transition"],
                "motion": _motion_label(cfg.get("animations", ["zoom_in"])),
                "animations": cfg.get("animations", ["zoom_in"]),
                "color_grade": cfg["color_grade"],
                "subtitle_style": cfg["subtitle_style"],
                "music_volume": cfg["music_volume"],
            }
            for key, cfg in TEMPLATES.items()
        ]
    }


# ---------------------------------------------------------------------------
# DELETE /video/project/{project_id}  — delete rendered video files
# ---------------------------------------------------------------------------
@router.delete("/project/{project_id}")
async def delete_video(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    output_dir = pdir / "output"
    deleted = 0
    locked: List[str] = []

    targets = [
        output_dir / name
        for name in ["video_final.mp4", "_raw_video.mp4", "_concat.mp4", "_with_audio.mp4", "manifest.json"]
    ]
    scenes_dir = output_dir / "scenes"
    if scenes_dir.exists():
        targets += list(scenes_dir.glob("scene_*.mp4"))

    for f in targets:
        if not f.exists():
            continue
        if await _unlink_with_retry(f):
            deleted += 1
        else:
            locked.append(f.name)

    if locked:
        raise HTTPException(
            status_code=409,
            detail=f"Deleted {deleted} files but {len(locked)} still locked by another process: {', '.join(locked)}. Stop video playback and retry.",
        )

    return {"deleted_files": deleted, "message": f"Deleted {deleted} video files"}
