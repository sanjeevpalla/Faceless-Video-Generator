import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.services.base import BaseService
from app.core.exceptions import ServiceError


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
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.whisper_model = whisper_model
        self.language = language
        self.device = device
        self.subtitles_dir = self.get_output_dir("subtitles")
        self.cache_dir = self.get_output_dir("cache/subtitles")
        self._model = None

    async def execute(self) -> Dict[str, Any]:
        return await self.generate()

    async def generate(self) -> Dict[str, Any]:
        audio_path = self._find_audio_file()
        if not audio_path:
            raise ServiceError(self.service_name, "No audio file found for subtitle generation")

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

    def _find_audio_file(self) -> Optional[Path]:
        audio_dir = self.project_dir / "audio"
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
