"""
PipelineService — single-click orchestration of the full generation pipeline.

Deep Dive steps (6):
  1. research   — ContentGenerationService: research → script → scenes → prompts → thumbnail → seo
  2. images     — ImageGenerationService (FLUX via ComfyUI)
  3. voice      — VoiceGenerationService / GoogleTTSService
  4. subtitles  — SubtitleGenerationService (Whisper)
  5. thumbnail  — ThumbnailGenerationService (FLUX)
  6. video      — VideoGenerationService (MoviePy)

AI News steps (7):
  1. topics     — AiNewsService.scrape_news_stories()
  2. content    — AiNewsService.generate_all_for_news() + AiNewsSectionService.generate_all_sections()
  3. images     — ImageGenerationService.generate_section_images() per section
  4. voice      — VoiceGenerationService.generate_section_voice() per section
  5. subtitles  — SubtitleGenerationService.generate_section_subtitles() per section
  6. clips_ltx  — AiNewsLTXService.generate_all_sections()
  7. video      — AiNewsClipService + AiNewsShortsService per section
"""
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.events import connection_manager
from app.core.exceptions import ServiceError
from app.services.base import BaseService


DEEP_DIVE_STEPS: List[Tuple[str, str]] = [
    ("research",   "Research & Script Generation"),
    ("images",     "Image Generation (FLUX)"),
    ("voice",      "Voice Generation (TTS)"),
    ("subtitles",  "Subtitle Generation (Whisper)"),
    ("thumbnail",  "Thumbnail Image"),
    ("video",      "Video Render"),
]

AI_NEWS_STEPS: List[Tuple[str, str]] = [
    ("topics",    "Fetch AI News Topics"),
    ("content",   "Content & Section Generation"),
    ("images",    "Section Images (FLUX)"),
    ("voice",     "Section Voice (TTS)"),
    ("subtitles", "Section Subtitles (Whisper)"),
    ("clips_ltx", "LTX-Video Clip Animation"),
    ("video",     "Section Video Render"),
]


