"""
Content Generation API — drives the 7-step Gemini pipeline.

Endpoints:
  POST /content/{project_id}/trends          Step 1: discover trending topics (or AI news stories)
  POST /content/{project_id}/research        Step 2: research a topic (Deep Dive only)
  POST /content/{project_id}/script          Step 3: generate script
  POST /content/{project_id}/scenes          Step 4: break script into scenes JSON
  POST /content/{project_id}/image-prompts   Step 5: generate FLUX image prompts
  POST /content/{project_id}/thumbnail       Step 6: generate thumbnail concept
  POST /content/{project_id}/seo             Step 7: generate SEO metadata
  POST /content/{project_id}/generate        Steps 3-7: full pipeline (background)
"""
import json as _json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.services.content_service import ContentGenerationService

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class TrendsResponse(BaseModel):
    text: str


class ResearchRequest(BaseModel):
    topic: str


class ResearchResponse(BaseModel):
    topic: str
    text: str


class GenerateRequest(BaseModel):
    topic: str
    research: Optional[str] = None


class GenerateResponse(BaseModel):
    topic: str
    script: str
    scenes: str
    image_prompts: str
    thumbnail: str
    seo: str
    files_saved: list[str]


class ScriptRequest(BaseModel):
    research: str


class ScenesRequest(BaseModel):
    script: str


class ImagePromptsRequest(BaseModel):
    scenes_json: str


class ThumbnailRequest(BaseModel):
    script: str


class SeoRequest(BaseModel):
    script: str


# ── Shared helpers ────────────────────────────────────────────────────────────

