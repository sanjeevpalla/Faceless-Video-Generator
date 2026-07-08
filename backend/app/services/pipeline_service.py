"""
PipelineService — single-click orchestration of the full generation pipeline.

Deep Dive steps (8):
  1. trend_discovery — ContentGenerationService.discover_trend_candidates() + WhatsApp approval gate
  2. research   — ContentGenerationService: research → script → scenes → prompts → thumbnail → seo
  3. images     — ImageGenerationService (FLUX via ComfyUI)
  4. voice      — VoiceGenerationService / GoogleTTSService
  5. subtitles  — SubtitleGenerationService (Whisper)
  6. thumbnail  — ThumbnailGenerationService (FLUX)
  7. video      — VideoGenerationService (MoviePy)
  8. youtube_upload — YouTubeService.upload_video()

AI News steps (8):
  1. topics     — AiNewsService.scrape_news_stories()
  2. content    — AiNewsService.generate_all_for_news() + AiNewsSectionService.generate_all_sections()
  3. images     — ImageGenerationService.generate_section_images() per section
  4. voice      — VoiceGenerationService.generate_section_voice() per section
  5. subtitles  — SubtitleGenerationService.generate_section_subtitles() per section
  6. clips_ltx  — AiNewsLTXService.generate_all_sections()
  7. video      — AiNewsClipService + AiNewsShortsService per section
  8. youtube_upload — YouTubeService.upload_video()
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.events import connection_manager
from app.core.exceptions import ServiceError
from app.services.base import BaseService


class AwaitingExternalInputError(Exception):
    """Raised by a step to pause the pipeline indefinitely pending an external
    event (e.g. a WhatsApp reply). Caught distinctly by _run_steps — this is
    not a failure, so it must never trigger step-retry or a failure alert."""


DEEP_DIVE_STEPS: List[Tuple[str, str]] = [
    ("trend_discovery", "Trend Discovery (WhatsApp Approval)"),
    ("research",   "Research & Script Generation"),
    ("images",     "Image Generation (FLUX)"),
    ("voice",      "Voice Generation (TTS)"),
    ("subtitles",  "Subtitle Generation (Whisper)"),
    ("thumbnail",  "Thumbnail Image"),
    ("video",      "Video Render"),
    ("youtube_upload", "YouTube Upload"),
]

AI_NEWS_STEPS: List[Tuple[str, str]] = [
    ("topics",    "Fetch AI News Topics"),
    ("content",   "Content & Section Generation"),
    ("images",    "Section Images (FLUX)"),
    ("voice",     "Section Voice (TTS)"),
    ("subtitles", "Section Subtitles (Whisper)"),
    ("clips_ltx", "LTX-Video Clip Animation"),
    ("video",     "Section Video Render"),
    ("youtube_upload", "YouTube Upload"),
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
                await self._dispatch_with_retry(step_name, sub_cb)
            except AwaitingExternalInputError:
                await self._broadcast("pipeline_awaiting_input", {
                    "step_name": step_name, "step_label": step_label,
                    "step_index": i, "total_steps": total,
                })
                return {"status": "awaiting_input", "step_name": step_name, "step_label": step_label}
            except Exception as exc:
                await self._broadcast("pipeline_step_failed", {
                    "step_name": step_name, "step_label": step_label,
                    "step_index": i, "total_steps": total, "error": str(exc),
                })
                await self._send_failure_alert(step_label, exc)
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
                "trend_discovery": self._dd_trend_discovery,
                "research":  self._dd_research,
                "images":    self._dd_images,
                "voice":     self._dd_voice,
                "subtitles": self._dd_subtitles,
                "thumbnail": self._dd_thumbnail,
                "video":     self._dd_video,
                "youtube_upload": self._dd_youtube_upload,
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
                "youtube_upload": self._an_youtube_upload,
            }
        fn = dispatch.get(step_name)
        if fn is None:
            raise ServiceError(self.service_name, f"Unknown step: {step_name}")
        await fn(sub_cb)

    async def _dispatch_with_retry(
        self, step_name: str, sub_cb: Callable, max_attempts: int = 3, base_delay: float = 2.0,
    ) -> None:
        """Like BaseService.retry_async, but lets AwaitingExternalInputError pass through
        immediately (unretried) since it's a deliberate pause, not a failure."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            await self.check_cancelled()
            try:
                await self._dispatch(step_name, sub_cb)
                return
            except AwaitingExternalInputError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    self.logger.warning(
                        f"Step '{step_name}' attempt {attempt}/{max_attempts} failed: {exc}. "
                        f"Retrying in {delay:.1f}s…"
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"Step '{step_name}' failed after {max_attempts} attempts: {exc}")
        raise last_exc

    async def _send_failure_alert(self, step_label: str, exc: Exception) -> None:
        """Best-effort WhatsApp failure notification for unattended runs. Never raises."""
        try:
            from app.database import get_session_factory
            from app.repositories.settings_repo import SettingsRepository
            from app.services.whatsapp_service import WhatsAppService

            async with get_session_factory()() as sess:
                wa_settings = await SettingsRepository(sess).get_whatsapp_settings()
            if not wa_settings.enabled:
                return
            wa_svc = WhatsAppService(wa_settings)
            await wa_svc.send_alert_text(
                f"⚠️ Project '{self.project_id}' failed at step '{step_label}': {exc}"
            )
        except Exception as alert_exc:
            self.logger.warning(f"Failed to send WhatsApp failure alert: {alert_exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Deep Dive steps
    # ─────────────────────────────────────────────────────────────────────────

    async def _dd_trend_discovery(self, sub_cb: Callable) -> None:
        """Discover candidate topics and gate on a WhatsApp reply before letting
        the pipeline proceed into `research`. Always raises
        AwaitingExternalInputError until input/trend_selected.json exists —
        the webhook handler (backend/app/api/webhooks.py) writes that file and
        enqueues a fresh pipeline job once the user taps a topic."""
        input_dir = self.project_dir / "input"
        selected_path = input_dir / "trend_selected.json"
        if selected_path.exists():
            await sub_cb(100, "Topic already selected — skipping", {})
            return

        from app.database import get_session_factory
        from app.repositories.project_repo import ProjectRepository
        from app.repositories.settings_repo import SettingsRepository

        async with get_session_factory()() as sess:
            project = await ProjectRepository(sess).get_by_id(self.project_id)
        wa_state = ((project.resume_state or {}).get("whatsapp") or {}) if project else {}

        if wa_state.get("status") != "awaiting_whatsapp_reply":
            from app.services.content_service import ContentGenerationService
            from app.services.whatsapp_service import WhatsAppService

            await sub_cb(5, "Discovering trend candidates…", {})
            svc = ContentGenerationService(
                project_id=self.project_id, project_dir=self.project_dir,
                api_key=self.gemini.api_key, pro_model=self.gemini.pro_model,
                script_model=self.gemini.script_model, flash_model=self.gemini.flash_model,
                search_grounding=self.gemini.search_grounding,
                image_backend=self.gemini.image_backend,
                language=self.project_language, channel_name=self.channel_name,
                progress_callback=sub_cb,
            )
            candidates = await svc.discover_trend_candidates(n=10)
            (input_dir / "trend_candidates.json").write_text(
                json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            await sub_cb(80, "Sending topics to WhatsApp for approval…", {})
            async with get_session_factory()() as sess:
                wa_settings = await SettingsRepository(sess).get_whatsapp_settings()
                wa_svc = WhatsAppService(wa_settings)
                message_id = await wa_svc.send_topic_list(candidates)
                await ProjectRepository(sess).set_awaiting_whatsapp_reply(
                    self.project_id, candidates, message_id, job_id="",
                )
                await sess.commit()

        await sub_cb(100, "Awaiting WhatsApp reply…", {})
        raise AwaitingExternalInputError(
            f"Awaiting WhatsApp topic selection for project {self.project_id}"
        )

    async def _dd_research(self, sub_cb: Callable) -> None:
        """Research + Script → SEO (ContentGenerationService)."""
        from app.services.content_service import ContentGenerationService

        input_dir     = self.project_dir / "input"
        research_path = input_dir / "research.txt"
        trends_path   = input_dir / "trends.txt"
        selected_path = input_dir / "trend_selected.json"

        research_text = (
            research_path.read_text(encoding="utf-8").strip()
            if research_path.exists() else ""
        )
        if selected_path.exists():
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
            topic_text = selected.get("title") or self.project_id
        elif trends_path.exists():
            topic_text = trends_path.read_text(encoding="utf-8")[:300].strip()
        else:
            topic_text = self.project_id

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

    async def _dd_youtube_upload(self, sub_cb: Callable) -> None:
        video_path = self.project_dir / "output" / "video_final.mp4"
        thumbnail_path = self.project_dir / "output" / "thumbnail" / "thumbnail.png"
        await self._youtube_upload_common(sub_cb, video_path, thumbnail_path)

    # ─────────────────────────────────────────────────────────────────────────
    # AI News steps
    # ─────────────────────────────────────────────────────────────────────────

    async def _an_topics(self, sub_cb: Callable) -> None:
        topics_path = self.project_dir / "input" / "topics.json"
        if topics_path.exists():
            await sub_cb(100, "Topics already fetched — skipping", {})
            return

        from app.services.ai_news_service import AiNewsService, get_recent_story_titles, scrape_rss_news
        try:
            svc = self._build_ai_news_svc(sub_cb)
            stories = await svc.scrape_news_stories(n=10)
        except Exception as exc:
            self.logger.warning("Gemini news scrape failed, falling back to RSS: %s", exc)
            exclude_titles = get_recent_story_titles(exclude_dir=self.project_dir)
            stories = await scrape_rss_news(n=10, exclude_titles=exclude_titles)

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

        clip_svc  = AiNewsClipService(
            project_id=self.project_id, project_dir=self.project_dir,
            language=self.project_language, channel_name=self.channel_name,
        )
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

    async def _an_youtube_upload(self, sub_cb: Callable) -> None:
        """AI News has no single rendered episode video — concatenate the
        per-section clips (output/clips_ai_news/{label}.mp4) into one file
        before uploading."""
        combined_path = self.project_dir / "output" / "ai_news_final.mp4"
        if not combined_path.exists():
            labels = self._section_labels()
            clips_dir = self.project_dir / "output" / "clips_ai_news"
            clip_paths = [clips_dir / f"{label}.mp4" for label in labels if (clips_dir / f"{label}.mp4").exists()]
            if not clip_paths:
                await sub_cb(100, "No AI News clips found — skipping YouTube upload", {})
                return

            await sub_cb(5, "Combining section clips…", {})
            concat_list = self.project_dir / "output" / "_ai_news_concat.txt"
            concat_list.write_text(
                "\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8"
            )
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-c", "copy", str(combined_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0 or not combined_path.exists():
                raise ServiceError(self.service_name, f"ffmpeg concat failed: {stderr.decode(errors='ignore')[-500:]}")

        thumbnail_path = self.project_dir / "output" / "thumbnail" / "thumbnail.png"
        await self._youtube_upload_common(sub_cb, combined_path, thumbnail_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _youtube_upload_common(
        self, sub_cb: Callable, video_path: Path, thumbnail_path: Optional[Path],
    ) -> None:
        video_id_path = self.project_dir / "output" / "youtube_video_id.txt"
        if video_id_path.exists():
            await sub_cb(100, "Already uploaded to YouTube — skipping", {})
            return
        if not video_path.exists():
            raise ServiceError(self.service_name, f"Rendered video not found: {video_path}")

        seo_path = self.project_dir / "input" / "seo.json"
        title, description, tags = self.project_id, "", []
        if seo_path.exists():
            try:
                seo = json.loads(seo_path.read_text(encoding="utf-8"))
                title = seo.get("title") or title
                description = seo.get("description") or ""
                tags = seo.get("tags") or []
            except json.JSONDecodeError:
                pass

        from app.database import get_session_factory
        from app.repositories.settings_repo import SettingsRepository
        from app.services.youtube_service import YouTubeService

        async with get_session_factory()() as sess:
            yt_settings = await SettingsRepository(sess).get_youtube_settings()

        await sub_cb(10, "Uploading to YouTube…", {})
        yt_svc = YouTubeService(yt_settings)
        video_id = await yt_svc.upload_video(
            video_path=video_path, title=title, description=description, tags=tags,
            thumbnail_path=thumbnail_path if thumbnail_path and thumbnail_path.exists() else None,
        )
        video_id_path.write_text(video_id, encoding="utf-8")
        await sub_cb(100, f"Uploaded to YouTube: {video_id}", {"youtube_video_id": video_id})

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
