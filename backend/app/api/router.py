from fastapi import APIRouter

from app.api import projects, settings, jobs, ws, logs, images, voice, subtitles, video, queue, thumbnail, metadata, wan2, services, narrator, shorts, content, ai_news

api_router = APIRouter()

api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(images.router, prefix="/images", tags=["images"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(subtitles.router, prefix="/subtitles", tags=["subtitles"])
api_router.include_router(video.router, prefix="/video", tags=["video"])
api_router.include_router(queue.router, prefix="/queue", tags=["queue"])
api_router.include_router(thumbnail.router, prefix="/thumbnail", tags=["thumbnail"])
api_router.include_router(metadata.router, prefix="/metadata", tags=["metadata"])
api_router.include_router(wan2.router, prefix="/wan2", tags=["wan2"])
api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(narrator.router, prefix="/narrator", tags=["narrator"])
api_router.include_router(shorts.router, prefix="/shorts", tags=["shorts"])
api_router.include_router(content.router, prefix="/content", tags=["content"])
api_router.include_router(ai_news.router, prefix="/ai-news", tags=["ai-news"])
