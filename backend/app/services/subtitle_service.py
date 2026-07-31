import asyncio
import hashlib
import json
import re
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.base import BaseService
from app.core.exceptions import ServiceError


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


# Max characters per subtitle line/chunk — keeps captions readable, matching
# roughly what Whisper itself would break a long sentence into.
_MAX_CHUNK_CHARS = 90


class SubtitleGenerationService(BaseService):
    """Generates subtitles using OpenAI Whisper."""

    service_name = "subtitle_generation"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        whisper_model: str = "base",
        language: str = "en",
        device: str = "cpu",
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
        audio_dir_override: Optional[Path] = None,
        output_dir_override: Optional[Path] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.whisper_model = whisper_model
        self.language = language
        self.device = device
        self.audio_dir_override = Path(audio_dir_override) if audio_dir_override else None
        self.subtitles_dir = (
            self.ensure_dir(Path(output_dir_override)) if output_dir_override
            else self.get_output_dir("subtitles")
        )
        self.cache_dir = self.get_output_dir("cache/subtitles")
        self._model = None

    async def execute(self) -> Dict[str, Any]:
        return await self.generate()

    async def generate(self) -> Dict[str, Any]:
        audio_path = self._find_audio_file()
        if not audio_path:
            raise ServiceError(self.service_name, "No audio file found for subtitle generation")

        # Prefer building subtitles directly from the known TTS narration text
        # (scenes.json) over re-transcribing via Whisper ASR — this is exact
        # (no ASR errors) and, for lower-resource languages Whisper handles
        # poorly (e.g. Telugu/Tamil/Kannada/Malayalam), the only reliable
        # option. Only falls through to Whisper when there's no per-scene
        # audio to anchor timing to (e.g. a single uploaded narration file).
        audio_dir = self.audio_dir_override or (self.project_dir / "audio")
        scene_segments = self._scene_based_segments(self._scenes_json_path(), audio_dir)
        if scene_segments is not None:
            await self.report_progress(
                60, f"Building subtitles from {len(scene_segments)} known narration segment(s)…"
            )
            srt_path = await self.export_srt(scene_segments)
            vtt_path = await self.export_vtt(scene_segments)
            result = {
                "srt_path": str(srt_path),
                "vtt_path": str(vtt_path),
                "segment_count": len(scene_segments),
                "source": "scene_text",
                "segments": scene_segments,
            }
            await self.report_progress(100, "Subtitle generation complete (from known narration text)")
            return result

        audio_hash = self._hash_audio(audio_path)
        cached = self.check_cache(audio_hash)
        if cached:
            await self.report_progress(100, "Subtitles loaded from cache")
            return cached

        await self.report_progress(10, "Loading Whisper model...")
        model = await self._load_model()

        await self.report_progress(25, "Transcribing audio...")
        segments = await self._transcribe(model, audio_path)

        await self.report_progress(75, "Exporting subtitles...")
        srt_path = await self.export_srt(segments)
        vtt_path = await self.export_vtt(segments)

        await self.report_progress(90, "Writing cache...")
        result = {
            "srt_path": str(srt_path),
            "vtt_path": str(vtt_path),
            "segment_count": len(segments),
            "audio_hash": audio_hash,
            "segments": segments,
        }

        cache_file = self.cache_dir / f"{audio_hash}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        await self.report_progress(100, "Subtitle generation complete")
        return result

    async def generate_section_subtitles(
        self,
        section_label: str,
        audio_path: Path,
    ) -> Dict[str, Any]:
        """Run Whisper on section narration WAV and save SRT/VTT under subtitles/sections/{label}/.

        Args:
            section_label: e.g. 'intro', 'story_01', 'outro'
            audio_path:    full path to audio/sections/{label}/narration.wav
        """
        if not audio_path.exists():
            raise ServiceError(
                self.service_name,
                f"Audio not found for section '{section_label}' — generate voice first.",
            )

        sec_sub_dir = self.subtitles_dir / "sections" / section_label
        sec_sub_dir.mkdir(parents=True, exist_ok=True)

        # Prefer known narration text (see generate()'s docstring comment for why)
        # over Whisper ASR — audio_path's own directory holds this section's
        # per-scene WAVs (audio/[lang/]sections/{label}/scene_NNN.wav).
        segments = self._scene_based_segments(
            self._section_scenes_json_path(section_label), audio_path.parent
        )
        if segments is None:
            await self.report_progress(10, f"Loading Whisper model for section '{section_label}'…")
            model = await self._load_model()

            await self.report_progress(30, f"Transcribing section '{section_label}'…")
            segments = await self._transcribe(model, audio_path)

        await self.report_progress(80, "Writing subtitle files…")

        # Write SRT
        srt_path = sec_sub_dir / "subtitles.srt"
        srt_lines = []
        for i, seg in enumerate(segments, 1):
            srt_lines.append(
                f"{i}\n"
                f"{self._seconds_to_srt_time(seg['start'])} --> {self._seconds_to_srt_time(seg['end'])}\n"
                f"{seg['text']}\n"
            )
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")

        # Write VTT
        vtt_path = sec_sub_dir / "subtitles.vtt"
        vtt_lines = ["WEBVTT\n"]
        for i, seg in enumerate(segments, 1):
            vtt_lines.append(
                f"{i}\n"
                f"{self._seconds_to_vtt_time(seg['start'])} --> {self._seconds_to_vtt_time(seg['end'])}\n"
                f"{seg['text']}\n"
            )
        vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")

        await self.report_progress(100, f"Section '{section_label}' subtitles done — {len(segments)} segments")
        return {
            "label":          section_label,
            "srt_path":       str(srt_path),
            "vtt_path":       str(vtt_path),
            "segment_count":  len(segments),
        }

    # ------------------------------------------------------------------
    # Known-text subtitles — build directly from scenes.json narration +
    # each scene's actual audio duration, bypassing Whisper ASR entirely.
    # ------------------------------------------------------------------
    def _is_primary(self) -> bool:
        """audio_dir_override is None precisely when this is the project's
        primary language — the same convention pipeline_service.py and
        api/jobs.py already use when constructing this service per language."""
        return self.audio_dir_override is None

    def _scenes_json_path(self) -> Path:
        if self._is_primary():
            return self.project_dir / "input" / "scenes.json"
        return self.project_dir / "input" / self.language / "scenes.json"

    def _section_scenes_json_path(self, section_label: str) -> Path:
        if self._is_primary():
            return self.project_dir / "input" / "sections" / section_label / "scenes.json"
        return self.project_dir / "input" / self.language / "sections" / section_label / "scenes.json"

    def _scene_based_segments(
        self, scenes_path: Path, audio_dir: Path
    ) -> Optional[List[Dict[str, Any]]]:
        """Build subtitle segments straight from known narration text, timed to
        each scene's actual generated audio duration. Returns None (meaning
        "fall back to Whisper") when there's no per-scene audio to anchor
        timing to — e.g. a single uploaded narration file with no scene_*.wav
        breakdown, where we have no reliable way to know where each line of
        text starts and ends.
        """
        if not scenes_path.exists():
            return None
        try:
            data = json.loads(scenes_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        raw_scenes = data if isinstance(data, list) else data.get("scenes", [])
        if not raw_scenes:
            return None

        scene_wavs = sorted(audio_dir.glob("scene_*.wav"))
        if not scene_wavs:
            return None

        durations: Dict[int, float] = {}
        for wav in scene_wavs:
            try:
                sid = int(wav.stem.split("_")[1])
            except (IndexError, ValueError):
                continue
            durations[sid] = _wav_duration(wav)

        segments: List[Dict[str, Any]] = []
        t = 0.0
        seg_id = 0
        for i, scene in enumerate(raw_scenes):
            raw_sid = scene.get("scene_id") if isinstance(scene, dict) else None
            if raw_sid is None and isinstance(scene, dict):
                raw_sid = scene.get("id")
            try:
                sid = int(raw_sid) if raw_sid is not None else i + 1
            except (ValueError, TypeError):
                sid = i + 1

            dur = durations.get(sid)
            if dur is None:
                continue  # this scene has no generated audio yet

            text = (scene.get("narration") or "").strip() if isinstance(scene, dict) else ""
            if text:
                for chunk_text, chunk_start, chunk_end in self._split_narration(text, t, t + dur):
                    seg_id += 1
                    segments.append({
                        "id": seg_id,
                        "start": chunk_start,
                        "end": chunk_end,
                        "text": chunk_text,
                    })
            t += dur

        return segments

    @staticmethod
    def _split_narration(text: str, start: float, end: float) -> List[Tuple[str, float, float]]:
        """Split narration text into readable caption-sized chunks, distributing
        the scene's [start, end) duration proportionally by character count."""
        raw_parts = re.split(r"(?<=[.!?।॥])\s+", text)
        parts = [p.strip() for p in raw_parts if p.strip()] or [text]

        chunks: List[str] = []
        for part in parts:
            if len(part) <= _MAX_CHUNK_CHARS:
                chunks.append(part)
                continue
            words = part.split()
            cur = ""
            for w in words:
                candidate = f"{cur} {w}".strip()
                if len(candidate) <= _MAX_CHUNK_CHARS:
                    cur = candidate
                else:
                    if cur:
                        chunks.append(cur)
                    cur = w
            if cur:
                chunks.append(cur)
        if not chunks:
            chunks = [text]

        total_chars = sum(len(c) for c in chunks) or 1
        total_dur = max(end - start, 0.01)

        result: List[Tuple[str, float, float]] = []
        t = start
        for i, chunk in enumerate(chunks):
            share = len(chunk) / total_chars
            seg_end = end if i == len(chunks) - 1 else min(end, t + total_dur * share)
            result.append((chunk, t, seg_end))
            t = seg_end
        return result

    def _find_audio_file(self) -> Optional[Path]:
        audio_dir = self.audio_dir_override or (self.project_dir / "audio")
        for ext in ["*.wav", "*.mp3", "*.m4a", "*.ogg"]:
            files = list(audio_dir.glob(ext))
            if files:
                # Prefer merged narration
                for f in files:
                    if "merged" in f.name or "narration" in f.name:
                        return f
                return files[0]
        return None

    def check_cache(self, audio_hash: str) -> Optional[Dict[str, Any]]:
        cache_file = self.cache_dir / f"{audio_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                if Path(data.get("srt_path", "")).exists():
                    return data
            except Exception:
                pass
        return None

    def _hash_audio(self, audio_path: Path) -> str:
        stat = audio_path.stat()
        content = f"{audio_path}|{stat.st_size}|{stat.st_mtime}|{self.whisper_model}|{self.language}|fp16=False"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def _load_model(self):
        if self._model is not None:
            return self._model

        loop = asyncio.get_event_loop()

        def _load():
            import torch
            import whisper
            device = self.device
            if device == "cuda" and not torch.cuda.is_available():
                self.logger.warning("CUDA not available, falling back to CPU for Whisper")
                device = "cpu"
            return whisper.load_model(self.whisper_model, device=device)

        self._model = await loop.run_in_executor(None, _load)
        return self._model

    async def _transcribe(self, model, audio_path: Path) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()

        def _run():
            result = model.transcribe(
                str(audio_path),
                language=self.language,
                task="transcribe",
                fp16=False,
                verbose=False,
            )
            return result.get("segments", [])

        raw_segments = await loop.run_in_executor(None, _run)

        segments = []
        for seg in raw_segments:
            segments.append({
                "id": seg.get("id", 0),
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": seg.get("text", "").strip(),
            })
        return segments

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _seconds_to_vtt_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    async def export_srt(self, segments: List[Dict[str, Any]]) -> Path:
        srt_path = self.subtitles_dir / "subtitles.srt"
        lines = []
        for i, seg in enumerate(segments, 1):
            start = self._seconds_to_srt_time(seg["start"])
            end = self._seconds_to_srt_time(seg["end"])
            lines.append(f"{i}\n{start} --> {end}\n{seg['text']}\n")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.logger.info(f"Exported SRT: {srt_path}")
        return srt_path

    async def export_vtt(self, segments: List[Dict[str, Any]]) -> Path:
        vtt_path = self.subtitles_dir / "subtitles.vtt"
        lines = ["WEBVTT\n"]
        for i, seg in enumerate(segments, 1):
            start = self._seconds_to_vtt_time(seg["start"])
            end = self._seconds_to_vtt_time(seg["end"])
            lines.append(f"{i}\n{start} --> {end}\n{seg['text']}\n")
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.logger.info(f"Exported VTT: {vtt_path}")
        return vtt_path
