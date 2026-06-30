"""
Google Cloud Text-to-Speech voice generation service.

Uses the REST API directly (no google-cloud SDK required) — only needs an
API key from the Google Cloud Console with the TTS API enabled.

Free tier: 1 million characters/month for WaveNet/Neural2 voices,
           4 million characters/month for Standard voices.
"""
import asyncio
import base64
import json
import logging
import subprocess
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_GTTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# ISO 639-1 → (languageCode, voice_name) defaults
_LANG_DEFAULTS: Dict[str, tuple] = {
    "en":  ("en-US", "en-US-Neural2-C"),
    "te":  ("te-IN", "te-IN-Standard-A"),
    "hi":  ("hi-IN", "hi-IN-Wavenet-A"),
    "ml":  ("ml-IN", "ml-IN-Wavenet-A"),
    "ta":  ("ta-IN", "ta-IN-Wavenet-A"),
    "kn":  ("kn-IN", "kn-IN-Wavenet-A"),
    "mr":  ("mr-IN", "mr-IN-Wavenet-A"),
    "bn":  ("bn-IN", "bn-IN-Wavenet-A"),
    "de":  ("de-DE", "de-DE-Neural2-A"),
    "fr":  ("fr-FR", "fr-FR-Neural2-A"),
    "es":  ("es-ES", "es-ES-Neural2-A"),
    "pt":  ("pt-BR", "pt-BR-Neural2-A"),
    "it":  ("it-IT", "it-IT-Neural2-A"),
    "ru":  ("ru-RU", "ru-RU-Wavenet-A"),
    "ar":  ("ar-XA", "ar-XA-Wavenet-A"),
    "zh":  ("cmn-CN", "cmn-CN-Wavenet-A"),
    "ja":  ("ja-JP", "ja-JP-Neural2-B"),
    "ko":  ("ko-KR", "ko-KR-Neural2-A"),
}


def language_defaults(lang: str) -> tuple:
    """Return (languageCode, voiceName) for a 2-letter ISO language code."""
    key = lang.lower().split("_")[0].split("-")[0]
    return _LANG_DEFAULTS.get(key, _LANG_DEFAULTS["en"])


