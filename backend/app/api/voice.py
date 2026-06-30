"""
Voice API — list generated scene audio files, serve them, trigger per-scene
regeneration, check Piper availability, and expose narration text.
"""
import asyncio
import json
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

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


def _wav_duration(path: Path) -> float:
    """Return duration in seconds of a WAV file, or 0.0 on error."""
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate) if rate else 0.0
    except Exception:
        return 0.0


def _read_scenes(project_dir: Path) -> List[Dict[str, Any]]:
    f = project_dir / "input" / "scenes.json"
    if not f.exists():
        return []
    try:
        _d = json.loads(f.read_text(encoding="utf-8"))
        return _d if isinstance(_d, list) else _d.get("scenes", [])
    except Exception:
        return []


def _scene_audio_status(audio_dir: Path, scene_id: int) -> Dict[str, Any]:
    filename = f"scene_{scene_id:03d}.wav"
    path = audio_dir / filename
    if path.exists():
        stat = path.stat()
        duration = _wav_duration(path)
        return {
            "scene_id": scene_id,
            "filename": filename,
            "status": "ready",
            "size": stat.st_size,
            "duration": round(duration, 2),
            "path": str(path),
        }
    return {
        "scene_id": scene_id,
        "filename": filename,
        "status": "missing",
        "size": 0,
        "duration": 0.0,
        "path": None,
    }


# ---------------------------------------------------------------------------
# GET /voice/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def list_voice(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    audio_dir = pdir / "audio"
    scenes = _read_scenes(pdir)

    if not scenes:
        return {"total": 0, "generated": 0, "total_duration": 0.0, "scenes": [], "merged": None}

    result_scenes = []
    for raw in scenes:
        sid = raw.get("scene_id", len(result_scenes) + 1)
        info = _scene_audio_status(audio_dir, sid)
        info["narration"] = raw.get("narration", "")
        info["scene_title"] = raw.get("title", f"Scene {sid}")
        result_scenes.append(info)

    generated = sum(1 for s in result_scenes if s["status"] == "ready")
    total_duration = sum(s["duration"] for s in result_scenes)

    # Merged narration info
    merged = None
    merged_path = audio_dir / "narration_merged.wav"
    if merged_path.exists():
        merged = {
            "filename": merged_path.name,
            "size": merged_path.stat().st_size,
            "duration": round(_wav_duration(merged_path), 2),
        }

    return {
        "total": len(result_scenes),
        "generated": generated,
        "total_duration": round(total_duration, 2),
        "scenes": result_scenes,
        "merged": merged,
    }


