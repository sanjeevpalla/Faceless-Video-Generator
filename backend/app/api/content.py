"""
Content Generation API — drives the 7-step Gemini pipeline, per language.

Endpoints:
  POST /content/{project_id}/trends          Step 1: discover trending topics (or AI news stories)
  POST /content/{project_id}/research        Step 2: research a topic (Deep Dive only)
  POST /content/{project_id}/script          Step 3: generate script
  POST /content/{project_id}/scenes          Step 4: break script into scenes JSON
  POST /content/{project_id}/image-prompts   Step 5: generate FLUX image prompts
  POST /content/{project_id}/thumbnail       Step 6: generate thumbnail concept
  POST /content/{project_id}/seo             Step 7: generate SEO metadata
  POST /content/{project_id}/generate        Steps 3-7: full pipeline (background, primary language)

Every step endpoint (except /generate) accepts an optional `language` query param
(defaults to the project's primary language). For the primary language, content is
generated fresh and read/written at project_dir/input/ exactly as before. For any other
project.languages entry, every step TRANSLATES the primary language's already-generated
content (one shared Gemini API key, Settings → Gemini AI — there is no per-language key)
rather than independently regenerating it, and is read/written at
project_dir/input/{language}/:
  - Research: not re-run — returns the primary language's research.txt as-is.
  - Script / Thumbnail / SEO: translated from the primary language's script.md /
    thumbnail_full.txt / seo.json (ContentGenerationService.translate_script /
    translate_thumbnail_concept / translate_seo).
  - Scenes: the primary language's fixed scene skeleton (scene_id/image_file/
    visual_description) has its narration/title translated
    (ContentGenerationService.translate_scenes_narration) so the shared FLUX images stay
    valid.
  - Image Prompts: derived purely from visual_description, which is identical across
    languages by construction — so non-primary languages just read the primary language's
    file rather than calling Gemini at all.
"""
import json as _json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.dependencies import get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError, ServiceError
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


def _is_primary(project, language: Optional[str]) -> bool:
    return (language or project.language or "en") == (project.language or "en")


def _input_dir_for(project_dir: Path, project, language: Optional[str]) -> Path:
    lang = language or project.language or "en"
    if lang == (project.language or "en"):
        return project_dir / "input"
    return project_dir / "input" / lang


def _build_svc(project, gemini, project_dir, channel_name, language: Optional[str] = None, **extra):
    lang = language or project.language or "en"
    svc = ContentGenerationService(
        project_id=project.id,
        project_dir=project_dir,
        api_key=gemini.api_key,
        pro_model=gemini.pro_model,
        script_model=gemini.script_model,
        flash_model=gemini.flash_model,
        search_grounding=gemini.search_grounding,
        image_backend=gemini.image_backend,
        language=lang,
        channel_name=channel_name,
        **extra,
    )
    svc.input_dir = _input_dir_for(project_dir, project, lang)
    svc.input_dir.mkdir(parents=True, exist_ok=True)
    return svc


def _build_ai_news_svc(project, gemini, project_dir, channel_name, language: Optional[str] = None, **extra):
    from app.services.ai_news_service import AiNewsService
    lang = language or project.language or "en"
    svc = AiNewsService(
        project_id=project.id,
        project_dir=project_dir,
        api_key=gemini.api_key,
        pro_model=gemini.pro_model,
        script_model=gemini.script_model,
        flash_model=gemini.flash_model,
        search_grounding=gemini.search_grounding,
        image_backend=gemini.image_backend,
        language=lang,
        channel_name=channel_name,
        **extra,
    )
    svc.input_dir = _input_dir_for(project_dir, project, lang)
    svc.input_dir.mkdir(parents=True, exist_ok=True)
    return svc


def _is_ai_news(project) -> bool:
    return getattr(project, "project_type", "deep_dive") == "ai_news"


