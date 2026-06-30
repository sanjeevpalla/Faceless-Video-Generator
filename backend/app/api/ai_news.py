"""AI News Content Generation API."""
import asyncio
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.dependencies import get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.services.ai_news_service import AiNewsService, scrape_rss_news
from app.services.ai_news_section_service import AiNewsSectionService


def _extract_section_narrator_text(script: str, label: str) -> str:
    """Return concatenated [NARRATOR] text from the matching SECTION in script.md.

    label examples: 'intro' (SECTION 1), 'story_01' (SECTION 2), 'outro' (SECTION 12).
    Returns empty string if section not found.
    """
    # Map label → expected section number
    if label == "intro":
        target_num = 1
    elif label == "outro":
        target_num = 12
    elif label.startswith("story_"):
        try:
            story_num  = int(label.split("_")[1])
            target_num = story_num + 1
        except (IndexError, ValueError):
            return ""
    else:
        return ""

    pattern = re.compile(r"^SECTION\s+(\d+)[:\s—–-]+(.+)$", re.MULTILINE)
    matches  = list(pattern.finditer(script))
    script_len = len(script)

    for i, m in enumerate(matches):
        if int(m.group(1)) != target_num:
            continue
        end_pos      = matches[i + 1].start() if i + 1 < len(matches) else script_len
        section_text = script[m.start():end_pos]
        narrator_blocks = re.findall(
            r"\[NARRATOR\]\s*([\s\S]*?)(?=\[VISUAL\]|\[NARRATOR\]|^SECTION|\Z)",
            section_text, re.MULTILINE,
        )
        return " ".join(b.strip() for b in narrator_blocks if b.strip())

    return ""

logger = logging.getLogger(__name__)

router = APIRouter()


class NewsStory(BaseModel):
    title: str
    summary: str = ""


class GenerateRequest(BaseModel):
    stories: List[NewsStory]


class ShortOptions(BaseModel):
    narrator_text: Optional[str] = None
    logo_path: Optional[str] = None


