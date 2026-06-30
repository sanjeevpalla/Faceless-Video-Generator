from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.core.dependencies import get_job_repo, get_project_repo, get_queue_manager, get_settings_repo
from app.core.exceptions import JobNotFoundError, ProjectNotFoundError, ServiceError
from app.models.job import JobStatus, JobType
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.schemas.common import MessageResponse
from app.schemas.job import JobCreate, JobResponse
from app.core.events import connection_manager
from app.workers.queue_manager import QueueJob, queue_manager as global_queue

router = APIRouter()


def _job_to_response(job) -> JobResponse:
    return JobResponse.from_orm_model(job)


def _to_store_key(job_type: str) -> str:
    """Map backend job_type to the key used in project.progress_state."""
    if job_type == "image":
        return "images"
    if job_type == "subtitle":
        return "subtitles"
    return job_type


@router.get("/project/{project_id}", response_model=List[JobResponse])
async def list_jobs_for_project(
    project_id: str,
    job_type: Optional[str] = Query(default=None),
    job_status: Optional[str] = Query(default=None, alias="status"),
    job_repo: JobRepository = Depends(get_job_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    jobs = await job_repo.get_by_project(
        project_id, status=job_status, job_type=job_type
    )
    return [_job_to_response(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
):
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return _job_to_response(job)


@router.post("/{job_id}/cancel", response_model=MessageResponse)
async def cancel_job(
    job_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
):
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise JobNotFoundError(job_id)

    await global_queue.cancel(job_id)
    await job_repo.update_status(job_id, JobStatus.CANCELLED)

    await connection_manager.broadcast_to_project(
        job.project_id,
        "job_cancelled",
        {"job_id": job_id, "job_type": str(job.job_type)},
        job_id=job_id,
    )
    return MessageResponse(message=f"Job {job_id} cancelled")


@router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
):
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise JobNotFoundError(job_id)

    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job with status {job.status}",
        )

    updated = await job_repo.increment_retry(job_id)
    return _job_to_response(updated)


@router.post("/trigger/{project_id}/{job_type}", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def trigger_job(
    project_id: str,
    job_type: str,
    background_tasks: BackgroundTasks,
    job_repo: JobRepository = Depends(get_job_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    try:
        jtype = JobType(job_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job type: {job_type!r}")

    # Create DB job record
    db_job = await job_repo.create(project_id=project_id, job_type=jtype)

    project_dir = Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    project_language = project.language or "en"
    flux_settings = await settings_repo.get_flux_settings()
    piper_settings = await settings_repo.get_piper_settings()
    video_settings = await settings_repo.get_video_settings()
    whisper_model = await settings_repo.get_by_key("whisper.model") or "base"
    whisper_device = await settings_repo.get_by_key("whisper.device") or "cuda"
    whisper_language = await settings_repo.get_by_key("whisper.language") or "en"

    async def progress_cb(progress: float, message: str, data: dict):
        # Use a fresh session — the request-scoped job_repo session closes when the
        # HTTP request ends, but this callback fires long after during job execution.
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_progress(db_job.id, progress)
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_id": db_job.id, "job_type": job_type, "progress": progress, "message": message, **data},
            job_id=db_job.id,
        )

    def make_coroutine():
        if jtype == JobType.TRANSLATE:
            from app.services.translation_service import TranslationService
            svc = TranslationService(
                project_id=project_id,
                project_dir=project_dir,
                target_language=project_language,
                progress_callback=progress_cb,
            )
            return svc.execute()
        elif jtype == JobType.IMAGE:
            from app.services.image_service import ImageGenerationService
            svc = ImageGenerationService(
                project_id=project_id,
                project_dir=project_dir,
                comfyui_url=flux_settings.comfyui_url,
                flux_settings=flux_settings.model_dump(),
                progress_callback=progress_cb,
            )
            return svc.execute()
        elif jtype == JobType.VOICE:
            async def _voice_job():
                tts_engine = await settings_repo.get_by_key("tts.engine") or "piper"
                if tts_engine == "google":
                    from app.services.google_tts_service import GoogleTTSService
                    gtts = await settings_repo.get_google_tts_settings()
                    if not gtts.api_key:
                        raise RuntimeError("Google TTS API key not configured — open Settings → Voice.")
                    svc = GoogleTTSService(
                        project_id=project_id,
                        project_dir=project_dir,
                        api_key=gtts.api_key,
                        voice_name=gtts.voice_name,
                        language_code=gtts.language_code,
                        speaking_rate=gtts.speaking_rate,
                        project_language=project_language,
                        progress_callback=progress_cb,
                    )
                else:
                    from app.services.piper_model_manager import ensure_model
                    from app.services.voice_service import VoiceGenerationService
                    resolved = await ensure_model(
                        project_language, piper_settings.model_path, progress_cb
                    )
                    svc = VoiceGenerationService(
                        project_id=project_id,
                        project_dir=project_dir,
                        piper_executable=piper_settings.executable,
                        model_path=resolved or piper_settings.model_path,
                        speed=piper_settings.speed,
                        progress_callback=progress_cb,
                    )
                return await svc.execute()
            return _voice_job()
        elif jtype == JobType.SUBTITLE:
            from app.services.subtitle_service import SubtitleGenerationService
            svc = SubtitleGenerationService(
                project_id=project_id,
                project_dir=project_dir,
                whisper_model=str(whisper_model),
                language=project_language,
                device=str(whisper_device),
                progress_callback=progress_cb,
            )
            return svc.execute()
        elif jtype == JobType.THUMBNAIL:
            from app.services.thumbnail_service import ThumbnailGenerationService
            svc = ThumbnailGenerationService(
                project_id=project_id,
                project_dir=project_dir,
                comfyui_url=flux_settings.comfyui_url,
                flux_settings=flux_settings.model_dump(),
                progress_callback=progress_cb,
            )
            return svc.execute()
        elif jtype == JobType.VIDEO:
            from app.services.video_service import VideoGenerationService
            svc = VideoGenerationService(
                project_id=project_id,
                project_dir=project_dir,
                template=video_settings.template,
                fps=video_settings.fps,
                resolution=video_settings.resolution,
                zoom_amount=video_settings.zoom_amount,
                transition_duration=video_settings.transition_duration,
                video_codec=video_settings.codec,
                audio_codec=video_settings.audio_codec,
                video_bitrate=video_settings.bitrate,
                audio_bitrate=video_settings.audio_bitrate,
                progress_callback=progress_cb,
                narrator_enabled=video_settings.narrator_enabled,
                narrator_clips_dir=video_settings.narrator_clips_dir,
                narrator_position=video_settings.narrator_position,
                narrator_width=video_settings.narrator_width,
                narrator_margin=video_settings.narrator_margin,
                narrator_bottom_margin=video_settings.narrator_bottom_margin,
                narrator_shape=video_settings.narrator_shape,
                logo_path=video_settings.logo_path,
                logo_opacity=video_settings.logo_opacity,
                logo_scale=video_settings.logo_scale,
                logo_margin=video_settings.logo_margin,
                burn_subtitles=video_settings.burn_subtitles,
                project_type=getattr(project, "project_type", "deep_dive") or "deep_dive",
            )
            return svc.execute()
        elif jtype == JobType.METADATA:
            from app.services.metadata_service import MetadataService
            svc = MetadataService(
                project_id=project_id,
                project_dir=project_dir,
                progress_callback=progress_cb,
            )
            return svc.execute()
        else:
            raise ServiceError("jobs", f"Unknown job type: {job_type}")

    async def on_complete(result: dict):
        from app.database import get_session_factory
        async with get_session_factory()() as _session:
            await JobRepository(_session).update_status(db_job.id, JobStatus.COMPLETED)
            await ProjectRepository(_session).update_progress(
                project_id,
                _to_store_key(job_type),
                {
                    "status": "completed",
                    "progress": 100,
                    "completed": result.get("generated") or result.get("completed") or 0,
                    "total": result.get("total") or 0,
                },
            )
            await _session.commit()
        await connection_manager.broadcast_to_project(
            project_id,
            "job_completed",
            {"job_id": db_job.id, "job_type": job_type, "result": result},
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
            {"job_id": db_job.id, "job_type": job_type, "error": str(exc)},
            job_id=db_job.id,
        )

    queue_job = QueueJob(
        job_id=db_job.id,
        project_id=project_id,
        job_type=job_type,
        coroutine_factory=make_coroutine,
        priority=0.0,
        on_complete=on_complete,
        on_error=on_error,
    )

    await global_queue.enqueue(queue_job)
    await job_repo.update_status(db_job.id, JobStatus.PENDING)

    return _job_to_response(db_job)
