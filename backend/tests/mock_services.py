"""
Mock service implementations for testing without real hardware.
These replace ComfyUI/Piper/Whisper with deterministic fast stubs.
"""
import asyncio
import json
import struct
import wave
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.image_service import ImageGenerationService
from app.services.voice_service import VoiceGenerationService
from app.services.subtitle_service import SubtitleGenerationService


def _make_minimal_png(width: int = 4, height: int = 4) -> bytes:
    """Return a minimal valid PNG (solid black, RGB, no transparency)."""

    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    # One row: filter byte (0=None) + width RGB pixels (all black)
    raw_row = b"\x00" + b"\x00\x00\x00" * width
    raw = raw_row * height

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return png


class MockImageGenerationService(ImageGenerationService):
    """Generates minimal valid PNG placeholders instead of calling ComfyUI."""

    async def submit_to_comfyui(self, workflow: Dict[str, Any]) -> str:
        return "mock-prompt-id"

    async def poll_comfyui_job(
        self, job_id: str, timeout: int = 300, poll_interval: float = 2.0
    ) -> List[str]:
        return ["mock://image"]

    async def download_image(self, url: str, dest_path: Path) -> None:
        dest_path.write_bytes(_make_minimal_png())

    async def generate_scene(
        self,
        scene_id: Any,
        prompt: str,
        negative_prompt: str = "",
    ) -> Dict[str, Any]:
        await asyncio.sleep(0.01)  # simulate tiny delay
        dest_path = self.images_dir / f"scene_{int(scene_id):03d}.png"
        dest_path.write_bytes(_make_minimal_png())
        h = self._hash_prompt(prompt)
        result: Dict[str, Any] = {
            "scene_id": scene_id,
            "path": str(dest_path),
            "filename": dest_path.name,
            "prompt_hash": h,
        }
        cache_file = self.cache_dir / f"{h}.json"
        cache_file.write_text(json.dumps(result))
        return result


class MockVoiceGenerationService(VoiceGenerationService):
    """Generates silence WAV files instead of calling Piper."""

    async def _run_piper(self, text: str, output_path: Path) -> None:
        await asyncio.sleep(0.01)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            frames = max(22050, len(text) * 2205)
            wf.writeframes(b"\x00\x00" * frames)

    async def _run_piper_batch(self, texts: List[str], output_dir: Path) -> List[Path]:
        paths = []
        for i, text in enumerate(texts):
            await asyncio.sleep(0.01)
            p = output_dir / f"{i:03d}.wav"
            with wave.open(str(p), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(22050)
                frames = max(22050, len(text) * 2205)
                wf.writeframes(b"\x00\x00" * frames)
            paths.append(p)
        return paths

    async def merge_audio_files(
        self, audio_files: List[Dict[str, Any]]
    ) -> Optional[Path]:
        """Concatenate all WAV files into merged output without requiring FFmpeg."""
        if not audio_files:
            return None

        sorted_files = sorted(audio_files, key=lambda x: x.get("scene_id", 0))
        merged_path = self.audio_dir / "narration_merged.wav"
        all_frames = b""
        params = None

        for af in sorted_files:
            p = Path(af["path"])
            if p.exists():
                with wave.open(str(p), "rb") as wf:
                    if params is None:
                        params = wf.getparams()
                    all_frames += wf.readframes(wf.getnframes())

        if params and all_frames:
            with wave.open(str(merged_path), "wb") as wf:
                wf.setparams(params)
                wf.writeframes(all_frames)
            return merged_path

        return None


class MockSubtitleGenerationService(SubtitleGenerationService):
    """Returns deterministic mock segments without loading Whisper."""

    async def _load_model(self):
        return None

    async def _transcribe(
        self, model: Any, audio_path: Path
    ) -> List[Dict[str, Any]]:
        return [
            {"id": 1, "start": 0.0, "end": 3.0, "text": "Mock subtitle line one."},
            {"id": 2, "start": 3.0, "end": 6.0, "text": "Mock subtitle line two."},
            {"id": 3, "start": 6.0, "end": 9.0, "text": "Mock subtitle line three."},
        ]
