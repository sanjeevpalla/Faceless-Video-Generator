"""
TranslationService — translates project narration files to a target language.

Uses deep-translator (Google Translate free tier, no API key required) to translate:
  - input/scenes.json  → narration + title per scene
  - input/script.md    → full narration text
  - input/seo.json     → title, description, tags

Files NOT translated (must remain in English for FLUX image generation):
  - input/image_prompts.txt
  - input/thumbnail_prompt.txt
  - scenes.json → visual_description field

Original files are backed up with _original suffix before overwriting so the
user can restore them or re-run translation with a different language.
"""
import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.services.base import BaseService
from app.core.exceptions import ServiceError


class TranslationService(BaseService):
    service_name = "translation"

    SUPPORTED_LANGUAGES: Dict[str, str] = {
        "te": "Telugu",
        "hi": "Hindi",
        "ta": "Tamil",
        "kn": "Kannada",
        "ml": "Malayalam",
        "bn": "Bengali",
        "mr": "Marathi",
        "gu": "Gujarati",
        "pa": "Punjabi",
        "ur": "Urdu",
        "ar": "Arabic",
        "zh-CN": "Chinese (Simplified)",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "pt": "Portuguese",
        "ru": "Russian",
        "it": "Italian",
    }

    MAX_CHUNK = 4500  # Google free tier safe limit per request

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        target_language: str = "te",
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.target_language = target_language
        self.input_dir = self.project_dir / "input"

    async def execute(self) -> Dict[str, Any]:
        return await self.translate()

    # ------------------------------------------------------------------
    # Text chunking
    # ------------------------------------------------------------------
    def _chunk_text(self, text: str) -> List[str]:
        if len(text) <= self.MAX_CHUNK:
            return [text]
        chunks: List[str] = []
        current = ""
        for para in text.split("\n\n"):
            if len(current) + len(para) + 2 <= self.MAX_CHUNK:
                current = f"{current}\n\n{para}".strip()
            else:
                if current:
                    chunks.append(current)
                if len(para) > self.MAX_CHUNK:
                    # Para too big — split by sentence
                    for sentence in para.replace(". ", ".\n").splitlines():
                        s = sentence.strip()
                        if not s:
                            continue
                        if len(current) + len(s) + 1 <= self.MAX_CHUNK:
                            current = f"{current} {s}".strip()
                        else:
                            if current:
                                chunks.append(current)
                            current = s
                else:
                    current = para
        if current:
            chunks.append(current)
        return chunks or [text]

    def _translate_text(self, translator, text: str) -> str:
        if not text or not text.strip():
            return text
        translated: List[str] = []
        for chunk in self._chunk_text(text.strip()):
            try:
                result = translator.translate(chunk)
                translated.append(result if result else chunk)
            except Exception as exc:
                self.logger.warning(f"Translation chunk failed: {exc} — keeping original")
                translated.append(chunk)
        return "\n\n".join(translated)

    # ------------------------------------------------------------------
    # Per-file translation
    # ------------------------------------------------------------------
    def _backup(self, path: Path) -> None:
        backup = path.parent / f"{path.stem}_original{path.suffix}"
        if not backup.exists():
            shutil.copy2(path, backup)
            self.logger.debug(f"Backed up {path.name} → {backup.name}")

    def _translate_scenes(self, translator) -> bool:
        path = self.input_dir / "scenes.json"
        if not path.exists():
            self.logger.info("scenes.json not found — skipping")
            return False
        self._backup(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.logger.warning(f"Cannot parse scenes.json: {exc}")
            return False

        scenes = raw.get("scenes", raw) if isinstance(raw, dict) else raw
        for scene in scenes:
            if scene.get("narration"):
                scene["narration"] = self._translate_text(translator, scene["narration"])
            if scene.get("title"):
                scene["title"] = self._translate_text(translator, scene["title"])
            # visual_description intentionally NOT translated — used by FLUX image gen

        out = {"scenes": scenes} if (isinstance(raw, dict) and "scenes" in raw) else scenes
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.info(f"Translated {len(scenes)} scene(s) in scenes.json")
        return True

    def _translate_script(self, translator) -> bool:
        path: Optional[Path] = None
        for name in ["script.md", "script.txt"]:
            c = self.input_dir / name
            if c.exists():
                path = c
                break
        if path is None:
            self.logger.info("script.md not found — skipping")
            return False
        self._backup(path)
        text = path.read_text(encoding="utf-8")
        translated = self._translate_text(translator, text)
        path.write_text(translated, encoding="utf-8")
        self.logger.info(f"Translated {path.name} ({len(text)} → {len(translated)} chars)")
        return True

    def _translate_seo(self, translator) -> bool:
        path = self.input_dir / "seo.json"
        if not path.exists():
            self.logger.info("seo.json not found — skipping")
            return False
        self._backup(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.logger.warning(f"Cannot parse seo.json: {exc}")
            return False

        for key in ("title", "description"):
            if data.get(key):
                data[key] = self._translate_text(translator, data[key])
        if isinstance(data.get("tags"), list):
            data["tags"] = [self._translate_text(translator, t) for t in data["tags"] if t]

        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.info("Translated seo.json")
        return True

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    async def translate(self) -> Dict[str, Any]:
        try:
            from deep_translator import GoogleTranslator
        except ImportError:
            raise ServiceError(
                self.service_name,
                "deep-translator is not installed. Run: pip install deep-translator",
            )

        lang_name = self.SUPPORTED_LANGUAGES.get(self.target_language, self.target_language)
        await self.report_progress(5, f"Starting translation to {lang_name}…")

        translator = GoogleTranslator(source="auto", target=self.target_language)
        loop = asyncio.get_event_loop()

        await self.report_progress(15, "Translating scenes.json…")
        scenes_ok = await loop.run_in_executor(None, self._translate_scenes, translator)
        await self.check_cancelled()

        await self.report_progress(50, "Translating script.md…")
        script_ok = await loop.run_in_executor(None, self._translate_script, translator)
        await self.check_cancelled()

        await self.report_progress(80, "Translating seo.json…")
        seo_ok = await loop.run_in_executor(None, self._translate_seo, translator)

        await self.report_progress(100, f"Translation to {lang_name} complete")
        return {
            "target_language": self.target_language,
            "language_name": lang_name,
            "scenes_translated": scenes_ok,
            "script_translated": script_ok,
            "seo_translated": seo_ok,
        }
