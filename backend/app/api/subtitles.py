"""
Subtitles API — list generated subtitle files, serve SRT/VTT, return parsed
segments, check Whisper availability, and allow triggering regeneration.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_dir(project) -> Path:
    settings = get_settings()
    return Path(project.project_dir) if project.project_dir else (settings.PROJECTS_DIR / project.id)


def _parse_srt(srt_text: str) -> List[Dict[str, Any]]:
    """Parse SRT content into a list of segment dicts."""
    segments = []
    blocks = srt_text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        time_parts = lines[1].split(" --> ")
        if len(time_parts) != 2:
            continue

        def srt_to_seconds(t: str) -> float:
            t = t.replace(",", ".").strip()
            parts = t.split(":")
            h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
            return h * 3600 + m * 60 + s

        text = " ".join(lines[2:]).strip()
        segments.append({
            "id": idx,
            "start": srt_to_seconds(time_parts[0]),
            "end": srt_to_seconds(time_parts[1]),
            "text": text,
        })
    return segments


def _srt_to_vtt(srt_text: str) -> str:
    """Convert SRT content to WebVTT format."""
    vtt = "WEBVTT\n\n"
    vtt += srt_text.replace(",", ".")
    return vtt


# ---------------------------------------------------------------------------
# GET /subtitles/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def get_subtitle_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    subs_dir = pdir / "subtitles"
    srt_path = subs_dir / "subtitles.srt"
    vtt_path = subs_dir / "subtitles.vtt"

    srt_exists = srt_path.exists()
    vtt_exists = vtt_path.exists()

    segments = []
    srt_content = ""
    if srt_exists:
        srt_content = srt_path.read_text(encoding="utf-8")
        segments = _parse_srt(srt_content)

    total_duration = segments[-1]["end"] if segments else 0.0

    return {
        "status": "ready" if srt_exists else "missing",
        "srt_exists": srt_exists,
        "vtt_exists": vtt_exists,
        "segment_count": len(segments),
        "total_duration": round(total_duration, 2),
        "srt_size": srt_path.stat().st_size if srt_exists else 0,
    }


# ---------------------------------------------------------------------------
# GET /subtitles/project/{project_id}/segments  — parsed SRT as JSON
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/segments")
async def get_segments(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    srt_path = _project_dir(project) / "subtitles" / "subtitles.srt"
    if not srt_path.exists():
        return {"segments": [], "segment_count": 0}

    srt_text = srt_path.read_text(encoding="utf-8")
    segments = _parse_srt(srt_text)
    return {"segments": segments, "segment_count": len(segments)}


# ---------------------------------------------------------------------------
# GET /subtitles/project/{project_id}/srt  — serve raw SRT text
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/srt")
async def get_srt(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "subtitles" / "subtitles.srt"
    if not path.exists():
        raise HTTPException(status_code=404, detail="SRT file not generated yet")

    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/plain")


# ---------------------------------------------------------------------------
# GET /subtitles/project/{project_id}/srt/download  — download SRT file
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/srt/download")
async def download_srt(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "subtitles" / "subtitles.srt"
    if not path.exists():
        raise HTTPException(status_code=404, detail="SRT file not generated yet")

    return FileResponse(
        str(path),
        media_type="application/x-subrip",
        filename=f"{project.name}_subtitles.srt",
    )


# ---------------------------------------------------------------------------
# GET /subtitles/project/{project_id}/vtt/download  — download VTT file
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/vtt/download")
async def download_vtt(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    vtt_path = pdir / "subtitles" / "subtitles.vtt"

    # Generate VTT on the fly from SRT if needed
    if not vtt_path.exists():
        srt_path = pdir / "subtitles" / "subtitles.srt"
        if not srt_path.exists():
            raise HTTPException(status_code=404, detail="Subtitle files not generated yet")
        vtt_content = _srt_to_vtt(srt_path.read_text(encoding="utf-8"))
        vtt_path.write_text(vtt_content, encoding="utf-8")

    return FileResponse(
        str(vtt_path),
        media_type="text/vtt",
        filename=f"{project.name}_subtitles.vtt",
    )


# ---------------------------------------------------------------------------
# GET /subtitles/whisper/status  — check Whisper availability
# ---------------------------------------------------------------------------
@router.get("/whisper/status")
async def whisper_status(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    model_name = await settings_repo.get_by_key("whisper.model") or "base"
    device = await settings_repo.get_by_key("whisper.device") or "cpu"

    try:
        import whisper as _whisper
        available_models = list(_whisper.available_models())
        return {
            "available": True,
            "configured_model": str(model_name),
            "device": str(device),
            "available_models": available_models,
            "version": getattr(_whisper, "__version__", "unknown"),
        }
    except ImportError:
        return {
            "available": False,
            "configured_model": str(model_name),
            "device": str(device),
            "available_models": [],
            "version": None,
            "error": "openai-whisper not installed. Run: pip install openai-whisper",
        }


# ---------------------------------------------------------------------------
# DELETE /subtitles/project/{project_id}  — delete generated subtitles + cache
# ---------------------------------------------------------------------------
@router.delete("/project/{project_id}")
async def delete_subtitles(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    deleted = 0

    for folder in [pdir / "subtitles", pdir / "cache" / "subtitles"]:
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file():
                    f.unlink(missing_ok=True)
                    deleted += 1

    return {"deleted_files": deleted, "message": f"Deleted {deleted} subtitle files"}
