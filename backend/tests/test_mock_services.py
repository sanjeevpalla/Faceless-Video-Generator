"""Tests that exercise the mock service stubs end-to-end without hardware."""
import json
import wave
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.mock_services import (
    MockImageGenerationService,
    MockVoiceGenerationService,
    MockSubtitleGenerationService,
)


def make_wav(path: Path, duration_frames: int = 8000) -> None:
    """Write a minimal valid WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * duration_frames)


class TestMockImageService:
    @pytest.mark.asyncio
    async def test_mock_generates_images(self, tmp_project_dir, image_prompts_txt):
        svc = MockImageGenerationService(
            project_id="mock-test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        result = await svc.generate_all()
        assert result["total"] == 3
        assert result["generated"] == 3
        assert result["failed"] == []

    @pytest.mark.asyncio
    async def test_mock_generated_files_exist(self, tmp_project_dir, image_prompts_txt):
        svc = MockImageGenerationService(
            project_id="mock-test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        result = await svc.generate_all()
        for img in result["images"]:
            assert Path(img["path"]).exists()

    @pytest.mark.asyncio
    async def test_mock_generated_files_are_valid_png(
        self, tmp_project_dir, image_prompts_txt
    ):
        svc = MockImageGenerationService(
            project_id="mock-test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        result = await svc.generate_all()
        for img in result["images"]:
            data = Path(img["path"]).read_bytes()
            # PNG magic bytes
            assert data[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_mock_image_cache_written(self, tmp_project_dir, image_prompts_txt):
        svc = MockImageGenerationService(
            project_id="mock-test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        result = await svc.generate_all()
        cache_dir = tmp_project_dir / "cache" / "images"
        cache_files = list(cache_dir.glob("*.json"))
        assert len(cache_files) == 3

    @pytest.mark.asyncio
    async def test_mock_generate_scene_directly(self, tmp_project_dir):
        svc = MockImageGenerationService(
            project_id="mock-scene",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        result = await svc.generate_scene(42, "A test prompt for scene generation", "")
        assert result["scene_id"] == 42
        assert Path(result["path"]).exists()
        assert Path(result["path"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_mock_manifest_written(self, tmp_project_dir, image_prompts_txt):
        svc = MockImageGenerationService(
            project_id="mock-manifest",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        await svc.generate_all()
        manifest = json.loads(
            (tmp_project_dir / "images" / "manifest.json").read_text()
        )
        assert manifest["total"] == 3
        assert manifest["generated"] == 3


class TestMockVoiceService:
    @pytest.mark.asyncio
    async def test_mock_generates_wav_files(self, tmp_project_dir, scenes_json):
        svc = MockVoiceGenerationService(
            project_id="mock-voice",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate_all()
        assert result["total"] == 3
        assert result["generated"] == 3

    @pytest.mark.asyncio
    async def test_mock_wav_files_exist(self, tmp_project_dir, scenes_json):
        svc = MockVoiceGenerationService(
            project_id="mock-voice",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate_all()
        for af in result["audio_files"]:
            assert Path(af["path"]).exists()

    @pytest.mark.asyncio
    async def test_mock_wav_files_readable(self, tmp_project_dir, scenes_json):
        svc = MockVoiceGenerationService(
            project_id="mock-voice",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate_all()
        for af in result["audio_files"]:
            p = Path(af["path"])
            assert p.exists()
            with wave.open(str(p), "rb") as wf:
                assert wf.getnframes() > 0

    @pytest.mark.asyncio
    async def test_mock_produces_merged_audio(self, tmp_project_dir, scenes_json):
        svc = MockVoiceGenerationService(
            project_id="mock-voice",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate_all()
        assert result["merged_audio"] is not None
        assert Path(result["merged_audio"]).exists()

    @pytest.mark.asyncio
    async def test_mock_merged_wav_readable(self, tmp_project_dir, scenes_json):
        svc = MockVoiceGenerationService(
            project_id="mock-voice",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate_all()
        merged_path = Path(result["merged_audio"])
        with wave.open(str(merged_path), "rb") as wf:
            assert wf.getnframes() > 0

    @pytest.mark.asyncio
    async def test_mock_audio_durations_positive(self, tmp_project_dir, scenes_json):
        svc = MockVoiceGenerationService(
            project_id="mock-voice",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate_all()
        for af in result["audio_files"]:
            assert af["duration"] > 0.0

    @pytest.mark.asyncio
    async def test_mock_manifest_written(self, tmp_project_dir, scenes_json):
        svc = MockVoiceGenerationService(
            project_id="mock-manifest-voice",
            project_dir=tmp_project_dir,
        )
        await svc.generate_all()
        manifest_path = tmp_project_dir / "audio" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["total"] == 3


class TestMockSubtitleService:
    @pytest.mark.asyncio
    async def test_mock_generates_srt_and_vtt(self, tmp_project_dir):
        # Create a fake merged audio for the service to find
        audio_dir = tmp_project_dir / "audio"
        merged = audio_dir / "narration_merged.wav"
        make_wav(merged)

        svc = MockSubtitleGenerationService(
            project_id="mock-sub",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate()
        assert result["segment_count"] == 3
        assert Path(result["srt_path"]).exists()
        assert Path(result["vtt_path"]).exists()

    @pytest.mark.asyncio
    async def test_mock_srt_content(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "narration_merged.wav")

        svc = MockSubtitleGenerationService(
            project_id="mock-sub-content",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate()
        srt = Path(result["srt_path"]).read_text(encoding="utf-8")
        assert "Mock subtitle line one" in srt
        assert "Mock subtitle line two" in srt
        assert "Mock subtitle line three" in srt

    @pytest.mark.asyncio
    async def test_mock_vtt_has_webvtt_header(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "narration_merged.wav")

        svc = MockSubtitleGenerationService(
            project_id="mock-sub-vtt",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate()
        vtt = Path(result["vtt_path"]).read_text(encoding="utf-8")
        assert "WEBVTT" in vtt

    @pytest.mark.asyncio
    async def test_mock_no_audio_raises(self, tmp_project_dir):
        """Should raise ServiceError when no audio file is found."""
        from app.core.exceptions import ServiceError
        svc = MockSubtitleGenerationService(
            project_id="mock-sub-no-audio",
            project_dir=tmp_project_dir,
        )
        # audio dir is empty (no WAV files)
        with pytest.raises(ServiceError, match="No audio file found"):
            await svc.generate()

    @pytest.mark.asyncio
    async def test_mock_prefers_merged_audio(self, tmp_project_dir):
        """Service should pick narration_merged.wav over individual scene files."""
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav")
        make_wav(audio_dir / "narration_merged.wav")

        svc = MockSubtitleGenerationService(
            project_id="mock-prefer-merged",
            project_dir=tmp_project_dir,
        )
        # Just check it finds and uses the merged file without error
        found = svc._find_audio_file()
        assert found is not None
        assert "merged" in found.name

    @pytest.mark.asyncio
    async def test_mock_cache_written(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "narration_merged.wav")

        svc = MockSubtitleGenerationService(
            project_id="mock-cache-sub",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate()
        cache_files = list(svc.cache_dir.glob("*.json"))
        assert len(cache_files) == 1
        cached = json.loads(cache_files[0].read_text())
        assert cached["segment_count"] == 3