class GoogleTTSService:
    """Generate narration WAV files using the Google Cloud TTS REST API."""

    SAMPLE_RATE = 22050

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        api_key: str,
        voice_name: str = "",
        language_code: str = "",
        speaking_rate: float = 1.0,
        project_language: str = "en",
        progress_callback: Optional[Callable] = None,
    ) -> None:
        self.project_id = project_id
        self.project_dir = project_dir
        self.api_key = api_key
        self.speaking_rate = speaking_rate
        self._progress_cb = progress_callback
        self.audio_dir = project_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        # Fall back to language defaults when not explicitly set in settings
        default_lc, default_vn = language_defaults(project_language)
        self.language_code = language_code or default_lc
        self.voice_name = voice_name or default_vn

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _progress(self, pct: float, msg: str, data: dict = None) -> None:
        if self._progress_cb:
            await self._progress_cb(pct, msg, data or {})

    def _synthesize(self, text: str, dest: Path) -> None:
        """Synthesize one text string and write a WAV file to *dest*."""
        url = f"{_GTTS_URL}?key={self.api_key}"
        body = json.dumps({
            "input": {"text": text},
            "voice": {
                "languageCode": self.language_code,
                "name": self.voice_name,
            },
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": self.SAMPLE_RATE,
                "speakingRate": self.speaking_rate,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"Google TTS API error {exc.code}: {detail[:400]}"
            ) from exc

        raw_pcm = base64.b64decode(result["audioContent"])
        with wave.open(str(dest), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)          # 16-bit PCM
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(raw_pcm)

    def _concat(self, wavs: List[Path], dest: Path) -> None:
        fl = dest.parent / "_gtts_concat.txt"
        fl.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in wavs),
            encoding="utf-8",
        )
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(fl), "-c", "copy", str(dest)],
            capture_output=True, text=True, timeout=300,
        )
        fl.unlink(missing_ok=True)
        if r.returncode != 0:
            raise RuntimeError(f"Audio merge failed: {r.stderr[-400:]}")

    def _clear_stale(self, sec_audio: Path, chunks: list) -> None:
        """If all scene WAVs already exist, delete them so stale audio is never reused."""
        existing = [sec_audio / f"scene_{int(c['id']):03d}.wav" for c in chunks]
        if all(w.exists() and w.stat().st_size > 0 for w in existing):
            for w in existing:
                w.unlink(missing_ok=True)
            (sec_audio / "narration.wav").unlink(missing_ok=True)

    def _load_scenes(self, path: Path) -> List[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data if isinstance(data, list) else data.get("scenes", [])
        return [
            {"id": s.get("scene_id", i + 1), "text": s.get("narration", "").strip()}
            for i, s in enumerate(raw)
            if s.get("narration", "").strip()
        ]

    # ── public API (mirrors VoiceGenerationService) ──────────────────────────

    async def execute(self) -> Dict[str, Any]:
        """Generate narration for a standard Deep Dive project (input/scenes.json)."""
        scenes_path = self.project_dir / "input" / "scenes.json"
        if not scenes_path.exists():
            raise FileNotFoundError("input/scenes.json not found")

        chunks = self._load_scenes(scenes_path)
        if not chunks:
            raise RuntimeError("No narration text found in scenes.json")

        self._clear_stale(self.audio_dir, chunks)

        total = len(chunks)
        loop = asyncio.get_event_loop()
        generated: List[Path] = []

        for idx, chunk in enumerate(chunks):
            dest = self.audio_dir / f"scene_{int(chunk['id']):03d}.wav"
            await self._progress(
                idx / total * 90,
                f"Google TTS: scene {idx + 1}/{total}",
                {"scene_id": chunk["id"], "completed": idx, "total": total},
            )
            await loop.run_in_executor(None, self._synthesize, chunk["text"], dest)
            generated.append(dest)

        merged = self.audio_dir / "narration_merged.wav"
        if generated:
            await loop.run_in_executor(None, self._concat, generated, merged)

        await self._progress(100, f"Google TTS done — {total} scenes", {})
        return {
            "generated": total,
            "total": total,
            "narration_wav": str(merged) if merged.exists() else None,
        }

    async def generate_section_voice(
        self,
        section_label: str,
        section_scenes_path: Optional[Path] = None,
        section_script_text: str = "",
    ) -> Dict[str, Any]:
        """Generate narration for one AI News section."""
        sec_audio = self.audio_dir / "sections" / section_label
        sec_audio.mkdir(parents=True, exist_ok=True)

        chunks: List[Dict[str, Any]] = []
        if section_scenes_path and section_scenes_path.exists():
            chunks = self._load_scenes(section_scenes_path)
        elif section_script_text:
            chunks = [{"id": 1, "text": section_script_text.strip()}]

        if not chunks:
            raise RuntimeError(f"No narration text for section '{section_label}'")

        self._clear_stale(sec_audio, chunks)

        total = len(chunks)
        loop = asyncio.get_event_loop()
        generated: List[Path] = []

        for idx, chunk in enumerate(chunks):
            dest = sec_audio / f"scene_{int(chunk['id']):03d}.wav"
            await self._progress(
                idx / total * 90,
                f"Google TTS: {section_label} {idx + 1}/{total}",
                {"scene_id": chunk["id"], "completed": idx, "total": total},
            )
            await loop.run_in_executor(None, self._synthesize, chunk["text"], dest)
            generated.append(dest)

        narr = sec_audio / "narration.wav"
        if generated:
            await loop.run_in_executor(None, self._concat, generated, narr)

        await self._progress(100, f"Section '{section_label}' done", {})
        return {
            "label": section_label,
            "chunks": total,
            "generated": len(generated),
            "narration_wav": str(narr) if narr.exists() else None,
        }