class PipelineService(BaseService):
    """Runs the full generation pipeline for Deep Dive or AI News projects."""

    service_name = "pipeline"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        project_type: str,
        project_language: str,
        gemini_settings: Any,
        flux_settings: Any,
        piper_settings: Any,
        video_settings: Any,
        whisper_model: str,
        whisper_device: str,
        tts_engine: str,
        google_tts_settings: Any,
        channel_name: str,
        comfyui_url: str,
        progress_callback: Optional[Callable] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback)
        self.project_type     = project_type
        self.project_language = project_language
        self.gemini           = gemini_settings
        self.flux             = flux_settings
        self.piper            = piper_settings
        self.video            = video_settings
        self.whisper_model    = whisper_model
        self.whisper_device   = whisper_device
        self.tts_engine       = tts_engine
        self.google_tts       = google_tts_settings
        self.channel_name     = channel_name
        self.comfyui_url      = comfyui_url

    # ── Entry point ────────────────────────────────────────────────────────────

    async def execute(self) -> Dict[str, Any]:
        steps = DEEP_DIVE_STEPS if self.project_type != "ai_news" else AI_NEWS_STEPS
        return await self._run_steps(steps)

    # ── Step orchestrator ──────────────────────────────────────────────────────

    async def _run_steps(self, steps: List[Tuple[str, str]]) -> Dict[str, Any]:
        total = len(steps)
        t0    = time.monotonic()

        for i, (step_name, step_label) in enumerate(steps):
            await self.check_cancelled()

            await self._broadcast("pipeline_step_started", {
                "step_name": step_name, "step_label": step_label,
                "step_index": i, "total_steps": total,
            })

            base_pct  = (i / total) * 100.0
            step_pct  = 100.0 / total

            async def sub_cb(
                p: float, msg: str, data: dict,
                _b: float = base_pct, _w: float = step_pct,
                _n: str = step_name, _i: int = i,
            ) -> None:
                await self.report_progress(
                    _b + p * _w / 100.0, msg,
                    {"pipeline_step": _n, "step_index": _i, "total_steps": total, **data},
                )

            try:
                await self._dispatch(step_name, sub_cb)
            except Exception as exc:
                await self._broadcast("pipeline_step_failed", {
                    "step_name": step_name, "step_label": step_label,
                    "step_index": i, "total_steps": total, "error": str(exc),
                })
                raise ServiceError(
                    self.service_name, f"Step '{step_label}' failed: {exc}"
                ) from exc

            await self._broadcast("pipeline_step_completed", {
                "step_name": step_name, "step_label": step_label,
                "step_index": i, "total_steps": total,
            })

        duration = round(time.monotonic() - t0)
        await self._broadcast("pipeline_completed", {
            "total_steps": total, "duration_s": duration,
        })
        return {"status": "completed", "total_steps": total, "duration_s": duration}

    # ── Dispatcher ─────────────────────────────────────────────────────────────

    async def _dispatch(self, step_name: str, sub_cb: Callable) -> None:
        if self.project_type != "ai_news":
            dispatch = {
                "research":  self._dd_research,
                "images":    self._dd_images,
                "voice":     self._dd_voice,
                "subtitles": self._dd_subtitles,
                "thumbnail": self._dd_thumbnail,
                "video":     self._dd_video,
            }
        else:
            dispatch = {
                "topics":    self._an_topics,
                "content":   self._an_content,
                "images":    self._an_images,
                "voice":     self._an_voice,
                "subtitles": self._an_subtitles,
                "clips_ltx": self._an_ltx,
                "video":     self._an_video,
            }
        fn = dispatch.get(step_name)
        if fn is None:
            raise ServiceError(self.service_name, f"Unknown step: {step_name}")
        await fn(sub_cb)

    # ─────────────────────────────────────────────────────────────────────────
    # Deep Dive steps
    # ─────────────────────────────────────────────────────────────────────────

    async def _dd_research(self, sub_cb: Callable) -> None:
        """Research + Script → SEO (ContentGenerationService)."""
        from app.services.content_service import ContentGenerationService

        input_dir     = self.project_dir / "input"
        research_path = input_dir / "research.txt"
        trends_path   = input_dir / "trends.txt"

        research_text = (
            research_path.read_text(encoding="utf-8").strip()
            if research_path.exists() else ""
        )
        topic_text = (
            trends_path.read_text(encoding="utf-8")[:300].strip()
            if trends_path.exists() else self.project_id
        )

        svc = ContentGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            api_key=self.gemini.api_key, pro_model=self.gemini.pro_model,
            script_model=self.gemini.script_model, flash_model=self.gemini.flash_model,
            search_grounding=self.gemini.search_grounding,
            image_backend=self.gemini.image_backend,
            language=self.project_language, channel_name=self.channel_name,
            progress_callback=sub_cb,
        )

        if not research_text:
            await sub_cb(5, "Researching topic…", {})
            research_text = await svc.research_topic(topic_text)

        await svc.generate_all(topic=topic_text, research=research_text)

    async def _dd_images(self, sub_cb: Callable) -> None:
        from app.services.image_service import ImageGenerationService
        svc = ImageGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            comfyui_url=self.comfyui_url,
            flux_settings=self._flux_dict(),
            progress_callback=sub_cb,
        )
        await svc.execute()

    async def _dd_voice(self, sub_cb: Callable) -> None:
        svc = await self._build_voice_svc(sub_cb)
        await svc.execute()

    async def _dd_subtitles(self, sub_cb: Callable) -> None:
        from app.services.subtitle_service import SubtitleGenerationService
        svc = SubtitleGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            whisper_model=self.whisper_model, language=self.project_language,
            device=self.whisper_device, progress_callback=sub_cb,
        )
        await svc.execute()

    async def _dd_thumbnail(self, sub_cb: Callable) -> None:
        from app.services.thumbnail_service import ThumbnailGenerationService
        svc = ThumbnailGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            comfyui_url=self.comfyui_url, flux_settings=self._flux_dict(),
            progress_callback=sub_cb,
        )
        await svc.execute()

    async def _dd_video(self, sub_cb: Callable) -> None:
        from app.services.video_service import VideoGenerationService
        v = self.video
        svc = VideoGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            template=v.template, fps=v.fps, resolution=v.resolution,
            zoom_amount=v.zoom_amount, transition_duration=v.transition_duration,
            video_codec=v.codec, audio_codec=v.audio_codec,
            video_bitrate=v.bitrate, audio_bitrate=v.audio_bitrate,
            narrator_enabled=v.narrator_enabled, narrator_clips_dir=v.narrator_clips_dir,
            narrator_position=v.narrator_position, narrator_width=v.narrator_width,
            narrator_margin=v.narrator_margin, narrator_bottom_margin=v.narrator_bottom_margin,
            narrator_shape=v.narrator_shape,
            logo_path=v.logo_path, logo_opacity=v.logo_opacity,
            logo_scale=v.logo_scale, logo_margin=v.logo_margin,
            burn_subtitles=v.burn_subtitles,
            project_type="deep_dive",
            progress_callback=sub_cb,
        )
        await svc.execute()

    # ─────────────────────────────────────────────────────────────────────────
    # AI News steps
    # ─────────────────────────────────────────────────────────────────────────

    async def _an_topics(self, sub_cb: Callable) -> None:
        topics_path = self.project_dir / "input" / "topics.json"
        if topics_path.exists():
            await sub_cb(100, "Topics already fetched — skipping", {})
            return

        from app.services.ai_news_service import AiNewsService, scrape_rss_news
        try:
            svc = self._build_ai_news_svc(sub_cb)
            stories = await svc.scrape_news_stories(n=10)
        except Exception as exc:
            self.logger.warning("Gemini news scrape failed, falling back to RSS: %s", exc)
            stories = await scrape_rss_news(n=10)

        input_dir = self.project_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        topics_path.write_text(json.dumps(stories, indent=2, ensure_ascii=False), encoding="utf-8")
        await sub_cb(100, f"Fetched {len(stories)} stories", {"story_count": len(stories)})

    async def _an_content(self, sub_cb: Callable) -> None:
        topics_path = self.project_dir / "input" / "topics.json"
        script_path = self.project_dir / "input" / "script.md"

        if not topics_path.exists():
            raise ServiceError(self.service_name, "topics.json not found — Topics step must run first")

        stories = json.loads(topics_path.read_text(encoding="utf-8"))
        stories_data = [{"title": s["title"], "summary": s.get("summary", "")} for s in stories]

        if not script_path.exists():
            svc = self._build_ai_news_svc(sub_cb)
            await svc.generate_all_for_news(stories_data)
        else:
            await sub_cb(50, "Script already exists — skipping to section split", {})

        # Split to per-section files
        from app.services.ai_news_section_service import AiNewsSectionService
        script = script_path.read_text(encoding="utf-8")

        async def sec_cb(p: float, msg: str, data: dict) -> None:
            await sub_cb(50.0 + p * 0.5, msg, data)

        sec_svc = AiNewsSectionService(
            project_id=self.project_id, project_dir=self.project_dir,
            api_key=self.gemini.api_key, pro_model=self.gemini.pro_model,
            script_model=self.gemini.script_model, flash_model=self.gemini.flash_model,
            search_grounding=self.gemini.search_grounding,
            image_backend=self.gemini.image_backend,
            language=self.project_language, channel_name=self.channel_name,
            progress_callback=sec_cb,
        )
        await sec_svc.generate_all_sections(script, image_backend=self.gemini.image_backend)

    async def _an_images(self, sub_cb: Callable) -> None:
        from app.services.image_service import ImageGenerationService
        labels = self._section_labels()
        total  = len(labels)
        flux   = self._flux_dict()

        for i, label in enumerate(labels):
            await self.check_cancelled()
            prompts_path = self.project_dir / "input" / "sections" / label / "image_prompts.txt"
            if not prompts_path.exists():
                continue

            async def img_cb(p: float, msg: str, data: dict, _i: int = i) -> None:
                await sub_cb(_i / total * 100 + p / total, msg, {"section": label, **data})

            svc = ImageGenerationService(
                project_id=self.project_id, project_dir=self.project_dir,
                comfyui_url=self.comfyui_url, flux_settings=flux,
                progress_callback=img_cb,
            )
            await svc.generate_section_images(label, prompts_path)

    async def _an_voice(self, sub_cb: Callable) -> None:
        labels = self._section_labels()
        total  = len(labels)

        for i, label in enumerate(labels):
            await self.check_cancelled()
            scenes_path = self.project_dir / "input" / "sections" / label / "scenes.json"
            if not scenes_path.exists():
                continue

            async def voice_cb(p: float, msg: str, data: dict, _i: int = i) -> None:
                await sub_cb(_i / total * 100 + p / total, msg, {"section": label, **data})

            svc = await self._build_voice_svc(voice_cb)
            await svc.generate_section_voice(
                section_label=label,
                section_scenes_path=scenes_path,
                section_script_text="",
            )

    async def _an_subtitles(self, sub_cb: Callable) -> None:
        from app.services.subtitle_service import SubtitleGenerationService
        labels = self._section_labels()
        total  = len(labels)

        svc = SubtitleGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            whisper_model=self.whisper_model, language=self.project_language,
            device=self.whisper_device,
        )

        for i, label in enumerate(labels):
            await self.check_cancelled()
            audio_path = self.project_dir / "audio" / "sections" / label / "narration.wav"
            srt_path   = self.project_dir / "subtitles" / "sections" / label / "subtitles.srt"
            if not audio_path.exists() or srt_path.exists():
                continue

            async def sub_cb2(p: float, msg: str, data: dict, _i: int = i) -> None:
                await sub_cb(_i / total * 100 + p / total, msg, {"section": label, **data})

            svc.progress_callback = sub_cb2
            await svc.generate_section_subtitles(label, audio_path)

    async def _an_ltx(self, sub_cb: Callable) -> None:
        from app.services.ltx_comfy_service import AiNewsLTXService
        svc = AiNewsLTXService(
            project_id=self.project_id, project_dir=self.project_dir,
            comfyui_url=self.comfyui_url, progress_callback=sub_cb,
        )
        await svc.generate_all_sections()

    async def _an_video(self, sub_cb: Callable) -> None:
        from app.services.shorts_service import AiNewsClipService, AiNewsShortsService
        from app.services.ai_news_section_service import AiNewsSectionService

        labels = self._section_labels()
        total  = len(labels)

        # Parse section titles from script
        script_path    = self.project_dir / "input" / "script.md"
        section_titles: Dict[str, str] = {}
        if script_path.exists():
            try:
                parsed = AiNewsSectionService.parse_script_sections(
                    script_path.read_text(encoding="utf-8")
                )
                section_titles = {s["label"]: s["title"] for s in parsed}
            except Exception:
                pass

        clip_svc  = AiNewsClipService(project_id=self.project_id, project_dir=self.project_dir)
        short_svc = AiNewsShortsService(
            project_id=self.project_id, project_dir=self.project_dir,
            narrator_clips_dir=self.video.narrator_clips_dir or "",
        )

        for i, label in enumerate(labels):
            await self.check_cancelled()
            audio_path = self.project_dir / "audio" / "sections" / label / "narration.wav"
            if label != "agenda" and not audio_path.exists():
                continue

            title = section_titles.get(label, label.replace("_", " ").title())

            try:
                await clip_svc.regenerate_section_clip(label, title=title)
            except Exception as exc:
                self.logger.warning("Clip failed for %s: %s", label, exc)

            try:
                await short_svc.generate_section_short(label, title=title)
            except Exception as exc:
                self.logger.warning("Short failed for %s: %s", label, exc)

            await sub_cb((i + 1) / total * 100, f"Done: {label}", {"section": label})

    # ─────────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _flux_dict(self) -> Dict[str, Any]:
        return self.flux.model_dump() if hasattr(self.flux, "model_dump") else dict(self.flux)

    def _build_ai_news_svc(self, progress_callback: Callable):
        from app.services.ai_news_service import AiNewsService
        return AiNewsService(
            project_id=self.project_id, project_dir=self.project_dir,
            api_key=self.gemini.api_key, pro_model=self.gemini.pro_model,
            script_model=self.gemini.script_model, flash_model=self.gemini.flash_model,
            search_grounding=self.gemini.search_grounding,
            image_backend=self.gemini.image_backend,
            language=self.project_language, channel_name=self.channel_name,
            progress_callback=progress_callback,
        )

    async def _build_voice_svc(self, progress_callback: Callable):
        if self.tts_engine == "google":
            from app.services.google_tts_service import GoogleTTSService
            return GoogleTTSService(
                project_id=self.project_id, project_dir=self.project_dir,
                api_key=self.google_tts.api_key,
                voice_name=self.google_tts.voice_name,
                language_code=self.google_tts.language_code,
                speaking_rate=self.google_tts.speaking_rate,
                project_language=self.project_language,
                progress_callback=progress_callback,
            )
        from app.services.piper_model_manager import ensure_model
        from app.services.voice_service import VoiceGenerationService
        resolved = await ensure_model(
            self.project_language, self.piper.model_path, progress_callback
        )
        return VoiceGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            piper_executable=self.piper.executable,
            model_path=resolved or self.piper.model_path,
            speed=self.piper.speed,
            progress_callback=progress_callback,
        )

    def _section_labels(self) -> List[str]:
        sections_dir = self.project_dir / "input" / "sections"
        if sections_dir.exists():
            labels = sorted(d.name for d in sections_dir.iterdir() if d.is_dir())
            if labels:
                return labels
        return ["intro"] + [f"story_{i:02d}" for i in range(1, 11)] + ["outro"]

    async def _broadcast(self, event: str, data: dict) -> None:
        await connection_manager.broadcast_to_project(self.project_id, event, data)