# ---------------------------------------------------------------------------
# GET /voice/project/{project_id}/narration  — return scene narration texts
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/narration")
async def get_narration(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    scenes = _read_scenes(_project_dir(project))
    return {
        "scenes": [
            {
                "scene_id": s.get("scene_id", i + 1),
                "title": s.get("title", f"Scene {i + 1}"),
                "narration": s.get("narration", ""),
                "duration": s.get("duration", 0),
            }
            for i, s in enumerate(scenes)
        ]
    }


# ---------------------------------------------------------------------------
# GET /voice/project/{project_id}/scene/{scene_id}/file
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/scene/{scene_id}/file")
async def get_scene_audio(
    project_id: str,
    scene_id: int,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "audio" / f"scene_{scene_id:03d}.wav"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Audio for scene {scene_id} not generated yet")

    data = path.read_bytes()
    return Response(content=data, media_type="audio/wav")


# ---------------------------------------------------------------------------
# GET /voice/project/{project_id}/merged/file
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/merged/file")
async def get_merged_audio(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    path = _project_dir(project) / "audio" / "narration_merged.wav"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Merged narration audio not generated yet")

    # Read into memory so the file handle is released immediately (avoids WinError 32 on delete)
    data = path.read_bytes()
    return Response(content=data, media_type="audio/wav")


# ---------------------------------------------------------------------------
# POST /voice/project/{project_id}/scene/{scene_id}/regenerate
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/scene/{scene_id}/regenerate")
async def regenerate_scene_voice(
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
    scenes = _read_scenes(pdir)
    scene_map = {s.get("scene_id", i + 1): s for i, s in enumerate(scenes)}

    if scene_id not in scene_map:
        raise HTTPException(status_code=400, detail=f"Scene {scene_id} not found in scenes.json")

    narration = scene_map[scene_id].get("narration", "").strip()
    if not narration:
        raise HTTPException(status_code=400, detail=f"Scene {scene_id} has empty narration")

    piper_settings = await settings_repo.get_piper_settings()

    db_job = await job_repo.create(
        project_id=project_id,
        job_type=JobType.VOICE,
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
            {"job_id": db_job.id, "job_type": "voice", "scene_id": scene_id, "progress": progress, "message": message},
            job_id=db_job.id,
        )

    def make_coro():
        from app.services.voice_service import VoiceGenerationService
        svc = VoiceGenerationService(
            project_id=project_id,
            project_dir=pdir,
            piper_executable=piper_settings.executable,
            model_path=piper_settings.model_path,
            speed=piper_settings.speed,
            progress_callback=progress_cb,
        )
        return svc.generate_scene_audio(scene_id, narration)

    async def on_complete(result: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "scene_audio_ready",
            {"job_id": db_job.id, "scene_id": scene_id, "filename": result.get("filename"), "duration": result.get("duration", 0)},
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
            {"job_id": db_job.id, "job_type": "voice", "scene_id": scene_id, "error": str(exc)},
            job_id=db_job.id,
        )

    queue_job = QueueJob(
        job_id=db_job.id,
        project_id=project_id,
        job_type="voice",
        coroutine_factory=make_coro,
        priority=10.0,
        on_complete=on_complete,
        on_error=on_error,
    )
    await global_queue.enqueue(queue_job)

    return {
        "job_id": db_job.id,
        "scene_id": scene_id,
        "status": "queued",
        "message": f"Regeneration of scene {scene_id} audio queued",
    }


# ---------------------------------------------------------------------------
# GET /voice/piper/status  — check Piper executable availability
# ---------------------------------------------------------------------------
@router.get("/piper/status")
async def piper_status(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    import asyncio
    piper = await settings_repo.get_piper_settings()
    exe = piper.executable or "piper"
    model = piper.model_path

    # Check executable exists on PATH or as absolute path
    exe_path = shutil.which(exe)
    exe_found = exe_path is not None or Path(exe).is_file()

    model_found = bool(model) and Path(model).exists()

    # Quick version check
    version = None
    if exe_found:
        try:
            proc = await asyncio.create_subprocess_exec(
                exe_path or exe, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            raw = (out or err).decode("utf-8", errors="replace").strip()
            version = raw.split("\n")[0][:80] if raw else None
        except Exception:
            pass

    return {
        "executable": exe,
        "executable_found": exe_found,
        "executable_path": exe_path,
        "model_path": model,
        "model_found": model_found,
        "version": version,
        "ready": exe_found and model_found,
    }


# ---------------------------------------------------------------------------
# POST /voice/project/{project_id}/upload  — upload a narration audio file
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/upload")
async def upload_narration(
    project_id: str,
    file: UploadFile = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Accept any audio file and save it as narration_merged.wav.

    Non-WAV formats (MP3, M4A, OGG, FLAC, AAC…) are converted via FFmpeg.
    The resulting file is used by the video pipeline as the narration track,
    allowing users to skip Piper TTS entirely.
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    audio_dir = pdir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix.lower()
    tmp_path = audio_dir / f"_upload_tmp{suffix or '.bin'}"
    dest = audio_dir / "narration_merged.wav"

    contents = await file.read()
    tmp_path.write_bytes(contents)

    try:
        if suffix == ".wav":
            # Verify it's a valid PCM WAV before accepting
            try:
                with wave.open(str(tmp_path), "rb"):
                    pass
                shutil.move(str(tmp_path), str(dest))
            except Exception:
                # Fallback: re-encode through FFmpeg anyway
                _convert_to_wav(tmp_path, dest)
        else:
            _convert_to_wav(tmp_path, dest)
    finally:
        tmp_path.unlink(missing_ok=True)

    duration = _wav_duration(dest)
    return {
        "uploaded": True,
        "filename": dest.name,
        "duration": round(duration, 2),
        "size": dest.stat().st_size,
    }


def _convert_to_wav(src: Path, dest: Path) -> None:
    """Convert any FFmpeg-readable audio file to 16-bit mono WAV."""
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1",
            str(dest),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise HTTPException(
            status_code=422,
            detail=f"Audio conversion failed: {r.stderr[-300:]}",
        )


# ---------------------------------------------------------------------------
# Multi-part narration upload helpers
# ---------------------------------------------------------------------------
_PARTS_DIR_NAME = "parts"
_PARTS_MANIFEST = "manifest.json"


def _parts_dir(audio_dir: Path) -> Path:
    d = audio_dir / _PARTS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_manifest(parts_dir: Path) -> List[Dict[str, Any]]:
    m = parts_dir / _PARTS_MANIFEST
    if not m.exists():
        return []
    try:
        return json.loads(m.read_text(encoding="utf-8")).get("parts", [])
    except Exception:
        return []


def _write_manifest(parts_dir: Path, parts: List[Dict[str, Any]]) -> None:
    (parts_dir / _PARTS_MANIFEST).write_text(
        json.dumps({"parts": parts}, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# POST /voice/project/{project_id}/parts  — add one audio part
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/parts")
async def upload_audio_part(
    project_id: str,
    file: UploadFile = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Upload one audio part. Parts are stored in order and merged on demand."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    audio_dir = _project_dir(project) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    pd = _parts_dir(audio_dir)
    parts = _read_manifest(pd)

    index = len(parts)
    original_name = file.filename or f"part_{index}.bin"
    suffix = Path(original_name).suffix.lower()
    tmp_path = pd / f"_tmp_{index}{suffix or '.bin'}"
    dest = pd / f"part_{index:03d}.wav"

    contents = await file.read()
    tmp_path.write_bytes(contents)
    try:
        _convert_to_wav(tmp_path, dest)
    finally:
        tmp_path.unlink(missing_ok=True)

    duration = _wav_duration(dest)
    entry = {
        "index": index,
        "filename": dest.name,
        "original_name": original_name,
        "duration": round(duration, 2),
        "size": dest.stat().st_size,
    }
    parts.append(entry)
    _write_manifest(pd, parts)
    return entry


# ---------------------------------------------------------------------------
# GET /voice/project/{project_id}/parts  — list all parts
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/parts")
async def list_audio_parts(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pd = _parts_dir(_project_dir(project) / "audio")
    parts = _read_manifest(pd)
    total_duration = sum(p.get("duration", 0) for p in parts)
    return {"parts": parts, "total_duration": round(total_duration, 2)}


# ---------------------------------------------------------------------------
# GET /voice/project/{project_id}/parts/{index}/file  — stream one part
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/parts/{index}/file")
async def get_audio_part_file(
    project_id: str,
    index: int,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pd = _parts_dir(_project_dir(project) / "audio")
    parts = _read_manifest(pd)
    if index < 0 or index >= len(parts):
        raise HTTPException(status_code=404, detail=f"Part {index} not found")

    wav = pd / parts[index]["filename"]
    if not wav.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")
    return FileResponse(str(wav), media_type="audio/wav",
                        headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# DELETE /voice/project/{project_id}/parts/{index}  — remove one part
# ---------------------------------------------------------------------------
@router.delete("/project/{project_id}/parts/{index}")
async def delete_audio_part(
    project_id: str,
    index: int,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    audio_dir = _project_dir(project) / "audio"
    pd = _parts_dir(audio_dir)
    parts = _read_manifest(pd)
    if index < 0 or index >= len(parts):
        raise HTTPException(status_code=404, detail=f"Part {index} not found")

    # Remove the WAV file
    (pd / parts[index]["filename"]).unlink(missing_ok=True)
    parts.pop(index)

    # Renumber remaining files and manifest entries
    for i, p in enumerate(parts):
        old_wav = pd / p["filename"]
        new_wav = pd / f"part_{i:03d}.wav"
        if old_wav.exists() and old_wav != new_wav:
            old_wav.rename(new_wav)
        p["index"] = i
        p["filename"] = new_wav.name

    _write_manifest(pd, parts)
    return {"deleted": True, "remaining": len(parts)}


# ---------------------------------------------------------------------------
# POST /voice/project/{project_id}/parts/reorder  — reorder parts by index list
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/parts/reorder")
async def reorder_audio_parts(
    project_id: str,
    body: Dict[str, Any],
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Body: {"order": [2, 0, 1]}  — new position for each original index."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    audio_dir = _project_dir(project) / "audio"
    pd = _parts_dir(audio_dir)
    parts = _read_manifest(pd)
    order: List[int] = body.get("order", [])

    if sorted(order) != list(range(len(parts))):
        raise HTTPException(status_code=400, detail="order must be a permutation of existing part indices")

    # Move WAVs to temp names first to avoid collision during rename
    tmp_names = []
    for i, orig_idx in enumerate(order):
        src = pd / parts[orig_idx]["filename"]
        tmp = pd / f"_reorder_{i:03d}.wav"
        src.rename(tmp)
        tmp_names.append(tmp)

    new_parts = []
    for i, (tmp, orig_idx) in enumerate(zip(tmp_names, order)):
        dest = pd / f"part_{i:03d}.wav"
        tmp.rename(dest)
        entry = dict(parts[orig_idx])
        entry["index"] = i
        entry["filename"] = dest.name
        new_parts.append(entry)

    _write_manifest(pd, new_parts)
    return {"parts": new_parts}


# ---------------------------------------------------------------------------
# POST /voice/project/{project_id}/parts/merge  — concat parts → narration_merged.wav
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/parts/merge")
async def merge_audio_parts(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Concatenate all uploaded parts in order into narration_merged.wav."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    audio_dir = _project_dir(project) / "audio"
    pd = _parts_dir(audio_dir)
    parts = _read_manifest(pd)

    if not parts:
        raise HTTPException(status_code=400, detail="No audio parts uploaded yet")

    wav_paths = [pd / p["filename"] for p in parts]
    missing = [str(p) for p in wav_paths if not p.exists()]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing files: {missing}")

    file_list = pd / "file_list.txt"
    file_list.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in wav_paths),
        encoding="utf-8",
    )
    dest = audio_dir / "narration_merged.wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(file_list), "-c", "copy", str(dest)],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        raise HTTPException(status_code=422,
                            detail=f"Merge failed: {r.stderr[-400:]}")

    duration = _wav_duration(dest)
    return {
        "merged": True,
        "parts": len(parts),
        "duration": round(duration, 2),
        "filename": dest.name,
        "size": dest.stat().st_size,
    }


# ---------------------------------------------------------------------------
# DELETE /voice/project/{project_id}  — delete all generated audio + cache
# ---------------------------------------------------------------------------
async def _unlink_with_retry(path: Path, retries: int = 5, delay: float = 0.5) -> bool:
    for attempt in range(retries):
        try:
            path.unlink(missing_ok=True)
            return True
        except PermissionError:
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    return False


@router.delete("/project/{project_id}")
async def delete_voice(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    deleted = 0
    locked = []

    for folder in [pdir / "audio", pdir / "cache" / "audio"]:
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file():
                    if await _unlink_with_retry(f):
                        deleted += 1
                    else:
                        locked.append(f.name)

    if locked:
        raise HTTPException(
            status_code=409,
            detail=f"Deleted {deleted} files but {len(locked)} are still locked by another process: {', '.join(locked)}. Stop any audio playback and retry.",
        )

    return {"deleted_files": deleted, "message": f"Deleted {deleted} audio files"}