LanguageQuery = Query(None, description="Language code — defaults to the project's primary language")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}/state")
async def get_content_state(
    project_id: str,
    language: Optional[str] = LanguageQuery,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return all previously-generated content files so the UI can restore state after refresh."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    input_dir = _input_dir_for(project_dir, project, language)
    primary_input_dir = project_dir / "input"

    def read(filename: str, dir_override: Optional[Path] = None) -> str:
        p = (dir_override or input_dir) / filename
        return p.read_text(encoding="utf-8") if p.exists() else ""

    return {
        "trends":        read("trends.txt"),
        "research":      read("research.txt"),
        "script":        read("script.md"),
        "scenes":        read("scenes.json"),
        # Image prompts are shared — always reflect the primary language's file.
        "image_prompts": read("image_prompts.txt", primary_input_dir),
        "thumbnail":     read("thumbnail_full.txt"),
        "seo":           read("seo.json"),
    }


@router.post("/{project_id}/trends", response_model=TrendsResponse)
async def discover_trends(
    project_id: str,
    language: Optional[str] = LanguageQuery,
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

        input_dir = _input_dir_for(project_dir, project, language)
        stories = []
        try:
            svc = _build_ai_news_svc(project, gemini, project_dir, channel_name, language=language)
            stories = await svc.scrape_news_stories(n=10)
        except Exception as exc:
            logger.warning("Gemini AI news scrape failed, falling back to RSS: %s", exc)

        if not stories:
            try:
                from app.services.ai_news_service import get_recent_story_titles
                exclude_titles = get_recent_story_titles(exclude_dir=project_dir)
                stories = await scrape_rss_news(n=10, exclude_titles=exclude_titles)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to fetch AI news: {exc}")

        # Persist structured stories so the script endpoint can use them without re-scraping
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
    svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
    try:
        text = await svc.discover_trends()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return TrendsResponse(text=text)


@router.post("/{project_id}/research", response_model=ResearchResponse)
async def research_topic(
    project_id: str,
    body: ResearchRequest,
    language: Optional[str] = LanguageQuery,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 2 — Research a topic and produce a fact-checked dossier (Deep Dive only,
    primary language only — research runs once, not per language). Non-primary
    languages just return the primary language's already-saved research.txt."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if not _is_primary(project, language):
        primary_path = project_dir / "input" / "research.txt"
        text = primary_path.read_text(encoding="utf-8") if primary_path.exists() else ""
        return ResearchResponse(topic=body.topic, text=text)

    svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
    try:
        text = await svc.research_topic(body.topic)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ResearchResponse(topic=body.topic, text=text)


@router.post("/{project_id}/script")
async def generate_script(
    project_id: str,
    body: ScriptRequest,
    language: Optional[str] = LanguageQuery,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 3 — Generate script.
    Primary language — Deep Dive: documentary script from research dossier.
    AI News: 12-section news-anchor script from topics.json (saved by the trends step).
    Non-primary languages: translate the primary language's already-generated script.md
    rather than independently regenerating it."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if not _is_primary(project, language):
        primary_script_path = project_dir / "input" / "script.md"
        if not primary_script_path.exists():
            raise HTTPException(
                status_code=400,
                detail="Run Script for the primary language first.",
            )
        base_script = primary_script_path.read_text(encoding="utf-8")
        svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
        try:
            text = await svc.translate_script(base_script, language)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"text": text}

    if _is_ai_news(project):
        input_dir = _input_dir_for(project_dir, project, language)
        topics_path = input_dir / "topics.json"
        if not topics_path.exists():
            raise HTTPException(
                status_code=400,
                detail="Run 'Fetch AI News Topics' (Trend Discovery) first.",
            )
        stories = _json.loads(topics_path.read_text(encoding="utf-8"))
        svc = _build_ai_news_svc(project, gemini, project_dir, channel_name, language=language)
        try:
            text = await svc.generate_news_script(stories)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"text": text}

    # Deep Dive: documentary script from research
    svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
    try:
        text = await svc.generate_script(body.research)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"text": text}


@router.post("/{project_id}/scenes")
async def generate_scenes(
    project_id: str,
    body: ScenesRequest,
    language: Optional[str] = LanguageQuery,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 4 — Break script into scenes JSON.
    Primary language: segments its own script into the scene skeleton (scene_id,
    duration, image_file, visual_description) that images are generated from.
    Any other language: reuses the PRIMARY language's scene skeleton (so the shared
    images stay valid) and translates the narration/title of each scene."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if not _is_primary(project, language):
        primary_scenes_path = project_dir / "input" / "scenes.json"
        if not primary_scenes_path.exists():
            raise HTTPException(
                status_code=400,
                detail="Run Scenes for the primary language first — the shared image "
                       "skeleton must exist before translating other languages' narration.",
            )
        try:
            base_scenes = _json.loads(primary_scenes_path.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Primary scenes.json is invalid: {exc}")

        svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
        try:
            translated = await svc.translate_scenes_narration(base_scenes, language)
        except ServiceError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        text = _json.dumps(translated, indent=2, ensure_ascii=False)
        (svc.input_dir / "scenes.json").write_text(text, encoding="utf-8")
        return {"text": text}

    svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
    try:
        text = await svc.generate_scenes(body.script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # For AI News: annotate each scene with story_number so the video renderer
    # can overlay "STORY X / 10" banners at the right timestamps.
    if _is_ai_news(project):
        try:
            from app.services.ai_news_service import AiNewsService
            script_path = svc.input_dir / "script.md"
            if script_path.exists():
                script_text = script_path.read_text(encoding="utf-8")
                tagged = AiNewsService._assign_story_numbers(script_text, text)
                if tagged:
                    text = tagged
                    (svc.input_dir / "scenes.json").write_text(
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
    language: Optional[str] = LanguageQuery,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 5 — Generate FLUX-optimized image prompts from scenes JSON.
    Image prompts are derived purely from visual_description, which is identical
    across languages by construction — so non-primary languages just read the
    primary language's file instead of spending another Gemini call."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if not _is_primary(project, language):
        primary_path = project_dir / "input" / "image_prompts.txt"
        text = primary_path.read_text(encoding="utf-8") if primary_path.exists() else ""
        return {"text": text}

    svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
    try:
        text = await svc.generate_image_prompts(body.scenes_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"text": text}


@router.post("/{project_id}/thumbnail")
async def generate_thumbnail(
    project_id: str,
    body: ThumbnailRequest,
    language: Optional[str] = LanguageQuery,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 6 — Generate thumbnail concept from script (primary language).
    Non-primary languages translate the primary language's already-generated
    thumbnail concept — the FLUX-rendered background image itself is shared across
    every language; only the overlaid title/tags text differs per language."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if not _is_primary(project, language):
        primary_path = project_dir / "input" / "thumbnail_full.txt"
        if not primary_path.exists():
            raise HTTPException(
                status_code=400,
                detail="Run Thumbnail for the primary language first.",
            )
        base_thumbnail_full = primary_path.read_text(encoding="utf-8")
        svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
        try:
            text = await svc.translate_thumbnail_concept(base_thumbnail_full, language)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"text": text}

    svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
    try:
        text = await svc.generate_thumbnail(body.script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"text": text}


@router.post("/{project_id}/seo")
async def generate_seo(
    project_id: str,
    body: SeoRequest,
    language: Optional[str] = LanguageQuery,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Step 7 — Generate SEO metadata JSON from script (primary language).
    Non-primary languages translate the primary language's already-generated SEO
    metadata (title, alternate_titles, description, tags, hashtags, chapters,
    keywords) rather than independently regenerating it."""
    project, gemini, project_dir, channel_name = await _resolve(
        project_id, project_repo, settings_repo
    )

    if not _is_primary(project, language):
        primary_path = project_dir / "input" / "seo.json"
        if not primary_path.exists():
            raise HTTPException(
                status_code=400,
                detail="Run SEO for the primary language first.",
            )
        base_seo_json = primary_path.read_text(encoding="utf-8")
        svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
        try:
            text = await svc.translate_seo(base_seo_json, language)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"text": text}

    svc = _build_svc(project, gemini, project_dir, channel_name, language=language)
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
    """Steps 3-7 — Generate script, scenes, image prompts, thumbnail, SEO for the
    primary language. Streams progress via WebSocket with job_type='content'.
    Other languages are generated by the full pipeline (see PipelineService)."""
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