@router.post("/{project_id}/generate")
async def generate_ai_news_content(
    project_id: str,
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate script, scenes, image prompts, thumbnail, and SEO from 10 news stories.
    Streams progress via WebSocket with job_type='ai_news_content'."""
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
    stories_data = [{"title": s.title, "summary": s.summary} for s in body.stories]

    async def progress_cb(progress: float, message: str, data: dict) -> None:
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_type": "ai_news_content", "progress": progress, "message": message, **data},
        )

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "ai_news_content", "progress": 0, "message": "Starting AI news content generation…"},
            )
            svc = AiNewsService(
                project_id=project_id,
                project_dir=project_dir,
                api_key=gemini.api_key,
                pro_model=gemini.pro_model,
                script_model=gemini.script_model,
                flash_model=gemini.flash_model,
                search_grounding=gemini.search_grounding,
                image_backend=gemini.image_backend,
                language=project.language or "en",
                channel_name=channel_name,
                progress_callback=progress_cb,
            )
            await svc.generate_all_for_news(stories_data)

            # Immediately split global scenes.json / image_prompts.txt into
            # per-section files so the Clips page shows sections as ready.
            script_path = project_dir / "input" / "script.md"
            if script_path.exists():
                await connection_manager.broadcast_to_project(
                    project_id, "job_progress",
                    {"job_type": "ai_news_content", "progress": 95,
                     "message": "Splitting scenes into per-section files…"},
                )
                async def _section_progress(progress: float, message: str, data: dict) -> None:
                    await connection_manager.broadcast_to_project(
                        project_id, "job_progress",
                        {"job_type": "ai_news_content", "progress": 95 + progress * 0.05,
                         "message": message, **data},
                    )
                sec_svc = AiNewsSectionService(
                    project_id=project_id,
                    project_dir=project_dir,
                    api_key=gemini.api_key,
                    pro_model=gemini.pro_model,
                    script_model=gemini.script_model,
                    flash_model=gemini.flash_model,
                    search_grounding=gemini.search_grounding,
                    image_backend=gemini.image_backend,
                    language=project.language or "en",
                    channel_name=channel_name,
                    progress_callback=_section_progress,
                )
                try:
                    await sec_svc.generate_all_sections(
                        script_path.read_text(encoding="utf-8"),
                        image_backend=gemini.image_backend,
                    )
                except Exception as sec_exc:
                    logger.warning("Per-section split failed (non-fatal): %s", sec_exc)

            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {
                    "job_type": "ai_news_content",
                    "result": {
                        "files_saved": [
                            "script.md", "scenes.json", "image_prompts.txt",
                            "thumbnail_prompt.txt", "seo.json",
                        ],
                    },
                },
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "ai_news_content", "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": "AI news content generation started — watch progress via WebSocket"}


@router.get("/{project_id}/scrape")
async def scrape_ai_news(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Fetch the 10 most important AI news stories from the last 24 hours.
    Uses Gemini search grounding when API key is configured, RSS feeds otherwise."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    channel_name = (await settings_repo.get_by_key("channel.name")) or "Deep Dive AI"
    gemini = await settings_repo.get_gemini_settings()

    if gemini.api_key:
        try:
            svc = AiNewsService(
                project_id=project_id,
                project_dir=project_dir,
                api_key=gemini.api_key,
                pro_model=gemini.pro_model,
                script_model=gemini.script_model,
                flash_model=gemini.flash_model,
                search_grounding=gemini.search_grounding,
                image_backend=gemini.image_backend,
                language=project.language or "en",
                channel_name=channel_name,
            )
            stories = await svc.scrape_news_stories(n=10)
            return {"stories": stories, "source": "gemini"}
        except Exception as exc:
            logger.warning("Gemini news scrape failed, falling back to RSS: %s", exc)

    stories = await scrape_rss_news(n=10)
    return {"stories": stories, "source": "rss"}


@router.get("/{project_id}/sections")
async def get_sections_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return status of all 13 AI News sections (intro + agenda + 10 stories + outro).

    For each section, reports which per-section asset files exist so the frontend
    can show which steps are complete and which still need to be generated.
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    input_dir   = project_dir / "input"
    audio_dir   = project_dir / "audio"
    sub_dir     = project_dir / "subtitles"
    clips_dir   = project_dir / "output" / "clips_ai_news"

    # Parse script.md to get section titles
    script_path = input_dir / "script.md"
    sections_from_script: List[Dict[str, Any]] = []
    if script_path.exists():
        script = script_path.read_text(encoding="utf-8")
        sections_from_script = AiNewsSectionService.parse_script_sections(script)

    # Build ordered section descriptors (13 total, including agenda)
    ordered: List[Dict[str, Any]] = []
    order = 1
    for sec in sections_from_script:
        lbl  = sec["label"]
        s_type = sec["type"]
        story_num = 0 if s_type in ("intro", "outro") else (sec["num"] - 1)
        ordered.append({
            "label":     lbl,
            "type":      s_type,
            "story_num": story_num,
            "title":     sec["title"],
            "order":     order,
        })
        order += 1
        if s_type == "intro":
            ordered.append({
                "label":     "agenda",
                "type":      "agenda",
                "story_num": 0,
                "title":     "Today's Top 10 AI Stories",
                "order":     order,
            })
            order += 1

    # Fall back to a static skeleton when script.md isn't generated yet
    if not ordered:
        ordered = [{"label": "intro", "type": "intro", "story_num": 0, "title": "Introduction", "order": 1},
                   {"label": "agenda", "type": "agenda", "story_num": 0, "title": "Today's Top 10 AI Stories", "order": 2}]
        for n in range(1, 11):
            ordered.append({"label": f"story_{n:02d}", "type": "story", "story_num": n,
                             "title": f"Story {n}", "order": n + 2})
        ordered.append({"label": "outro", "type": "outro", "story_num": 0, "title": "Outro", "order": 13})

    # Attach file-existence flags to every descriptor
    result: List[Dict[str, Any]] = []
    for s in ordered:
        lbl = s["label"]
        s_type = s["type"]
        is_agenda = s_type == "agenda"

        def _ex(*parts: str) -> bool:
            return Path(*parts).exists()

        sec_input   = input_dir / "sections" / lbl
        sec_images  = project_dir / "images" / "sections" / lbl
        shorts_dir2 = project_dir / "output" / "ai_news_shorts"
        ltx_clips_dir = project_dir / "clips" / "sections" / lbl
        has_ltx = (
            ltx_clips_dir.exists()
            and any(ltx_clips_dir.glob("scene_*.mp4"))
            and not is_agenda
        )
        result.append({
            **s,
            "has_scenes":        _ex(str(sec_input), "scenes.json") if not is_agenda else None,
            "has_image_prompts": _ex(str(sec_input), "image_prompts.txt") if not is_agenda else None,
            "has_images":        any(sec_images.glob("scene_*.png")) if sec_images.exists() and not is_agenda else (None if is_agenda else False),
            "has_voice":         _ex(str(audio_dir / "sections" / lbl), "narration.wav"),
            "has_subtitles":     _ex(str(sub_dir / "sections" / lbl), "subtitles.srt"),
            "has_clip":          _ex(str(clips_dir / f"{lbl}.mp4")),
            "has_short":         _ex(str(shorts_dir2 / f"{lbl}.mp4")),
            "has_ltx":           has_ltx,
        })

    return result


@router.post("/{project_id}/sections/generate")
async def generate_sections_content(
    project_id: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate per-section scenes.json and image_prompts.txt for all 12 script sections.

    Reads script.md and creates input/sections/{label}/scenes.json and
    input/sections/{label}/image_prompts.txt for each section.
    Streams progress via WebSocket with job_type='ai_news_sections'.
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    gemini = await settings_repo.get_gemini_settings()
    if not gemini.api_key:
        raise HTTPException(status_code=400, detail="Gemini API key not configured.")

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    script_path = project_dir / "input" / "script.md"
    if not script_path.exists():
        raise HTTPException(status_code=400, detail="script.md not found — generate script first.")

    channel_name = (await settings_repo.get_by_key("channel.name")) or "Deep Dive AI"

    async def progress_cb(progress: float, message: str, data: dict) -> None:
        # When step=="ai_news_section" a single section just finished — tell the
        # frontend to refresh the sections list immediately (section_done flag).
        section_done = data.get("step") == "ai_news_section"
        await connection_manager.broadcast_to_project(
            project_id, "job_progress",
            {
                "job_type": "ai_news_sections",
                "progress": progress,
                "message": message,
                "section_done": section_done,
                **data,
            },
        )

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "ai_news_sections", "progress": 0,
                 "message": "Generating per-section scenes and image prompts…"},
            )
            script = script_path.read_text(encoding="utf-8")
            svc = AiNewsSectionService(
                project_id=project_id,
                project_dir=project_dir,
                api_key=gemini.api_key,
                pro_model=gemini.pro_model,
                script_model=gemini.script_model,
                flash_model=gemini.flash_model,
                search_grounding=gemini.search_grounding,
                image_backend=gemini.image_backend,
                language=project.language or "en",
                channel_name=channel_name,
                progress_callback=progress_cb,
            )
            results = await svc.generate_all_sections(script, image_backend=gemini.image_backend)
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "ai_news_sections",
                 "result": {"sections_generated": len(results)}},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "ai_news_sections", "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": "Per-section content generation started"}


@router.post("/{project_id}/sections/{label}/images")
async def generate_section_images(
    project_id: str,
    label: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate images for one AI News section via FLUX (ComfyUI) or Gemini.

    Reads  input/sections/{label}/image_prompts.txt
    Saves  images/sections/{label}/scene_NNN.png
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    prompts_path = project_dir / "input" / "sections" / label / "image_prompts.txt"
    if not prompts_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"image_prompts.txt not found for section '{label}' — generate section content first.",
        )

    gemini = await settings_repo.get_gemini_settings()
    image_backend = (gemini.image_backend or "flux").lower()

    async def progress_cb(progress: float, message: str, data: dict) -> None:
        await connection_manager.broadcast_to_project(
            project_id, "job_progress",
            {"job_type": "section_images", "section": label,
             "progress": progress, "message": message, **data},
        )

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_images", "section": label,
                 "progress": 0, "message": f"Generating images for section '{label}'…"},
            )
            if image_backend == "gemini":
                if not gemini.api_key:
                    raise HTTPException(status_code=400, detail="Gemini API key not configured.")
                from app.services.gemini_image_service import GeminiImageService
                svc: Any = GeminiImageService(
                    project_id=project_id,
                    project_dir=project_dir,
                    api_key=gemini.api_key,
                    model=gemini.image_model,
                    progress_callback=progress_cb,
                )
            else:
                from app.services.image_service import ImageGenerationService
                flux_settings = await settings_repo.get_flux_settings()
                svc = ImageGenerationService(
                    project_id=project_id,
                    project_dir=project_dir,
                    comfyui_url=flux_settings.comfyui_url or "http://127.0.0.1:8188",
                    flux_settings={
                        "steps":     flux_settings.steps,
                        "cfg":       flux_settings.cfg,
                        "width":     flux_settings.width,
                        "height":    flux_settings.height,
                        "sampler":   flux_settings.sampler,
                        "scheduler": flux_settings.scheduler,
                    },
                    progress_callback=progress_cb,
                )
            result = await svc.generate_section_images(label, prompts_path)
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "section_images", "section": label, "result": result},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "section_images", "section": label, "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": f"Image generation started for section '{label}'"}


@router.delete("/{project_id}/sections/{label}/images")
async def delete_section_images(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete all generated images for one AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    img_dir = project_dir / "images" / "sections" / label
    deleted = 0
    if img_dir.exists():
        for f in img_dir.glob("scene_*.png"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted, "label": label}


@router.delete("/{project_id}/sections/images/all")
async def delete_all_section_images(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete all generated images across every AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    sections_img_dir = project_dir / "images" / "sections"
    deleted = 0
    if sections_img_dir.exists():
        for f in sections_img_dir.rglob("scene_*.png"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted}


@router.post("/{project_id}/sections/{label}/images/{scene_id}/regenerate")
async def regenerate_section_image(
    project_id: str,
    label: str,
    scene_id: int,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Delete one scene image and regenerate it (reuses generate_section_images resume logic)."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    prompts_path = project_dir / "input" / "sections" / label / "image_prompts.txt"
    if not prompts_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"image_prompts.txt not found for section '{label}'",
        )

    img_path = project_dir / "images" / "sections" / label / f"scene_{scene_id:03d}.png"
    if img_path.exists():
        img_path.unlink()

    gemini = await settings_repo.get_gemini_settings()
    image_backend = (gemini.image_backend or "flux").lower()

    async def progress_cb(progress: float, message: str, data: dict) -> None:
        await connection_manager.broadcast_to_project(
            project_id, "job_progress",
            {"job_type": "section_image_regen", "section": label, "scene_id": scene_id,
             "progress": progress, "message": message, **data},
        )

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_image_regen", "section": label, "scene_id": scene_id,
                 "progress": 0, "message": f"Regenerating scene {scene_id} in '{label}'…"},
            )
            if image_backend == "gemini":
                if not gemini.api_key:
                    raise HTTPException(status_code=400, detail="Gemini API key not configured.")
                from app.services.gemini_image_service import GeminiImageService
                svc: Any = GeminiImageService(
                    project_id=project_id,
                    project_dir=project_dir,
                    api_key=gemini.api_key,
                    model=gemini.image_model,
                    progress_callback=progress_cb,
                )
            else:
                from app.services.image_service import ImageGenerationService
                flux_settings = await settings_repo.get_flux_settings()
                svc = ImageGenerationService(
                    project_id=project_id,
                    project_dir=project_dir,
                    comfyui_url=flux_settings.comfyui_url or "http://127.0.0.1:8188",
                    flux_settings={
                        "steps":     flux_settings.steps,
                        "cfg":       flux_settings.cfg,
                        "width":     flux_settings.width,
                        "height":    flux_settings.height,
                        "sampler":   flux_settings.sampler,
                        "scheduler": flux_settings.scheduler,
                    },
                    progress_callback=progress_cb,
                )
            result = await svc.generate_section_images(label, prompts_path)
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "section_image_regen", "section": label, "scene_id": scene_id,
                 "result": result},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "section_image_regen", "section": label, "scene_id": scene_id,
                 "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": f"Regenerating scene {scene_id} in section '{label}'"}


@router.post("/{project_id}/sections/{label}/images/{scene_id}/upload")
async def upload_section_image(
    project_id: str,
    label: str,
    scene_id: int,
    file: UploadFile = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Upload a replacement image for one section scene."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    img_dir = project_dir / "images" / "sections" / label
    img_dir.mkdir(parents=True, exist_ok=True)

    dest = img_dir / f"scene_{scene_id:03d}.png"
    content = await file.read()
    dest.write_bytes(content)

    return {"status": "uploaded", "path": str(dest)}


@router.post("/{project_id}/sections/{label}/subtitles")
async def generate_section_subtitles(
    project_id: str,
    label: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Run Whisper on audio/sections/{label}/narration.wav → subtitles/sections/{label}/subtitles.srt."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    audio_path = project_dir / "audio" / "sections" / label / "narration.wav"
    if not audio_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"narration.wav not found for section '{label}' — generate voice first.",
        )

    whisper_model  = await settings_repo.get_by_key("whisper.model")  or "base"
    whisper_device = await settings_repo.get_by_key("whisper.device") or "cpu"

    async def progress_cb(progress: float, message: str, data: dict) -> None:
        await connection_manager.broadcast_to_project(
            project_id, "job_progress",
            {"job_type": "section_subtitles", "section": label,
             "progress": progress, "message": message, **data},
        )

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_subtitles", "section": label,
                 "progress": 0, "message": f"Generating subtitles for section '{label}'…"},
            )
            from app.services.subtitle_service import SubtitleGenerationService
            svc = SubtitleGenerationService(
                project_id=project_id,
                project_dir=project_dir,
                whisper_model=whisper_model,
                language=project.language or "en",
                device=whisper_device,
                progress_callback=progress_cb,
            )
            result = await svc.generate_section_subtitles(label, audio_path)
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "section_subtitles", "section": label, "result": result},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "section_subtitles", "section": label, "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": f"Subtitle generation started for section '{label}'"}


@router.post("/{project_id}/sections/subtitles/generate-missing")
async def generate_missing_sections_subtitles(
    project_id: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Run Whisper on all sections that have narration.wav but no subtitles.srt.

    Loads the Whisper model once and processes all pending sections sequentially.
    Broadcasts section_subtitles + all_sections_subtitles job events.
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )

    whisper_model  = await settings_repo.get_by_key("whisper.model")  or "base"
    whisper_device = await settings_repo.get_by_key("whisper.device") or "cpu"

    # Sections that have narration.wav but no subtitles.srt
    pending = [
        lbl for lbl in _SECTION_LABEL_ORDER
        if (project_dir / "audio" / "sections" / lbl / "narration.wav").exists()
        and not (project_dir / "subtitles" / "sections" / lbl / "subtitles.srt").exists()
    ]
    if not pending:
        return {"status": "nothing_to_do", "message": "All sections already have subtitles", "labels": []}

    async def run() -> None:
        _log = logging.getLogger(__name__)
        from app.services.subtitle_service import SubtitleGenerationService

        async def _progress(progress: float, message: str, data: dict,
                            _lbl: str = "") -> None:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_subtitles", "section": _lbl,
                 "progress": progress, "message": message, **data},
            )

        # One service instance = Whisper model loaded once for all sections
        svc = SubtitleGenerationService(
            project_id=project_id,
            project_dir=project_dir,
            whisper_model=whisper_model,
            language=project.language or "en",
            device=whisper_device,
        )

        total = len(pending)
        for idx, label in enumerate(pending):
            audio_path = project_dir / "audio" / "sections" / label / "narration.wav"
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_subtitles", "section": label,
                 "progress": 0,
                 "message": f"Subtitles {idx + 1}/{total}: '{label}'…"},
            )
            try:
                # Proper async callback — awaited by report_progress
                async def _section_cb(p: float, m: str, d: dict, _l: str = label) -> None:
                    await connection_manager.broadcast_to_project(
                        project_id, "job_progress",
                        {"job_type": "section_subtitles", "section": _l,
                         "progress": p, "message": m, **d},
                    )
                svc.progress_callback = _section_cb
                result = await svc.generate_section_subtitles(label, audio_path)
                await connection_manager.broadcast_to_project(
                    project_id, "job_completed",
                    {"job_type": "section_subtitles", "section": label, "result": result},
                )
            except Exception as exc:
                _log.error("Subtitle failed for %s: %s", label, exc)
                await connection_manager.broadcast_to_project(
                    project_id, "job_failed",
                    {"job_type": "section_subtitles", "section": label, "error": str(exc)},
                )
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "all_sections_subtitles",
                 "progress": round((idx + 1) / total * 100),
                 "message": f"Done {idx + 1}/{total} sections"},
            )

        await connection_manager.broadcast_to_project(
            project_id, "job_completed",
            {"job_type": "all_sections_subtitles", "sections": pending},
        )

    background_tasks.add_task(run)
    return {
        "status": "started",
        "message": f"Subtitle generation started for {len(pending)} section(s)",
        "labels": pending,
    }


@router.delete("/{project_id}/sections/{label}/subtitles")
async def delete_section_subtitles(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete the generated SRT file for one AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    sub_dir = project_dir / "subtitles" / "sections" / label
    deleted = 0
    if sub_dir.exists():
        for f in sub_dir.glob("*.srt"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted, "label": label}


@router.delete("/{project_id}/sections/subtitles/all")
async def delete_all_section_subtitles(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete all generated SRT files across every AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    sections_subs = project_dir / "subtitles" / "sections"
    deleted = 0
    if sections_subs.exists():
        for f in sections_subs.rglob("*.srt"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted}


@router.post("/{project_id}/sections/{label}/voice")
async def generate_section_voice(
    project_id: str,
    label: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate Piper TTS narration for one AI News section.

    Source priority:
      1. input/sections/{label}/scenes.json  — per-scene WAV files
      2. script.md [NARRATOR] block          — single WAV for the whole section

    Output:
      audio/sections/{label}/scene_NNN.wav
      audio/sections/{label}/narration.wav
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    piper_settings = await settings_repo.get_piper_settings()
    if not piper_settings.executable:
        raise HTTPException(status_code=400, detail="Piper TTS not configured. Go to Settings → Voice.")

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    project_language = project.language or "en"

    # Determine narration source
    section_scenes_path = project_dir / "input" / "sections" / label / "scenes.json"
    script_path         = project_dir / "input" / "script.md"

    if not section_scenes_path.exists() and not script_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"No source found for section '{label}' — generate section content or script first.",
        )

    # Pre-read script narrator text (fallback if scenes.json is missing)
    script_narrator_text = ""
    if not section_scenes_path.exists() and script_path.exists():
        script_text          = script_path.read_text(encoding="utf-8")
        script_narrator_text = _extract_section_narrator_text(script_text, label)
        if not script_narrator_text:
            raise HTTPException(
                status_code=400,
                detail=f"Section '{label}' not found in script.md and no scenes.json exists.",
            )

    async def progress_cb(progress: float, message: str, data: dict) -> None:
        await connection_manager.broadcast_to_project(
            project_id, "job_progress",
            {"job_type": "section_voice", "section": label,
             "progress": progress, "message": message, **data},
        )

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_voice", "section": label,
                 "progress": 0, "message": f"Generating voice for section '{label}'…"},
            )
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
                from app.services.voice_service import VoiceGenerationService
                from app.services.piper_model_manager import ensure_model
                resolved_model = await ensure_model(project_language, piper_settings.model_path, progress_cb)
                svc = VoiceGenerationService(
                    project_id=project_id,
                    project_dir=project_dir,
                    piper_executable=piper_settings.executable,
                    model_path=resolved_model,
                    speed=piper_settings.speed,
                    progress_callback=progress_cb,
                )
            result = await svc.generate_section_voice(
                section_label=label,
                section_scenes_path=section_scenes_path if section_scenes_path.exists() else None,
                section_script_text=script_narrator_text,
            )
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "section_voice", "section": label, "result": result},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "section_voice", "section": label, "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {
        "status": "started",
        "message": f"Voice generation started for section '{label}'",
    }


_SECTION_LABEL_ORDER = ["intro"] + [f"story_{i:02d}" for i in range(1, 11)] + ["outro"]


@router.post("/{project_id}/sections/voice/generate-missing")
async def generate_missing_sections_voice(
    project_id: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate Piper TTS voice for all sections that are missing audio, one at a time.

    Runs sections sequentially to avoid overloading the CPU with concurrent
    Piper subprocesses.  Broadcasts job_progress / job_completed per section
    using the same 'section_voice' job_type the frontend already listens to.
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    piper_settings = await settings_repo.get_piper_settings()
    if not piper_settings.executable:
        raise HTTPException(status_code=400, detail="Piper TTS not configured. Go to Settings → Voice.")

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    project_language = project.language or "en"
    sections_input = project_dir / "input" / "sections"
    if not sections_input.exists():
        raise HTTPException(status_code=400, detail="No section content — generate sections first.")

    # Identify pending sections (have scenes.json, no scene WAVs yet)
    pending = [
        lbl for lbl in _SECTION_LABEL_ORDER
        if (sections_input / lbl / "scenes.json").exists()
        and not any((project_dir / "audio" / "sections" / lbl).glob("scene_*.wav"))
    ]
    if not pending:
        return {"status": "nothing_to_do", "message": "All sections already have voice", "labels": []}

    async def run() -> None:
        from app.services.voice_service import VoiceGenerationService

        _log = logging.getLogger(__name__)
        tts_engine = await settings_repo.get_by_key("tts.engine") or "piper"

        # ── Google TTS: no batch API — run sequentially per section ──────────
        if tts_engine == "google":
            from app.services.google_tts_service import GoogleTTSService
            gtts = await settings_repo.get_google_tts_settings()
            if not gtts.api_key:
                await connection_manager.broadcast_to_project(
                    project_id, "job_failed",
                    {"job_type": "all_sections_voice",
                     "error": "Google TTS API key not configured — open Settings → Voice."},
                )
                return
            total = len(pending)
            for idx, label in enumerate(pending):
                try:
                    svc = GoogleTTSService(
                        project_id=project_id,
                        project_dir=project_dir,
                        api_key=gtts.api_key,
                        voice_name=gtts.voice_name,
                        language_code=gtts.language_code,
                        speaking_rate=gtts.speaking_rate,
                        project_language=project_language,
                    )
                    result = await svc.generate_section_voice(
                        section_label=label,
                        section_scenes_path=sections_input / label / "scenes.json",
                    )
                    await connection_manager.broadcast_to_project(
                        project_id, "job_completed",
                        {"job_type": "section_voice", "section": label, "result": result},
                    )
                except Exception as e:
                    await connection_manager.broadcast_to_project(
                        project_id, "job_failed",
                        {"job_type": "section_voice", "section": label, "error": str(e)},
                    )
                await connection_manager.broadcast_to_project(
                    project_id, "job_progress",
                    {"job_type": "all_sections_voice",
                     "progress": round((idx + 1) / total * 100),
                     "message": f"Done {idx + 1}/{total} sections"},
                )
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "all_sections_voice", "sections": pending},
            )
            return

        # ── Phase 1: collect all pending utterances across sections ──────────
        # Flat list in section order: (label, chunk_id, dest_path, text)
        all_items: List[tuple] = []

        for label in pending:
            scenes_path = sections_input / label / "scenes.json"
            sec_audio   = project_dir / "audio" / "sections" / label
            sec_audio.mkdir(parents=True, exist_ok=True)
            try:
                data = json.loads(scenes_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            raw = data if isinstance(data, list) else data.get("scenes", [])
            for i, s in enumerate(raw):
                text = s.get("narration", "").strip()
                if not text:
                    continue
                chunk_id = s.get("scene_id", i + 1)
                dest = sec_audio / f"scene_{int(chunk_id):03d}.wav"
                if dest.exists() and dest.stat().st_size > 0:
                    continue  # already generated (resume)
                all_items.append((label, chunk_id, dest, text))

        # ── Phase 2: ONE Piper process for everything (fast path) ────────────
        from app.services.piper_model_manager import ensure_model
        resolved_model = await ensure_model(project_language, piper_settings.model_path)
        batch_ok = False
        if all_items:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "all_sections_voice", "progress": 0,
                 "message": f"Running Piper — {len(all_items)} utterances across {len(pending)} sections…"},
            )
            svc = VoiceGenerationService(
                project_id=project_id,
                project_dir=project_dir,
                piper_executable=piper_settings.executable,
                model_path=resolved_model,
                speed=piper_settings.speed,
            )
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    wav_paths = await svc._run_piper_batch(
                        [item[3] for item in all_items], Path(tmp_dir)
                    )
                    for i, (_lbl, _cid, dest, _) in enumerate(all_items):
                        if i < len(wav_paths):
                            shutil.copy2(wav_paths[i], dest)
                batch_ok = True
            except Exception as exc:
                _log.error("Voice batch failed (%s) — falling back to sequential", exc)

        # ── Phase 3: fallback sequential if batch failed ─────────────────────
        if all_items and not batch_ok:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "all_sections_voice", "progress": 0,
                 "message": "Batch failed — generating section by section…"},
            )
            total = len(pending)
            for idx, label in enumerate(pending):
                try:
                    svc_fb = VoiceGenerationService(
                        project_id=project_id,
                        project_dir=project_dir,
                        piper_executable=piper_settings.executable,
                        model_path=resolved_model,
                        speed=piper_settings.speed,
                    )
                    result = await svc_fb.generate_section_voice(
                        section_label=label,
                        section_scenes_path=sections_input / label / "scenes.json",
                    )
                    await connection_manager.broadcast_to_project(
                        project_id, "job_completed",
                        {"job_type": "section_voice", "section": label, "result": result},
                    )
                except Exception as e:
                    await connection_manager.broadcast_to_project(
                        project_id, "job_failed",
                        {"job_type": "section_voice", "section": label, "error": str(e)},
                    )
                await connection_manager.broadcast_to_project(
                    project_id, "job_progress",
                    {"job_type": "all_sections_voice",
                     "progress": round((idx + 1) / total * 100),
                     "message": f"Done {idx + 1}/{total} sections"},
                )
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "all_sections_voice", "sections": pending},
            )
            return

        # ── Phase 4: FFmpeg concat per section + broadcast completion ─────────
        total = len(pending)
        for idx, label in enumerate(pending):
            sec_audio = project_dir / "audio" / "sections" / label
            # Glob ALL scene WAVs that now exist (batch-written + any resumed)
            wavs = sorted(
                [f for f in sec_audio.glob("scene_*.wav") if f.stat().st_size > 0],
                key=lambda p: int(p.stem.rsplit("_", 1)[-1]),
            )
            if wavs:
                file_list = sec_audio / "file_list.txt"
                file_list.write_text(
                    "\n".join(f"file '{w.as_posix()}'" for w in wavs),
                    encoding="utf-8",
                )
                merged = sec_audio / "narration.wav"
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(file_list), "-c", "copy", str(merged),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr_c = await asyncio.wait_for(proc.communicate(), timeout=120.0)
                    if proc.returncode != 0:
                        _log.error(
                            "FFmpeg narration concat failed for section '%s': %s",
                            label, stderr_c.decode(errors="replace")[-500:],
                        )
                except Exception as e:
                    _log.warning("FFmpeg concat failed for %s: %s", label, e)

            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "section_voice", "section": label,
                 "result": {"label": label, "generated": len(wavs)}},
            )
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "all_sections_voice",
                 "progress": round((idx + 1) / total * 100),
                 "message": f"Done {idx + 1}/{total} sections"},
            )

        await connection_manager.broadcast_to_project(
            project_id, "job_completed",
            {"job_type": "all_sections_voice", "sections": pending},
        )

    background_tasks.add_task(run)
    return {
        "status": "started",
        "message": f"Voice generation started for {len(pending)} section(s)",
        "labels": pending,
    }


@router.delete("/{project_id}/sections/{label}/voice")
async def delete_section_voice(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete all generated audio files for one AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    audio_dir = project_dir / "audio" / "sections" / label
    deleted = 0
    if audio_dir.exists():
        for f in audio_dir.glob("*.wav"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted, "label": label}


@router.delete("/{project_id}/sections/voice/all")
async def delete_all_section_voice(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete all generated audio files across every AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    sections_audio = project_dir / "audio" / "sections"
    deleted = 0
    if sections_audio.exists():
        for f in sections_audio.rglob("*.wav"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted}


@router.get("/{project_id}/clips/{label}")
async def get_section_clip(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Serve an individual section clip video file (intro, agenda, story_01 … story_10, outro)."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    clip_path = project_dir / "output" / "clips_ai_news" / f"{label}.mp4"
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail=f"Clip '{label}' not found")

    return FileResponse(
        str(clip_path),
        media_type="video/mp4",
        filename=f"{label}.mp4",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{project_id}/sections/{label}/short")
async def generate_section_short(
    project_id: str,
    label: str,
    background_tasks: BackgroundTasks,
    options: ShortOptions = Body(default_factory=ShortOptions),
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate a 9:16 vertical short video for one AI News section.

    Uses:
      audio/sections/{label}/narration.wav   (required)
      images/sections/{label}/scene_NNN.png  (if available)
      subtitles/sections/{label}/subtitles.srt (if available — burned in)

    Optional body: { narrator_text, logo_path }
    Output: output/ai_news_shorts/{label}.mp4
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    audio_path = project_dir / "audio" / "sections" / label / "narration.wav"
    if not audio_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"narration.wav not found for section '{label}'. Generate voice first.",
        )

    # Read section title from the script if available
    title = label.replace("_", " ").title()
    script_path = project_dir / "input" / "script.md"
    if script_path.exists():
        try:
            script = script_path.read_text(encoding="utf-8")
            sections_parsed = AiNewsSectionService.parse_script_sections(script)
            matched = next((s for s in sections_parsed if s["label"] == label), None)
            if matched:
                title = matched["title"]
        except Exception:
            pass

    # Resolve optional logo path
    logo_resolved: Optional[Path] = None
    if options.logo_path:
        candidate = Path(options.logo_path)
        if not candidate.is_absolute():
            candidate = project_dir / "input" / candidate
        if candidate.exists():
            logo_resolved = candidate

    # Auto-detect logo.png / logo.jpg in project input if not specified but exists
    if logo_resolved is None and options.logo_path is None:
        for _logo_name in ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp"):
            _c = project_dir / "input" / _logo_name
            if _c.exists():
                logo_resolved = _c
                break

    narrator_text = options.narrator_text

    video_settings = await settings_repo.get_video_settings()
    narrator_clips_dir = video_settings.narrator_clips_dir or ""

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_short", "section": label,
                 "progress": 0, "message": f"Generating 9:16 short for '{label}'…"},
            )
            from app.services.shorts_service import AiNewsShortsService
            svc = AiNewsShortsService(project_id=project_id, project_dir=project_dir,
                                      narrator_clips_dir=narrator_clips_dir)
            result = await svc.generate_section_short(
                label,
                title=title,
                narrator_text=narrator_text,
                logo_path=logo_resolved,
            )
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "section_short", "section": label, "result": result},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "section_short", "section": label, "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": f"Short generation started for section '{label}'"}


@router.get("/{project_id}/shorts/{label}")
async def get_section_short_video(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Serve the 9:16 short video for a section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    short_path = project_dir / "output" / "ai_news_shorts" / f"{label}.mp4"
    if not short_path.exists():
        raise HTTPException(status_code=404, detail=f"Short '{label}' not found")

    return FileResponse(
        str(short_path),
        media_type="video/mp4",
        filename=f"{label}_short.mp4",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/{project_id}/sections/{label}/short")
async def delete_section_short(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete the generated 9:16 short video for one AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    short_path = project_dir / "output" / "ai_news_shorts" / f"{label}.mp4"
    deleted = 0
    if short_path.exists():
        short_path.unlink()
        deleted = 1

    return {"status": "deleted", "deleted_files": deleted, "label": label}


@router.delete("/{project_id}/sections/shorts/all")
async def delete_all_section_shorts(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete all generated 9:16 short videos across every AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    shorts_dir = project_dir / "output" / "ai_news_shorts"
    deleted = 0
    if shorts_dir.exists():
        for f in shorts_dir.glob("*.mp4"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted}


@router.post("/{project_id}/sections/{label}/clip/regenerate")
async def regenerate_section_clip(
    project_id: str,
    label: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Re-generate the 16:9 clip for one section from its images + narration."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    audio_path = project_dir / "audio" / "sections" / label / "narration.wav"
    if label != "agenda" and not audio_path.exists():
        raise HTTPException(status_code=400, detail=f"narration.wav not found for '{label}'.")

    title = label.replace("_", " ").title()
    script_path = project_dir / "input" / "script.md"
    if script_path.exists():
        try:
            sections_parsed = AiNewsSectionService.parse_script_sections(
                script_path.read_text(encoding="utf-8")
            )
            matched = next((s for s in sections_parsed if s["label"] == label), None)
            if matched:
                title = matched["title"]
        except Exception:
            pass

    async def run() -> None:
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "section_clip", "section": label, "progress": 0,
                 "message": f"Re-generating clip for '{label}'…"},
            )
            from app.services.shorts_service import AiNewsClipService
            svc = AiNewsClipService(project_id=project_id, project_dir=project_dir)
            result = await svc.regenerate_section_clip(label, title=title)
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "section_clip", "section": label, "result": result},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "section_clip", "section": label, "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": f"Clip regeneration started for section '{label}'"}


@router.post("/{project_id}/sections/{label}/clip/upload")
async def upload_section_clip(
    project_id: str,
    label: str,
    file: UploadFile = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Replace the 16:9 clip for one section with an uploaded MP4."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    out_dir = project_dir / "output" / "clips_ai_news"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{label}.mp4"
    content = await file.read()
    dest.write_bytes(content)
    return {"status": "uploaded", "label": label, "path": str(dest)}


@router.post("/{project_id}/sections/{label}/short/upload")
async def upload_section_short(
    project_id: str,
    label: str,
    file: UploadFile = File(...),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Replace the 9:16 short for one section with an uploaded MP4."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    out_dir = project_dir / "output" / "ai_news_shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{label}.mp4"
    content = await file.read()
    dest.write_bytes(content)
    return {"status": "uploaded", "label": label, "path": str(dest)}


@router.delete("/{project_id}/sections/clips/all")
async def delete_all_section_clips(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete all generated 16:9 clips across every AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    clips_dir = project_dir / "output" / "clips_ai_news"
    deleted = 0
    if clips_dir.exists():
        for f in clips_dir.glob("*.mp4"):
            f.unlink()
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted}


@router.delete("/{project_id}/sections/{label}/clip")
async def delete_section_clip(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete the 16:9 clip for one AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    clip_path = project_dir / "output" / "clips_ai_news" / f"{label}.mp4"
    deleted = 0
    if clip_path.exists():
        clip_path.unlink()
        deleted = 1

    return {"status": "deleted", "deleted_files": deleted, "label": label}


# ---------------------------------------------------------------------------
# LTX video clip generation (Image → LTX-Video via ComfyUI per section)
# ---------------------------------------------------------------------------

_COMFYUI_URL = "http://localhost:8188"
_ltx_tasks: dict = {}


@router.get("/ltx/status")
async def ltx_status():
    """Check whether ComfyUI is running at port 8188 (needed for LTX clip generation)."""
    import httpx as _httpx

    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_COMFYUI_URL}/system_stats")
            if r.status_code == 200:
                return {"online": True, "url": _COMFYUI_URL, "mode": "comfyui"}
    except Exception as exc:
        return {"online": False, "url": _COMFYUI_URL, "error": str(exc)}

    return {"online": False, "url": _COMFYUI_URL, "error": "unexpected status"}


class LtxSectionBody(BaseModel):
    use_ken_burns: bool = False


@router.get("/{project_id}/ltx/diagnose")
async def diagnose_ltx(
    project_id: str,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Check ComfyUI availability + required LTX nodes + model files."""
    import httpx as _httpx

    flux_settings = await settings_repo.get_flux_settings()
    comfy_url = (flux_settings.comfyui_url or "http://127.0.0.1:8188").rstrip("/")

    result: dict = {"comfy_url": comfy_url, "nodes": {}, "models": {}, "errors": []}

    REQUIRED_NODES = [
        "CheckpointLoaderSimple", "CLIPLoader", "CLIPTextEncode", "LoadImage",
        "LTXVImgToVideo", "LTXVConditioning", "ModelSamplingLTXV", "LTXVScheduler",
        "KSamplerSelect", "RandomNoise", "CFGGuider", "SamplerCustomAdvanced",
        "VAEDecode", "VHS_VideoCombine",
    ]
    REQUIRED_MODELS = {
        "checkpoints": "ltxv-2b-0.9.8-distilled-fp8.safetensors",
        "clip": "t5xxl_fp8_e4m3fn.safetensors",
    }

    try:
        async with _httpx.AsyncClient(timeout=10.0) as client:
            # 1. Check object_info (all available nodes)
            r = await client.get(f"{comfy_url}/object_info")
            r.raise_for_status()
            obj_info = r.json()
            available = set(obj_info.keys())
            for node in REQUIRED_NODES:
                result["nodes"][node] = node in available
                if node not in available:
                    result["errors"].append(f"Missing node: {node}")

            # 2. Check model files via /object_info/CheckpointLoaderSimple
            ckpt_info = obj_info.get("CheckpointLoaderSimple", {})
            ckpt_list = (ckpt_info.get("input", {}).get("required", {})
                         .get("ckpt_name", [{}])[0])
            if isinstance(ckpt_list, list):
                result["models"]["checkpoints_available"] = ckpt_list
                result["models"]["ltxv_checkpoint"] = (
                    REQUIRED_MODELS["checkpoints"] in ckpt_list
                )
                if not result["models"]["ltxv_checkpoint"]:
                    result["errors"].append(
                        f"Model not found in checkpoints: {REQUIRED_MODELS['checkpoints']}. "
                        f"Available: {ckpt_list}"
                    )

            clip_info = obj_info.get("CLIPLoader", {})
            clip_list = (clip_info.get("input", {}).get("required", {})
                         .get("clip_name", [{}])[0])
            if isinstance(clip_list, list):
                result["models"]["clips_available"] = clip_list
                result["models"]["t5_encoder"] = (
                    REQUIRED_MODELS["clip"] in clip_list
                )
                if not result["models"]["t5_encoder"]:
                    result["errors"].append(
                        f"T5 encoder not found: {REQUIRED_MODELS['clip']}. "
                        f"Available: {clip_list}"
                    )

            result["status"] = "ok" if not result["errors"] else "missing_dependencies"
    except Exception as exc:
        result["status"] = "comfyui_unreachable"
        result["errors"].append(str(exc))

    return result


@router.post("/{project_id}/sections/{label}/ltx")
async def generate_section_ltx(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate LTX-Video clips for all scenes in one section via ComfyUI.

    Clips output to clips/sections/{label}/scene_NNN.mp4 (video-only).
    Skips scenes that already have a clip.
    """
    import asyncio as _asyncio

    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )

    images_dir = project_dir / "images" / "sections" / label
    if not images_dir.exists() or not any(images_dir.glob("scene_*.png")):
        raise HTTPException(
            status_code=400,
            detail=f"No scene images found for section '{label}'. Generate images first.",
        )

    task_key = f"{project_id}:{label}"
    existing = _ltx_tasks.get(task_key)
    if existing and not existing.done():
        return {"status": "already_running", "message": f"LTX generation for '{label}' is already in progress"}

    flux_settings = await settings_repo.get_flux_settings()
    comfyui_url = flux_settings.comfyui_url or "http://127.0.0.1:8188"

    async def _progress_cb(pct: float, msg: str, data: dict):
        await connection_manager.broadcast_to_project(project_id, "ltx_progress", {
            "job_type": "section_ltx",
            "section": label,
            "progress": pct,
            "message": msg,
            **(data or {}),
        })

    from app.services.ltx_comfy_service import AiNewsLTXService
    svc = AiNewsLTXService(
        project_id=project_id,
        project_dir=project_dir,
        comfyui_url=comfyui_url,
        progress_callback=_progress_cb,
    )

    async def _run():
        try:
            await connection_manager.broadcast_to_project(project_id, "job_started", {
                "job_type": "section_ltx",
                "section": label,
                "message": f"Starting LTX generation for section '{label}'",
            })
            result = await svc.generate_section(label)
            await connection_manager.broadcast_to_project(project_id, "job_completed", {
                "job_type": "section_ltx",
                "section": label,
                "message": f"LTX generation complete for '{label}': {result['animated']}/{result['total']} clips",
            })
        except _asyncio.CancelledError:
            pass
        except Exception as exc:
            await connection_manager.broadcast_to_project(project_id, "job_failed", {
                "job_type": "section_ltx",
                "section": label,
                "error": str(exc),
            })

    task = _asyncio.create_task(_run())
    _ltx_tasks[task_key] = task

    return {"status": "started", "message": f"LTX generation started for section '{label}'"}


@router.post("/{project_id}/sections/ltx/generate-all")
async def generate_all_sections_ltx(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Generate LTX-Video clips for all AI News sections via ComfyUI (narrative order)."""
    import asyncio as _asyncio
    from app.services.ltx_comfy_service import AiNewsLTXService

    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )

    sections_root = project_dir / "images" / "sections"
    if not sections_root.exists():
        raise HTTPException(status_code=400, detail="No section images found. Generate images first.")

    task_key = f"{project_id}:all"
    existing = _ltx_tasks.get(task_key)
    if existing and not existing.done():
        return {"status": "already_running", "message": "All-sections LTX generation is already running"}

    flux_settings = await settings_repo.get_flux_settings()
    comfyui_url = flux_settings.comfyui_url or "http://127.0.0.1:8188"

    async def _all_progress_cb(pct: float, msg: str, data: dict):
        await connection_manager.broadcast_to_project(project_id, "ltx_progress", {
            "job_type": "section_ltx_all",
            "progress": pct,
            "message": msg,
            **(data or {}),
        })

    svc = AiNewsLTXService(
        project_id=project_id,
        project_dir=project_dir,
        comfyui_url=comfyui_url,
        progress_callback=_all_progress_cb,
    )

    async def _run_all():
        try:
            await connection_manager.broadcast_to_project(project_id, "job_started", {
                "job_type": "section_ltx_all",
                "message": "Starting LTX generation for all sections",
            })
            result = await svc.generate_all_sections()
            await connection_manager.broadcast_to_project(project_id, "job_completed", {
                "job_type": "section_ltx_all",
                "message": f"All-sections LTX complete: {result['total_sections']} sections processed",
            })
        except _asyncio.CancelledError:
            pass
        except Exception as exc:
            await connection_manager.broadcast_to_project(project_id, "job_failed", {
                "job_type": "section_ltx_all",
                "error": str(exc),
            })

    task = _asyncio.create_task(_run_all())
    _ltx_tasks[task_key] = task

    return {"status": "started", "message": "LTX generation started for all sections"}


@router.delete("/{project_id}/sections/{label}/ltx")
async def delete_section_ltx(
    project_id: str,
    label: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Delete LTX clips for one AI News section."""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    ltx_dir = project_dir / "clips" / "sections" / label
    deleted = 0
    if ltx_dir.exists():
        for f in ltx_dir.glob("scene_*.mp4"):
            f.unlink(missing_ok=True)
            deleted += 1

    return {"status": "deleted", "deleted_files": deleted, "label": label}


@router.get("/{project_id}/sections/content")
async def get_sections_content(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return text content + media file lists for all AI News sections.

    Used by ContentGenPage, ImageGenPage, VoiceGenPage, and SubtitlePage to
    populate section-divided views.
    """
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    input_dir  = project_dir / "input"
    images_dir = project_dir / "images"
    audio_dir  = project_dir / "audio"
    sub_dir    = project_dir / "subtitles"

    # Parse script.md to get section list with real titles and script text
    script_path = input_dir / "script.md"
    script_text = ""
    parsed_sections: List[Dict[str, Any]] = []
    if script_path.exists():
        script_text = script_path.read_text(encoding="utf-8")
        parsed_sections = AiNewsSectionService.parse_script_sections(script_text)

    # Build a lookup by label so we can merge with the static skeleton
    parsed_by_label: Dict[str, Dict[str, Any]] = {s["label"]: s for s in parsed_sections}

    # Always produce all 12 expected sections in the correct order
    _EXPECTED: List[Dict[str, Any]] = [{"label": "intro", "type": "intro", "num": 1, "title": "Introduction"}]
    for _n in range(1, 11):
        _EXPECTED.append({"label": f"story_{_n:02d}", "type": "story", "num": _n + 1, "title": f"Story {_n}"})
    _EXPECTED.append({"label": "outro", "type": "outro", "num": 12, "title": "Outro"})

    sections: List[Dict[str, Any]] = []
    for stub in _EXPECTED:
        merged = {**stub, **parsed_by_label.get(stub["label"], {})}
        sections.append(merged)

    # ── Auto-split global files into per-section files if needed ─────────────
    # If input/scenes.json or input/image_prompts.txt exist but per-section
    # files are missing, split them now so the UI shows content immediately
    # instead of falling back to raw script text.
    if parsed_sections:
        global_scenes_path  = input_dir / "scenes.json"
        global_prompts_path = input_dir / "image_prompts.txt"

        # Trigger split when ANY section file is missing OR when counts are stale
        # (e.g. global scenes.json was regenerated with different scene counts).
        needs_scene_split = global_scenes_path.exists() and any(
            not (input_dir / "sections" / s["label"] / "scenes.json").exists()
            for s in parsed_sections
        )
        if not needs_scene_split and global_scenes_path.exists():
            try:
                _raw_check: List[Dict[str, Any]] = json.loads(
                    global_scenes_path.read_text(encoding="utf-8")
                )
                _check_split = AiNewsSectionService._split_scenes_by_section(
                    script_text, parsed_sections, _raw_check
                )
                for _sec in parsed_sections:
                    _lbl = _sec["label"]
                    _sf = input_dir / "sections" / _lbl / "scenes.json"
                    if _sf.exists():
                        try:
                            _existing = len(json.loads(_sf.read_text(encoding="utf-8")))
                            if _existing != len(_check_split.get(_lbl, [])):
                                needs_scene_split = True
                                break
                        except Exception:
                            pass
            except Exception:
                pass

        split_by_label: Dict[str, List[Dict[str, Any]]] = {}

        if needs_scene_split and global_scenes_path.exists():
            try:
                raw_global: List[Dict[str, Any]] = json.loads(
                    global_scenes_path.read_text(encoding="utf-8")
                )
                split_by_label = AiNewsSectionService._split_scenes_by_section(
                    script_text, parsed_sections, raw_global
                )
                for sec in parsed_sections:
                    lbl = sec["label"]
                    sec_scenes = split_by_label.get(lbl, [])
                    sec_file = input_dir / "sections" / lbl / "scenes.json"
                    if not sec_scenes:
                        continue
                    # Write if missing; overwrite if existing count doesn't match
                    existing_ok = False
                    if sec_file.exists():
                        try:
                            existing_count = len(json.loads(sec_file.read_text(encoding="utf-8")))
                            existing_ok = (existing_count == len(sec_scenes))
                        except Exception:
                            pass
                    if not existing_ok:
                        sec_file.parent.mkdir(parents=True, exist_ok=True)
                        clean = [{k: v for k, v in s.items() if k != "_orig_id"} for s in sec_scenes]
                        sec_file.write_text(
                            json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8"
                        )
                logging.getLogger(__name__).info(
                    "Auto-split global scenes.json into %d sections", len(split_by_label)
                )
            except Exception as _e:
                logging.getLogger(__name__).warning("Auto-split scenes.json failed: %s", _e)

        needs_prompt_split = global_prompts_path.exists() and any(
            not (input_dir / "sections" / s["label"] / "image_prompts.txt").exists()
            for s in parsed_sections
        )
        # Also resplit prompts when a scenes split just happened (counts may have changed)
        if not needs_prompt_split and split_by_label and global_prompts_path.exists():
            for _sec in parsed_sections:
                _lbl = _sec["label"]
                _pf = input_dir / "sections" / _lbl / "image_prompts.txt"
                if _pf.exists():
                    try:
                        _plines = _pf.read_text(encoding="utf-8").splitlines()
                        _actual = sum(1 for l in _plines if l.strip().upper().startswith("PROMPT:"))
                        if _actual != len(split_by_label.get(_lbl, [])):
                            needs_prompt_split = True
                            break
                    except Exception:
                        pass

        if needs_prompt_split and global_prompts_path.exists():
            # Prefer re-splitting the global scenes.json so _orig_id values come
            # from the actual global scene_id values in that file — not a guessed
            # cumulative offset derived from per-section files (which may have
            # different scene counts if AiNewsSectionService generated them).
            if not split_by_label and global_scenes_path.exists():
                try:
                    raw_global2: List[Dict[str, Any]] = json.loads(
                        global_scenes_path.read_text(encoding="utf-8")
                    )
                    split_by_label = AiNewsSectionService._split_scenes_by_section(
                        script_text, parsed_sections, raw_global2
                    )
                except Exception as _e:
                    logging.getLogger(__name__).warning(
                        "Re-split of global scenes for prompt mapping failed: %s", _e
                    )

            # Last resort: reconstruct _orig_id by cumulative position from per-section files
            if not split_by_label:
                global_offset = 0
                for sec in parsed_sections:
                    lbl = sec["label"]
                    sp = input_dir / "sections" / lbl / "scenes.json"
                    if sp.exists():
                        try:
                            scenes = json.loads(sp.read_text(encoding="utf-8"))
                            for i, s in enumerate(scenes):
                                s["_orig_id"] = global_offset + i + 1
                            split_by_label[lbl] = scenes
                            global_offset += len(scenes)
                        except Exception:
                            pass

            if split_by_label:
                try:
                    global_prompts_text = global_prompts_path.read_text(encoding="utf-8")
                    prompts_map = AiNewsSectionService._split_prompts_by_section(
                        global_prompts_text, split_by_label
                    )
                    for lbl, text in prompts_map.items():
                        pf = input_dir / "sections" / lbl / "image_prompts.txt"
                        if not text:
                            continue
                        # Overwrite if file is missing OR if its prompt count
                        # doesn't match the section's scene count (stale/bad file).
                        expected = len(split_by_label.get(lbl, []))
                        existing_ok = False
                        if pf.exists():
                            existing_lines = pf.read_text(encoding="utf-8").splitlines()
                            actual = sum(1 for l in existing_lines if l.strip().upper().startswith("PROMPT:"))
                            existing_ok = (actual == expected)
                        if not existing_ok:
                            pf.parent.mkdir(parents=True, exist_ok=True)
                            pf.write_text(text, encoding="utf-8")
                    logging.getLogger(__name__).info(
                        "Auto-split global image_prompts.txt into %d sections", len(prompts_map)
                    )
                except Exception as _e:
                    logging.getLogger(__name__).warning("Auto-split image_prompts.txt failed: %s", _e)

    # ── Auto-distribute global images into per-section dirs ──────────────────
    # If images/scene_*.png exist (from standard pipeline) but images/sections/
    # doesn't, copy each image to images/sections/{label}/scene_{local_id}.png
    # so the AI News gallery can display them.  This is a one-time operation.
    global_imgs = list(images_dir.glob("scene_*.png"))
    sections_img_dir = images_dir / "sections"
    if global_imgs and not sections_img_dir.exists() and parsed_sections:
        img_split = split_by_label  # re-use mapping built above if available
        if not img_split and global_scenes_path.exists():
            try:
                _raw = json.loads(global_scenes_path.read_text(encoding="utf-8"))
                img_split = AiNewsSectionService._split_scenes_by_section(
                    script_text, parsed_sections, _raw
                )
            except Exception as _e:
                logging.getLogger(__name__).warning("Image dist: scene split failed: %s", _e)

        if img_split:
            for _lbl, _scenes in img_split.items():
                sec_img_dir = sections_img_dir / _lbl
                for _local_id, _scene in enumerate(_scenes, 1):
                    _orig_id = _scene.get("_orig_id", _local_id)
                    src = images_dir / f"scene_{_orig_id:03d}.png"
                    if src.exists():
                        sec_img_dir.mkdir(parents=True, exist_ok=True)
                        dst = sec_img_dir / f"scene_{_local_id:03d}.png"
                        if not dst.exists():
                            shutil.copy2(src, dst)
            logging.getLogger(__name__).info(
                "Auto-distributed global images into per-section dirs"
            )

    result: List[Dict[str, Any]] = []
    for i, sec in enumerate(sections):
        lbl       = sec["label"]
        sec_input = input_dir  / "sections" / lbl
        sec_imgs  = images_dir / "sections" / lbl
        sec_aud   = audio_dir  / "sections" / lbl
        sec_subs  = sub_dir    / "sections" / lbl

        def _read(p: Path) -> Optional[str]:
            return p.read_text(encoding="utf-8") if p.exists() else None

        image_ids = sorted(
            int(f.stem.rsplit("_", 1)[-1])
            for f in sec_imgs.glob("scene_*.png")
        ) if sec_imgs.exists() else []

        voice_ids = sorted(
            int(f.stem.rsplit("_", 1)[-1])
            for f in sec_aud.glob("scene_*.wav")
        ) if sec_aud.exists() else []

        result.append({
            "label":           lbl,
            "type":            sec["type"],
            "title":           sec["title"],
            "order":           i + 1,
            "scenes_json":     _read(sec_input / "scenes.json"),
            "image_prompts":   _read(sec_input / "image_prompts.txt"),
            "subtitle_srt":    _read(sec_subs  / "subtitles.srt"),
            "image_scene_ids": image_ids,
            "voice_scene_ids": voice_ids,
            "has_narration":   (sec_aud / "narration.wav").exists(),
            "script_text":     sec.get("script"),   # raw section script from script.md
        })

    return result


@router.get("/{project_id}/sections/{label}/media/image/{scene_id}")
async def get_section_image(
    project_id: str,
    label: str,
    scene_id: int,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Serve images/sections/{label}/scene_{scene_id:03d}.png"""
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    img_path = project_dir / "images" / "sections" / label / f"scene_{scene_id:03d}.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Section image not found: {label}/scene_{scene_id:03d}.png")

    return FileResponse(str(img_path), media_type="image/png",
                        headers={"Cache-Control": "max-age=3600"})


@router.get("/{project_id}/sections/{label}/media/audio/{filename}")
async def get_section_audio(
    project_id: str,
    label: str,
    filename: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Serve audio/sections/{label}/{filename} (scene_NNN.wav or narration.wav)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = (
        Path(project.project_dir) if project.project_dir else Path(f"projects/{project_id}")
    )
    audio_path = project_dir / "audio" / "sections" / label / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Section audio not found: {label}/{filename}")

    media_type = "audio/wav" if filename.endswith(".wav") else "audio/mpeg"
    return FileResponse(str(audio_path), media_type=media_type,
                        headers={"Cache-Control": "max-age=3600"})


@router.get("/{project_id}/state")
async def get_ai_news_state(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """Return all previously-generated content files for state restoration."""
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
        "script":        read("script.md"),
        "scenes":        read("scenes.json"),
        "image_prompts": read("image_prompts.txt"),
        "thumbnail":     read("thumbnail_full.txt"),
        "seo":           read("seo.json"),
    }