async def _resolve(
    project_id: str,
    project_repo: ProjectRepository,
    settings_repo: SettingsRepository,
):
    """Return (project, gemini, project_dir, channel_name) or raise HTTPException."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)
    gemini = await settings_repo.get_gemini_settings()
    if not gemini.api_key:
        raise HTTPException(
            status_code=400,
            detail="Gemini API key not configured. Go to Settings → Gemini AI.",
        )
    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    channel_name = (await settings_repo.get_by_key("channel.name")) or "Deep Dive AI"
    return project, gemini, project_dir, channel_name


def _build_svc(project, gemini, project_dir, channel_name, **extra):
    return ContentGenerationService(
        project_id=project.id,
        project_dir=project_dir,
        api_key=gemini.api_key,
        pro_model=gemini.pro_model,
        script_model=gemini.script_model,
        flash_model=gemini.flash_model,
        search_grounding=gemini.search_grounding,
        image_backend=gemini.image_backend,
        language=project.language or "en",
        channel_name=channel_name,
        **extra,
    )


def _build_ai_news_svc(project, gemini, project_dir, channel_name, **extra):
    from app.services.ai_news_service import AiNewsService
    return AiNewsService(
        project_id=project.id,
        project_dir=project_dir,
        api_key=gemini.api_key,
        pro_model=gemini.pro_model,
        script_model=gemini.script_model,
        flash_model=gemini.flash_model,
        search_grounding=gemini.search_grounding,
        image_backend=gemini.image_backend,
        language=project.language or "en",
        channel_name=channel_name,
        **extra,
    )


def _is_ai_news(project) -> bool:
    return getattr(project, "project_type", "deep_dive") == "ai_news"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}/state")
async def get_content_state(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return all previously-generated content files so the UI can restore state after refresh."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    input_dir = project_dir / "input"

    def read(filename: str) -> str:
        p = input_dir / filename
        return p.read_text(encoding="utf-8") if p.exists() else ""

    return {
        "trends":        read("trends.txt"),
        "research":      read("research.txt"),
        "script":        read("script.md"),
        "scenes":        read("scenes.json"),
        "image_prompts": read("image_prompts.txt"),
        "thumbnail":     read("thumbnail_full.txt"),
        "seo":           read("seo.json"),
    }


@router.post("/{project_id}/trends", response_model=TrendsResponse)
async def discover_trends(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 1 — Discover topics.
    Deep Dive: broad AI trend discovery via Google Search.
    AI News: fetch today's top 10 AI stories and save topics.json for the script step."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if _is_ai_news(project):
        from app.services.ai_news_service import AiNewsService, scrape_rss_news

        stories = []
        try:
            svc = _build_ai_news_svc(project, gemini, project_dir, channel_name)
            stories = await svc.scrape_news_stories(n=10)
        except Exception as exc:
            logger.warning("Gemini AI news scrape failed, falling back to RSS: %s", exc)

        if not stories:
            try:
                stories = await scrape_rss_news(n=10)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to fetch AI news: {exc}")

        # Persist structured stories so the script endpoint can use them without re-scraping
        input_dir = project_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / "topics.json").write_text(
            _json.dumps(stories, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Format as readable Markdown for display in ContentGenPage
        today_str = date.today().strftime("%B %d, %Y")
        lines = [f"# Today's Top 10 AI News — {today_str}\n"]
        for i, s in enumerate(stories, 1):
            lines.append(f"## {i}. {s['title']}")
            src = s.get("source", "")
            if src:
                lines.append(f"*Source: {src}*\n")
            summary = s.get("summary", "")
            if summary:
                lines.append(f"{summary}\n")
            else:
                lines.append("")
        text = "\n".join(lines)
        (input_dir / "trends.txt").write_text(text, encoding="utf-8")
        return TrendsResponse(text=text)

    # Deep Dive: broad trend discovery
    svc = _build_svc(project, gemini, project_dir, channel_name)
    try:
        text = await svc.discover_trends()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return TrendsResponse(text=text)


@router.post("/{project_id}/research", response_model=ResearchResponse)
async def research_topic(
    project_id: str,
    body: ResearchRequest,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 2 — Research a topic and produce a fact-checked dossier (Deep Dive only)."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )
    svc = _build_svc(project, gemini, project_dir, channel_name)
    try:
        text = await svc.research_topic(body.topic)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ResearchResponse(topic=body.topic, text=text)


@router.post("/{project_id}/script")
async def generate_script(
    project_id: str,
    body: ScriptRequest,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 3 — Generate script.
    Deep Dive: documentary script from research dossier.
    AI News: 12-section news-anchor script from topics.json (saved by the trends step)."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if _is_ai_news(project):
        topics_path = project_dir / "input" / "topics.json"
        if not topics_path.exists():
            raise HTTPException(
                status_code=400,
                detail="Run 'Fetch AI News Topics' (Trend Discovery) first.",
            )
        stories = _json.loads(topics_path.read_text(encoding="utf-8"))
        svc = _build_ai_news_svc(project, gemini, project_dir, channel_name)
        try:
            text = await svc.generate_news_script(stories)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"text": text}

    # Deep Dive: documentary script from research
    svc = _build_svc(project, gemini, project_dir, channel_name)
    try:
        text = await svc.generate_script(body.research)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"text": text}


@router.post("/{project_id}/scenes")
async def generate_scenes(
    project_id: str,
    body: ScenesRequest,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 4 — Break script into scenes JSON."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )
    svc = _build_svc(project, gemini, project_dir, channel_name)
    try:
        text = await svc.generate_scenes(body.script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # For AI News: annotate each scene with story_number so the video renderer
    # can overlay "STORY X / 10" banners at the right timestamps.
    if _is_ai_news(project):
        try:
            from app.services.ai_news_service import AiNewsService
            script_path = project_dir / "input" / "script.md"
            if script_path.exists():
                script_text = script_path.read_text(encoding="utf-8")
                tagged = AiNewsService._assign_story_numbers(script_text, text)
                if tagged:
                    text = tagged
                    (project_dir / "input" / "scenes.json").write_text(
                        tagged, encoding="utf-8"
                    )
                    logger.info("scenes.json annotated with story_number for AI News project %s", project_id)
        except Exception:
            logger.warning("story_number annotation failed for %s — skipping", project_id, exc_info=True)

    return {"text": text}


@router.post("/{project_id}/image-prompts")
async def generate_image_prompts(
    project_id: str,
    body: ImagePromptsRequest,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 5 — Generate FLUX-optimized image prompts from scenes JSON."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )
    svc = _build_svc(project, gemini, project_dir, channel_name)
    try:
        text = await svc.generate_image_prompts(body.scenes_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"text": text}


@router.post("/{project_id}/thumbnail")
async def generate_thumbnail(
    project_id: str,
    body: ThumbnailRequest,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 6 — Generate thumbnail concept from script."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )
    svc = _build_svc(project, gemini, project_dir, channel_name)
    try:
        text = await svc.generate_thumbnail(body.script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"text": text}


@router.post("/{project_id}/seo")
async def generate_seo(
    project_id: str,
    body: SeoRequest,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 7 — Generate SEO metadata JSON from script."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )
    svc = _build_svc(project, gemini, project_dir, channel_name)
    try:
        text = await svc.generate_seo(body.script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"text": text}


@router.post("/{project_id}/generate")
async def generate_content(
    project_id: str,
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Steps 3-7 — Generate script, scenes, image prompts, thumbnail, SEO.
    Streams progress via WebSocket with job_type='content'."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    async def progress_cb(progress: float, message: str, data: dict):
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_type": "content", "progress": progress, "message": message, **data},
        )

    async def run():
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "content", "progress": 0, "message": "Starting content generation…"},
            )
            svc = _build_svc(project, gemini, project_dir, channel_name, progress_callback=progress_cb)
            result = await svc.generate_all(
                topic=body.topic,
                research=body.research or None,
            )
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "content", "result": {
                    "topic": result["topic"],
                    "files_saved": ["script.md", "scenes.json", "image_prompts.txt",
                                    "thumbnail_prompt.txt", "seo.json"],
                }},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "content", "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": "Content generation started — watch progress via WebSocket"}
