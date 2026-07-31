"""
PipelineService — single-click orchestration of the full generation pipeline.

Every project uses a single shared Gemini API key (Settings → Gemini AI) for every
language — there is no per-language key mapping. Trend discovery and research run
once, for the primary language only; every other language TRANSLATES the primary
language's already-generated script/scenes/thumbnail-concept/SEO rather than
independently regenerating them with its own Gemini call.

Deep Dive steps (8):
  1. trend_discovery — ContentGenerationService.discover_trend_candidates() + WhatsApp approval gate
                  (primary language only — a topic choice is language-agnostic).
  2. research   — primary language: research → script → scenes → prompts →
                  thumbnail concept → seo (ContentGenerationService.generate_all()).
                  Every additional language: translates the primary language's script,
                  scene narration, thumbnail concept, and seo (ContentGenerationService.
                  translate_language_variant()) — only the scene skeleton (scene_id/
                  duration/image_file/visual_description) is reused from the primary
                  language, so the shared FLUX images stay valid.
  3. images     — ImageGenerationService (FLUX via ComfyUI) — primary language's
                  image_prompts.txt only; shared by every language's video.
  4. voice      — VoiceGenerationService / GoogleTTSService, looped over every language
                  (own TTS API key where configured — unrelated to Gemini).
  5. duration_sync — DurationSyncService pads every language's per-scene WAV with
                  trailing silence to match the longest language for that scene, so
                  every language's rendered video (and total runtime) comes out the
                  same length — see duration_sync_service.py for why this is
                  sufficient without touching video/subtitle rendering code.
  6. subtitles  — SubtitleGenerationService (Whisper), looped over every language.
  7. thumbnail  — ThumbnailGenerationService (FLUX) renders once for the primary
                  language; every additional language reuses that same FLUX
                  background and just overlays its translated title/tags
                  (ThumbnailGenerationService.generate_language_variant()) — no
                  additional FLUX render per language.
  8. video      — VideoGenerationService (MoviePy), looped over every language.
  9. youtube_upload — YouTubeService.upload_video() (primary language).

AI News steps (9):
  1. topics     — AiNewsService.scrape_news_stories() (primary language).
  2. content    — primary language: AiNewsService.generate_all_for_news() +
                  AiNewsSectionService.generate_all_sections() (per-section scenes/
                  prompts). Every additional language: translates the primary
                  language's script, per-section scene narration, thumbnail concept,
                  and seo (_an_extra_language_content) — only the per-section scene
                  skeleton is reused from the primary language, so the shared images
                  stay valid.
  3. images     — ImageGenerationService.generate_section_images() per section —
                  primary language's prompts only; shared by every language's clips.
  4. voice      — VoiceGenerationService.generate_section_voice() per section, looped
                  over every language (own TTS API key where configured — unrelated
                  to Gemini).
  5. duration_sync — DurationSyncService pads every language's per-scene WAV with
                  trailing silence to match the longest language for that scene, so
                  every language's rendered video (and total runtime) comes out the
                  same length — see duration_sync_service.py for why this is
                  sufficient without touching video/subtitle rendering code.
  6. subtitles  — SubtitleGenerationService.generate_section_subtitles() per section,
                  looped over every language.
  7. thumbnail  — ThumbnailGenerationService (FLUX) renders once for the primary
                  language; every additional language reuses that same FLUX
                  background and just overlays its translated title/tags — no
                  additional FLUX render per language.
  8. clips_ltx  — AiNewsLTXService.generate_all_sections() (shared, language-agnostic).
  9. video      — AiNewsClipService per section, looped over every language.
  10. youtube_upload — YouTubeService.upload_video() (primary language).
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
    ("research",   "Research & Script Generation (+ translation for other languages)"),
    ("images",     "Image Generation (FLUX, primary language only)"),
    ("voice",      "Voice Generation (TTS, all languages)"),
    ("duration_sync", "Sync Narration Duration Across Languages"),
    ("subtitles",  "Subtitle Generation (Whisper, all languages)"),
    ("thumbnail",  "Thumbnail Image (shared render + translated overlay)"),
    ("video",      "Video Render (all languages)"),
    ("youtube_upload", "YouTube Upload"),
]

AI_NEWS_STEPS: List[Tuple[str, str]] = [
    ("topics",    "Fetch AI News Topics"),
    ("content",   "Content & Section Generation (+ translation for other languages)"),
    ("images",    "Section Images (FLUX, primary language only)"),
    ("voice",     "Section Voice (TTS, all languages)"),
    ("duration_sync", "Sync Narration Duration Across Languages"),
    ("subtitles", "Section Subtitles (Whisper, all languages)"),
    ("thumbnail", "Thumbnail Image (shared render + translated overlay)"),
    ("clips_ltx", "LTX-Video Clip Animation"),
    ("video",     "Section Video Render (all languages)"),
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
        default_voices: Optional[Dict[str, str]] = None,
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
        self.default_voices   = default_voices or {}

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
                "duration_sync": self._duration_sync,
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
                "duration_sync": self._duration_sync,
                "subtitles": self._an_subtitles,
                "thumbnail": self._an_thumbnail,
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
        """Primary language: Research + Script → SEO (ContentGenerationService).
        Then every additional project.languages entry translates the primary
        language's script/scenes/thumbnail-concept/seo (see
        _dd_translate_extra_languages) — only the scene skeleton is shared."""
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

        async def primary_cb(p: float, msg: str, data: dict) -> None:
            await sub_cb(p * 0.5, msg, data)

        svc = ContentGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            api_key=self.gemini.api_key, pro_model=self.gemini.pro_model,
            script_model=self.gemini.script_model, flash_model=self.gemini.flash_model,
            search_grounding=self.gemini.search_grounding,
            image_backend=self.gemini.image_backend,
            language=self.project_language, channel_name=self.channel_name,
            progress_callback=primary_cb,
        )

        if not research_text:
            await sub_cb(5, "Researching topic…", {})
            research_text = await svc.research_topic(topic_text)

        await svc.generate_all(topic=topic_text, research=research_text)

        await self._dd_translate_extra_languages(sub_cb)

    async def _dd_translate_extra_languages(self, sub_cb: Callable) -> None:
        """Translate the primary language's already-generated script/scenes/
        thumbnail-concept/seo into every other project.languages entry — every
        language shares the single Gemini API key configured in Settings, so
        calls are serialized against each other via one shared lock rather than
        run concurrently against separate per-language keys."""
        from app.database import get_session_factory
        from app.repositories.project_repo import ProjectRepository
        from app.services.content_service import ContentGenerationService

        async with get_session_factory()() as sess:
            project = await ProjectRepository(sess).get_by_id(self.project_id)
        languages = list((project.languages if project else None) or [self.project_language])
        extra_languages = [l for l in languages if l != self.project_language]
        if not extra_languages:
            await sub_cb(100, "No additional languages selected — skipping", {})
            return

        input_dir = self.project_dir / "input"
        scenes_path = input_dir / "scenes.json"
        if not scenes_path.exists():
            raise ServiceError(self.service_name, "scenes.json not found — primary language content must complete first")
        base_scenes_raw = json.loads(scenes_path.read_text(encoding="utf-8"))
        base_scenes = base_scenes_raw if isinstance(base_scenes_raw, list) else base_scenes_raw.get("scenes", [])

        shared_lock = asyncio.Lock()
        total = len(extra_languages)

        async def run_content_phase(idx: int, lang: str) -> Tuple[str, Optional[Exception]]:
            base_pct = 50.0 + idx / total * 50.0

            async def lang_cb(p: float, msg: str, data: dict, _b: float = base_pct, _lang: str = lang) -> None:
                await sub_cb(_b + p / total * 0.5, msg, {"language": _lang, **data})

            lang_content_svc = ContentGenerationService(
                project_id=self.project_id, project_dir=self.project_dir,
                api_key=self.gemini.api_key, pro_model=self.gemini.pro_model,
                script_model=self.gemini.script_model, flash_model=self.gemini.flash_model,
                search_grounding=self.gemini.search_grounding,
                image_backend=self.gemini.image_backend,
                language=self.project_language, channel_name=self.channel_name,
                progress_callback=lang_cb,
            )
            async with shared_lock:
                try:
                    await lang_content_svc.translate_language_variant(lang, base_scenes)
                except Exception as exc:
                    self.logger.warning("Language variant translation failed for '%s': %s", lang, exc)
                    await self._set_lang_progress(lang, "script", {"status": "failed", "error": str(exc)})
                    return lang, exc
                await self._set_lang_progress(lang, "script", {"status": "completed"})
                return lang, None

        await self.check_cancelled()
        await asyncio.gather(*[run_content_phase(i, lang) for i, lang in enumerate(extra_languages)])

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
        """Voice generation for every project.languages entry. Google TTS calls
        run concurrently, bounded by per-language-API-key locks (same pattern as
        content generation); Piper (local, no cloud rate limit) runs fully
        sequential via a shared lock."""
        languages = await self._get_project_languages()
        language_voices = await self._get_language_voices()
        input_dir = self.project_dir / "input"
        total = len(languages)
        voice_key_locks: Dict[str, asyncio.Lock] = {}

        async def run_voice(idx: int, lang: str) -> Tuple[str, Optional[Exception]]:
            is_primary = lang == self.project_language
            base_pct = idx / total * 100.0

            async def lang_cb(p: float, msg: str, data: dict, _b: float = base_pct, _lang: str = lang, _primary: bool = is_primary) -> None:
                extra = {} if _primary else {"language": _lang}
                await sub_cb(_b + p / total, msg, {**extra, **data})

            if self.tts_engine == "google":
                lock_key = self.google_tts.language_api_keys.get(lang) or self.google_tts.api_key or "_google_shared"
            else:
                lock_key = "_piper_shared"
            lock = voice_key_locks.setdefault(lock_key, asyncio.Lock())

            async with lock:
                try:
                    voice_svc = await self._build_voice_svc(
                        lang_cb, language=lang,
                        scenes_path_override=None if is_primary else input_dir / lang / "scenes.json",
                        output_dir_override=None if is_primary else self.project_dir / "audio" / lang,
                        voice_id=self._resolve_voice_id(language_voices, lang),
                    )
                    await voice_svc.execute()
                except Exception as exc:
                    self.logger.warning("Voice generation failed for '%s': %s", lang, exc)
                    if not is_primary:
                        await self._set_lang_progress(lang, "voice", {"status": "failed", "error": str(exc)})
                    return lang, exc
                if not is_primary:
                    await self._set_lang_progress(lang, "voice", {"status": "completed"})
                return lang, None

        await self.check_cancelled()
        await asyncio.gather(*[run_voice(i, lang) for i, lang in enumerate(languages)])

    async def _duration_sync(self, sub_cb: Callable) -> None:
        """Shared by Deep Dive and AI News: pads every language's per-scene WAV
        with trailing silence to match the longest language for that scene, so
        every language's rendered video ends up the same total length. No-ops
        for single-language projects. See duration_sync_service.py."""
        from app.services.duration_sync_service import DurationSyncService

        languages = await self._get_project_languages()
        svc = DurationSyncService(
            project_id=self.project_id, project_dir=self.project_dir,
            languages=languages, project_language=self.project_language,
            progress_callback=sub_cb,
        )
        await svc.execute()

    async def _dd_subtitles(self, sub_cb: Callable) -> None:
        """Subtitles (+ localized metadata output for extra languages) for every
        project.languages entry. Sequential — Whisper has real local GPU/CPU
        resource contention, unrelated to API keys."""
        from app.services.subtitle_service import SubtitleGenerationService
        from app.services.metadata_service import MetadataService

        languages = await self._get_project_languages()
        input_dir = self.project_dir / "input"
        total = len(languages)

        for i, lang in enumerate(languages):
            await self.check_cancelled()
            is_primary = lang == self.project_language
            base_pct = i / total * 100.0

            async def lang_cb(p: float, msg: str, data: dict, _b: float = base_pct, _lang: str = lang, _primary: bool = is_primary) -> None:
                extra = {} if _primary else {"language": _lang}
                await sub_cb(_b + p / total, msg, {**extra, **data})

            svc = SubtitleGenerationService(
                project_id=self.project_id, project_dir=self.project_dir,
                whisper_model=self.whisper_model, language=lang, device=self.whisper_device,
                progress_callback=lang_cb,
                audio_dir_override=None if is_primary else self.project_dir / "audio" / lang,
                output_dir_override=None if is_primary else self.project_dir / "subtitles" / lang,
            )
            await svc.execute()
            if is_primary:
                continue
            await self._set_lang_progress(lang, "subtitles", {"status": "completed"})

            meta_svc = MetadataService(
                project_id=self.project_id, project_dir=self.project_dir,
                progress_callback=lang_cb,
                seo_path_override=input_dir / lang / "seo.json",
                output_dir_override=self.project_dir / "output" / lang,
            )
            await meta_svc.execute()
            await self._set_lang_progress(lang, "metadata", {"status": "completed"})

    async def _dd_thumbnail(self, sub_cb: Callable) -> None:
        """Thumbnail IMAGE — one FLUX render for the primary language; every other
        project.languages entry reuses that same rendered background and just
        overlays its own (already-translated) title/tags via
        ThumbnailGenerationService.generate_language_variant() — no extra FLUX call."""
        from app.services.thumbnail_service import ThumbnailGenerationService

        languages = await self._get_project_languages()
        input_dir = self.project_dir / "input"
        total = len(languages)

        svc = ThumbnailGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            comfyui_url=self.comfyui_url, flux_settings=self._flux_dict(),
            progress_callback=sub_cb,
        )
        await svc.execute()

        extra_languages = [l for l in languages if l != self.project_language]
        for i, lang in enumerate(extra_languages):
            await self.check_cancelled()
            base_pct = (i + 1) / total * 100.0

            async def lang_cb(p: float, msg: str, data: dict, _b: float = base_pct, _lang: str = lang) -> None:
                await sub_cb(_b + p / total, msg, {"language": _lang, **data})

            seo_path = input_dir / lang / "seo.json"
            seo_data = json.loads(seo_path.read_text(encoding="utf-8")) if seo_path.exists() else {}
            svc.progress_callback = lang_cb
            await svc.generate_language_variant(lang, seo_data)
            await self._set_lang_progress(lang, "thumbnail", {"status": "completed"})

    async def _set_lang_progress(self, language: str, step: str, data: dict) -> None:
        from app.database import get_session_factory
        from app.repositories.project_repo import ProjectRepository
        async with get_session_factory()() as sess:
            await ProjectRepository(sess).update_language_progress(self.project_id, language, step, data)
            await sess.commit()

    async def _get_project_languages(self) -> List[str]:
        from app.database import get_session_factory
        from app.repositories.project_repo import ProjectRepository
        async with get_session_factory()() as sess:
            project = await ProjectRepository(sess).get_by_id(self.project_id)
        return list((project.languages if project else None) or [self.project_language])

    async def _get_language_voices(self) -> Dict[str, str]:
        """The user's explicit per-language voice selections, if any."""
        from app.database import get_session_factory
        from app.repositories.project_repo import ProjectRepository
        async with get_session_factory()() as sess:
            project = await ProjectRepository(sess).get_by_id(self.project_id)
        return dict((project.language_voices if project else None) or {})

    def _resolve_voice_id(self, language_voices: Dict[str, str], lang: str) -> Optional[str]:
        """Precedence: explicit per-project selection > global per-language
        Settings default > the built-in default (handled downstream)."""
        return language_voices.get(lang) or self.default_voices.get(lang)

    async def _dd_video(self, sub_cb: Callable) -> None:
        """Render the final video for every project.languages entry — each reusing
        the shared images/clips but its own audio/subtitles/thumbnail. Sequential
        (MoviePy/FFmpeg rendering is CPU/GPU-bound, no benefit from concurrency)."""
        from app.services.video_service import VideoGenerationService
        v = self.video
        languages = await self._get_project_languages()
        total = len(languages)

        for i, lang in enumerate(languages):
            await self.check_cancelled()
            is_primary = lang == self.project_language
            base_pct = i / total * 100.0

            async def lang_cb(p: float, msg: str, data: dict, _b: float = base_pct, _lang: str = lang, _primary: bool = is_primary) -> None:
                extra = {} if _primary else {"language": _lang}
                await sub_cb(_b + p / total, msg, {**extra, **data})

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
                language=lang,
                audio_dir_override=None if is_primary else self.project_dir / "audio" / lang,
                subtitles_dir_override=None if is_primary else self.project_dir / "subtitles" / lang,
                output_subdir="output" if is_primary else f"output/{lang}",
                progress_callback=lang_cb,
            )
            await svc.execute()
            if not is_primary:
                await self._set_lang_progress(lang, "video", {"status": "completed"})

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
        """Primary language: news script → per-section scenes/prompts split.
        Then every additional project.languages entry gets its own independent
        script + per-section scene-narration composition + thumbnail concept +
        SEO (see _an_extra_language_content) — only the per-section scene
        skeleton is shared, so the shared images stay valid."""
        topics_path = self.project_dir / "input" / "topics.json"
        script_path = self.project_dir / "input" / "script.md"

        if not topics_path.exists():
            raise ServiceError(self.service_name, "topics.json not found — Topics step must run first")

        stories = json.loads(topics_path.read_text(encoding="utf-8"))
        stories_data = [{"title": s["title"], "summary": s.get("summary", "")} for s in stories]

        async def primary_cb(p: float, msg: str, data: dict) -> None:
            await sub_cb(p * 0.35, msg, data)

        if not script_path.exists():
            svc = self._build_ai_news_svc(primary_cb)
            await svc.generate_all_for_news(stories_data)
        else:
            await sub_cb(35, "Script already exists — skipping to section split", {})

        # Split to per-section files
        from app.services.ai_news_section_service import AiNewsSectionService
        script = script_path.read_text(encoding="utf-8")

        async def sec_cb(p: float, msg: str, data: dict) -> None:
            await sub_cb(35.0 + p * 0.35, msg, data)

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

        async def extra_cb(p: float, msg: str, data: dict) -> None:
            await sub_cb(70.0 + p * 0.3, msg, data)

        await self._an_extra_language_content(extra_cb)

    async def _an_extra_language_content(self, sub_cb: Callable) -> None:
        """Translate the primary language's already-generated news script,
        per-section scene narration, thumbnail concept, and SEO into every other
        project.languages entry — mirrors _dd_translate_extra_languages: every
        language shares the single Gemini API key, so calls are serialized via
        one shared lock. Only the per-section scene skeleton (scene_id/
        image_file/visual_description) is reused verbatim from the primary
        language, so the shared images stay valid."""
        from app.database import get_session_factory
        from app.repositories.project_repo import ProjectRepository
        from app.services.ai_news_service import AiNewsService

        async with get_session_factory()() as sess:
            project = await ProjectRepository(sess).get_by_id(self.project_id)
        languages = list((project.languages if project else None) or [self.project_language])
        extra_languages = [l for l in languages if l != self.project_language]
        if not extra_languages:
            await sub_cb(100, "No additional languages selected — skipping", {})
            return

        labels = self._section_labels()
        if not labels:
            await sub_cb(100, "No sections found — skipping language variants", {})
            return

        input_dir = self.project_dir / "input"
        base_script = (input_dir / "script.md").read_text(encoding="utf-8")
        base_thumbnail_full = (input_dir / "thumbnail_full.txt").read_text(encoding="utf-8")
        base_seo_json = (input_dir / "seo.json").read_text(encoding="utf-8")

        shared_lock = asyncio.Lock()
        total = len(extra_languages)

        async def run_content_phase(idx: int, lang: str) -> None:
            base_pct = idx / total * 100.0

            async def lang_cb(p: float, msg: str, data: dict, _b: float = base_pct, _lang: str = lang) -> None:
                await sub_cb(_b + p / total, msg, {"language": _lang, **data})

            variant_dir = input_dir / lang
            variant_dir.mkdir(parents=True, exist_ok=True)

            variant_svc = AiNewsService(
                project_id=self.project_id, project_dir=self.project_dir,
                api_key=self.gemini.api_key, pro_model=self.gemini.pro_model,
                script_model=self.gemini.script_model, flash_model=self.gemini.flash_model,
                search_grounding=self.gemini.search_grounding,
                image_backend=self.gemini.image_backend,
                language=lang, channel_name=self.channel_name,
                progress_callback=lang_cb,
            )
            variant_svc.input_dir = variant_dir

            async with shared_lock:
                try:
                    await lang_cb(5, f"Translating {lang} script…", {})
                    await variant_svc.translate_script(base_script, lang)

                    for si, label in enumerate(labels):
                        await self.check_cancelled()
                        scenes_path = input_dir / "sections" / label / "scenes.json"
                        if not scenes_path.exists():
                            continue
                        base_scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
                        if not base_scenes:
                            continue
                        translated = await variant_svc.translate_scenes_narration(base_scenes, lang)
                        sec_dir = variant_dir / "sections" / label
                        sec_dir.mkdir(parents=True, exist_ok=True)
                        (sec_dir / "scenes.json").write_text(
                            json.dumps(translated, indent=2, ensure_ascii=False), encoding="utf-8"
                        )
                        await lang_cb(10 + si / len(labels) * 55, f"Translated narration: {label}", {"section": label})

                    await self._set_lang_progress(lang, "script", {"status": "completed"})

                    await lang_cb(75, f"Translating {lang} thumbnail concept…", {})
                    await variant_svc.translate_thumbnail_concept(base_thumbnail_full, lang)

                    await lang_cb(90, f"Translating {lang} SEO metadata…", {})
                    await variant_svc.translate_seo(base_seo_json, lang)
                except Exception as exc:
                    self.logger.warning("Language variant translation failed for '%s': %s", lang, exc)
                    await self._set_lang_progress(lang, "script", {"status": "failed", "error": str(exc)})
                    return

        await self.check_cancelled()
        await asyncio.gather(*[run_content_phase(i, lang) for i, lang in enumerate(extra_languages)])

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
        """Section voice for every project.languages entry. Sequential per
        language (nested per-section local TTS/ComfyUI calls make cross-language
        concurrency hard to reason about safely — unlike the pure-Gemini content
        phase, which does run concurrently)."""
        languages = await self._get_project_languages()
        labels = self._section_labels()
        language_voices = await self._get_language_voices()
        input_dir = self.project_dir / "input"
        total_langs = len(languages)
        total_secs = max(len(labels), 1)

        for li, lang in enumerate(languages):
            await self.check_cancelled()
            is_primary = lang == self.project_language
            base_pct = li / total_langs * 100.0
            voice_id = self._resolve_voice_id(language_voices, lang)

            for si, label in enumerate(labels):
                await self.check_cancelled()
                scenes_path = (input_dir / "sections" / label / "scenes.json") if is_primary \
                    else (input_dir / lang / "sections" / label / "scenes.json")
                if not scenes_path.exists():
                    continue

                async def voice_cb(p: float, msg: str, data: dict, _b: float = base_pct, _si: int = si, _lang: str = lang, _primary: bool = is_primary, _label: str = label) -> None:
                    extra = {"section": _label} if _primary else {"section": _label, "language": _lang}
                    await sub_cb(_b + (_si / total_secs * 100 + p / total_secs) / total_langs, msg, {**extra, **data})

                voice_svc = await self._build_voice_svc(
                    voice_cb, language=lang,
                    output_dir_override=None if is_primary else self.project_dir / "audio" / lang,
                    voice_id=voice_id,
                )
                await voice_svc.generate_section_voice(
                    section_label=label,
                    section_scenes_path=scenes_path,
                    section_script_text="",
                )
            if not is_primary:
                await self._set_lang_progress(lang, "voice", {"status": "completed"})

    async def _an_subtitles(self, sub_cb: Callable) -> None:
        """Section subtitles (+ localized metadata for extra languages) for every
        project.languages entry. Sequential — Whisper has real local GPU/CPU
        resource contention, unrelated to API keys."""
        from app.services.subtitle_service import SubtitleGenerationService
        from app.services.metadata_service import MetadataService

        languages = await self._get_project_languages()
        labels = self._section_labels()
        total_langs = len(languages)
        total_secs = max(len(labels), 1)

        for li, lang in enumerate(languages):
            await self.check_cancelled()
            is_primary = lang == self.project_language
            base_pct = li / total_langs * 100.0

            svc = SubtitleGenerationService(
                project_id=self.project_id, project_dir=self.project_dir,
                whisper_model=self.whisper_model, language=lang, device=self.whisper_device,
                audio_dir_override=None if is_primary else self.project_dir / "audio" / lang,
                output_dir_override=None if is_primary else self.project_dir / "subtitles" / lang,
            )

            for si, label in enumerate(labels):
                await self.check_cancelled()
                audio_dir = self.project_dir / "audio" if is_primary else self.project_dir / "audio" / lang
                subs_dir  = self.project_dir / "subtitles" if is_primary else self.project_dir / "subtitles" / lang
                audio_path = audio_dir / "sections" / label / "narration.wav"
                srt_path   = subs_dir / "sections" / label / "subtitles.srt"
                if not audio_path.exists() or srt_path.exists():
                    continue

                async def sub_cb2(p: float, msg: str, data: dict, _b: float = base_pct, _si: int = si, _lang: str = lang, _primary: bool = is_primary, _label: str = label) -> None:
                    extra = {"section": _label} if _primary else {"section": _label, "language": _lang}
                    await sub_cb(_b + (_si / total_secs * 100 + p / total_secs) / total_langs, msg, {**extra, **data})

                svc.progress_callback = sub_cb2
                await svc.generate_section_subtitles(label, audio_path)

            if is_primary:
                continue
            await self._set_lang_progress(lang, "subtitles", {"status": "completed"})

            meta_svc = MetadataService(
                project_id=self.project_id, project_dir=self.project_dir,
                seo_path_override=self.project_dir / "input" / lang / "seo.json",
                output_dir_override=self.project_dir / "output" / lang,
            )
            await meta_svc.execute()
            await self._set_lang_progress(lang, "metadata", {"status": "completed"})

    async def _an_thumbnail(self, sub_cb: Callable) -> None:
        """Thumbnail IMAGE — one FLUX render for the primary language; every other
        project.languages entry reuses that same rendered background and just
        overlays its own (already-translated) title/tags — no extra FLUX call."""
        from app.services.thumbnail_service import ThumbnailGenerationService

        languages = await self._get_project_languages()
        input_dir = self.project_dir / "input"
        total = len(languages)

        svc = ThumbnailGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            comfyui_url=self.comfyui_url, flux_settings=self._flux_dict(),
            progress_callback=sub_cb,
        )
        await svc.execute()

        extra_languages = [l for l in languages if l != self.project_language]
        for i, lang in enumerate(extra_languages):
            await self.check_cancelled()
            base_pct = (i + 1) / total * 100.0

            async def lang_cb(p: float, msg: str, data: dict, _b: float = base_pct, _lang: str = lang) -> None:
                await sub_cb(_b + p / total, msg, {"language": _lang, **data})

            seo_path = input_dir / lang / "seo.json"
            seo_data = json.loads(seo_path.read_text(encoding="utf-8")) if seo_path.exists() else {}
            svc.progress_callback = lang_cb
            await svc.generate_language_variant(lang, seo_data)
            await self._set_lang_progress(lang, "thumbnail", {"status": "completed"})

    async def _an_ltx(self, sub_cb: Callable) -> None:
        from app.services.ltx_comfy_service import AiNewsLTXService
        svc = AiNewsLTXService(
            project_id=self.project_id, project_dir=self.project_dir,
            comfyui_url=self.comfyui_url, progress_callback=sub_cb,
        )
        await svc.generate_all_sections()

    async def _an_video(self, sub_cb: Callable) -> None:
        """Render section clips for every project.languages entry — each reusing
        the shared images but its own audio/subtitles. Sequential (rendering is
        CPU/GPU-bound, no benefit from concurrency)."""
        from app.services.shorts_service import AiNewsClipService
        from app.services.ai_news_section_service import AiNewsSectionService

        languages = await self._get_project_languages()
        labels = self._section_labels()
        total_langs = len(languages)
        total_secs = max(len(labels), 1)

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

        for li, lang in enumerate(languages):
            await self.check_cancelled()
            is_primary = lang == self.project_language
            base_pct = li / total_langs * 100.0

            clip_svc = AiNewsClipService(
                project_id=self.project_id, project_dir=self.project_dir,
                language=lang, channel_name=self.channel_name,
                audio_dir_override=None if is_primary else self.project_dir / "audio" / lang,
                subtitles_dir_override=None if is_primary else self.project_dir / "subtitles" / lang,
                output_dir_override=None if is_primary else self.project_dir / "output" / lang,
            )

            for si, label in enumerate(labels):
                await self.check_cancelled()
                audio_dir = self.project_dir / "audio" if is_primary else self.project_dir / "audio" / lang
                audio_path = audio_dir / "sections" / label / "narration.wav"
                if label != "agenda" and not audio_path.exists():
                    continue

                title = section_titles.get(label, label.replace("_", " ").title())

                try:
                    await clip_svc.regenerate_section_clip(label, title=title)
                except Exception as exc:
                    self.logger.warning("Clip failed for %s/%s: %s", lang, label, exc)

                pct = base_pct + (si + 1) / total_secs * 100 / total_langs
                extra = {"section": label} if is_primary else {"section": label, "language": lang}
                await sub_cb(pct, f"Done: {label}", extra)

            if not is_primary:
                await self._set_lang_progress(lang, "video", {"status": "completed"})

    async def _an_youtube_upload(self, sub_cb: Callable) -> None:
        """AI News has no single rendered episode video — concatenate the
        per-section clips (output/clips_ai_news/{label}.mp4) into one file
        before uploading."""
        output_dir = self.project_dir / "output"
        combined_path = output_dir / "ai_news_final.mp4"
        if not combined_path.exists():
            labels = self._section_labels()
            clips_dir = output_dir / "clips_ai_news"
            clip_paths = [clips_dir / f"{label}.mp4" for label in labels if (clips_dir / f"{label}.mp4").exists()]
            if not clip_paths:
                await sub_cb(100, "No AI News clips found — skipping YouTube upload", {})
                return
            await sub_cb(5, "Combining section clips…", {})
            await self._concat_ai_news_clips(output_dir, clip_paths, combined_path)

        thumbnail_path = output_dir / "thumbnail" / "thumbnail.png"
        await self._youtube_upload_common(sub_cb, combined_path, thumbnail_path)

    async def _concat_ai_news_clips(
        self, output_dir: Path, clip_paths: List[Path], combined_path: Path,
    ) -> Path:
        """Concatenate ordered AI News section clips into a single video file via
        ffmpeg concat-demuxer. `output_dir` is the (possibly per-language) output
        root the temporary concat list is written under."""
        concat_list = output_dir / "_ai_news_concat.txt"
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
        return combined_path

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

    async def _build_voice_svc(
        self,
        progress_callback: Callable,
        language: Optional[str] = None,
        scenes_path_override: Optional[Path] = None,
        output_dir_override: Optional[Path] = None,
        voice_id: Optional[str] = None,
    ):
        lang = language or self.project_language
        if self.tts_engine == "google":
            from app.services.google_tts_service import GoogleTTSService
            # An explicit voice_id (user's per-language choice) always wins.
            # Otherwise the global Settings voice override is only meaningful
            # for the primary language — applying it to every additional
            # language variant would force e.g. a configured Spanish voice
            # onto a Hindi variant, so other languages fall back to their
            # per-language default inside GoogleTTSService.
            if voice_id:
                voice_name = voice_id
                language_code = "-".join(voice_id.split("-")[:2])
            else:
                is_primary = lang == self.project_language
                voice_name = self.google_tts.voice_name if is_primary else ""
                language_code = self.google_tts.language_code if is_primary else ""
            api_key = self.google_tts.language_api_keys.get(lang) or self.google_tts.api_key
            return GoogleTTSService(
                project_id=self.project_id, project_dir=self.project_dir,
                api_key=api_key,
                voice_name=voice_name,
                language_code=language_code,
                speaking_rate=self.google_tts.speaking_rate,
                project_language=lang,
                progress_callback=progress_callback,
                scenes_path_override=scenes_path_override,
                output_dir_override=output_dir_override,
            )
        from app.services.piper_model_manager import ensure_model
        from app.services.voice_service import VoiceGenerationService
        resolved = await ensure_model(
            lang, self.piper.model_path, progress_callback, voice_id=voice_id,
        )
        return VoiceGenerationService(
            project_id=self.project_id, project_dir=self.project_dir,
            piper_executable=self.piper.executable,
            model_path=resolved or self.piper.model_path,
            speed=self.piper.speed,
            progress_callback=progress_callback,
            scenes_path_override=scenes_path_override,
            output_dir_override=output_dir_override,
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
