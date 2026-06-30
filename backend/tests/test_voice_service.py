"""Tests for VoiceGenerationService."""
import asyncio
import json
import wave
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.voice_service import VoiceGenerationService
from app.core.exceptions import ServiceError


PROJECT_ID = "test-voice-001"


def make_wav(path: Path, duration_frames: int = 8000) -> None:
    """Write a minimal valid WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * duration_frames)


@pytest.fixture
def voice_service(tmp_project_dir):
    return VoiceGenerationService(
        project_id=PROJECT_ID,
        project_dir=tmp_project_dir,
        piper_executable="piper",
        model_path="",
        speed=1.0,
    )


class TestVoiceGenerationService:
    def test_hash_text_deterministic(self, voice_service):
        h1 = voice_service._hash_text("Hello world")
        h2 = voice_service._hash_text("Hello world")
        assert h1 == h2

    def test_hash_text_length(self, voice_service):
        h = voice_service._hash_text("Hello world")
        assert len(h) == 16

    def test_hash_text_different(self, voice_service):
        assert voice_service._hash_text("A") != voice_service._hash_text("B")

    def test_hash_text_includes_model_path(self, tmp_project_dir):
        svc_a = VoiceGenerationService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            model_path="/model_a.onnx",
        )
        svc_b = VoiceGenerationService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            model_path="/model_b.onnx",
        )
        assert svc_a._hash_text("same text") != svc_b._hash_text("same text")

    def test_hash_text_includes_speed(self, tmp_project_dir):
        svc_a = VoiceGenerationService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir, speed=1.0,
        )
        svc_b = VoiceGenerationService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir, speed=1.5,
        )
        assert svc_a._hash_text("same text") != svc_b._hash_text("same text")

    def test_check_cache_miss(self, voice_service):
        result = voice_service.check_cache("nonexistent_hash_xyz", 1)
        assert result is None

    def test_check_cache_hit(self, voice_service, tmp_project_dir):
        cache_dir = tmp_project_dir / "cache" / "audio"
        fake_wav = tmp_project_dir / "audio" / "scene_001.wav"
        fake_wav.parent.mkdir(parents=True, exist_ok=True)
        make_wav(fake_wav)
        entry = {
            "scene_id": 1,
            "path": str(fake_wav),
            "filename": fake_wav.name,
            "duration": 3.5,
        }
        (cache_dir / "hit_hash.json").write_text(json.dumps(entry))

        result = voice_service.check_cache("hit_hash", 1)
        assert result is not None
        assert result["duration"] == 3.5

    def test_check_cache_stale_missing_file(self, voice_service, tmp_project_dir):
        cache_dir = tmp_project_dir / "cache" / "audio"
        entry = {
            "scene_id": 1,
            "path": str(tmp_project_dir / "audio" / "nonexistent.wav"),
            "filename": "nonexistent.wav",
            "duration": 2.0,
        }
        (cache_dir / "stale_hash.json").write_text(json.dumps(entry))
        result = voice_service.check_cache("stale_hash", 1)
        assert result is None

    def test_check_cache_corrupt_json(self, voice_service, tmp_project_dir):
        cache_dir = tmp_project_dir / "cache" / "audio"
        (cache_dir / "bad_hash.json").write_text("{broken")
        result = voice_service.check_cache("bad_hash", 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_all_no_scenes_file(self, voice_service):
        with pytest.raises(ServiceError, match="scenes.json not found"):
            await voice_service.generate_all()

    @pytest.mark.asyncio
    async def test_generate_all_empty_scenes(self, voice_service, tmp_project_dir):
        (tmp_project_dir / "input" / "scenes.json").write_text(
            json.dumps({"scenes": []})
        )
        with pytest.raises(ServiceError, match="No scenes found"):
            await voice_service.generate_all()

    @pytest.mark.asyncio
    async def test_generate_all_resumes_existing_audio(
        self, voice_service, tmp_project_dir, scenes_json
    ):
        """Already-generated .wav files should be skipped."""
        audio_dir = tmp_project_dir / "audio"
        for i in range(1, 4):
            make_wav(audio_dir / f"scene_{i:03d}.wav")

        result = await voice_service.generate_all()
        assert result["generated"] == 3
        assert all(r.get("resumed") for r in result["audio_files"])

    @pytest.mark.asyncio
    async def test_generate_all_partial_resume(self, tmp_project_dir, scenes_json):
        """Only the scene without an existing WAV should call _run_piper_batch."""
        audio_dir = tmp_project_dir / "audio"
        for i in [1, 2]:
            make_wav(audio_dir / f"scene_{i:03d}.wav")

        piper_calls = []

        async def mock_run_piper_batch(texts, output_dir):
            piper_calls.extend(texts)
            paths = []
            for i, _ in enumerate(texts):
                p = output_dir / f"{i:03d}.wav"
                make_wav(p)
                paths.append(p)
            return paths

        svc = VoiceGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
        )
        svc._run_piper_batch = mock_run_piper_batch

        result = await svc.generate_all()
        assert result["generated"] == 3
        assert len(piper_calls) == 1  # only scene 3 synthesised

    @pytest.mark.asyncio
    async def test_generate_all_skips_empty_narration(self, tmp_project_dir):
        """Scenes with empty narration text should be skipped gracefully."""
        scenes = {
            "scenes": [
                {"scene_id": 1, "narration": "Hello this is valid text", "duration": 5},
                {"scene_id": 2, "narration": "", "duration": 5},  # empty
                {"scene_id": 3, "narration": "  ", "duration": 5},  # whitespace
            ]
        }
        (tmp_project_dir / "input" / "scenes.json").write_text(json.dumps(scenes))

        piper_calls = []

        async def mock_run_piper_batch(texts, output_dir):
            piper_calls.extend(texts)
            paths = []
            for i, _ in enumerate(texts):
                p = output_dir / f"{i:03d}.wav"
                make_wav(p)
                paths.append(p)
            return paths

        svc = VoiceGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
        )
        svc._run_piper_batch = mock_run_piper_batch

        result = await svc.generate_all()
        # Only scene 1 has valid text
        assert len(piper_calls) == 1
        assert "Hello this is valid text" in piper_calls[0]

    @pytest.mark.asyncio
    async def test_generate_all_records_failures(self, tmp_project_dir, scenes_json):
        """A failing _run_piper_batch should record all scenes as failed."""
        async def mock_run_piper_batch(texts, output_dir):
            raise RuntimeError("Piper binary not found")

        svc = VoiceGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
        )
        svc._run_piper_batch = mock_run_piper_batch

        result = await svc.generate_all()
        assert result["generated"] == 0
        assert len(result["failed"]) == 3

    @pytest.mark.asyncio
    async def test_generate_all_manifest_written(self, tmp_project_dir, scenes_json):
        """manifest.json must be present in audio dir after generate_all."""
        audio_dir = tmp_project_dir / "audio"
        for i in range(1, 4):
            make_wav(audio_dir / f"scene_{i:03d}.wav")

        svc = VoiceGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
        )
        await svc.generate_all()

        manifest_path = audio_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["total"] == 3
        assert manifest["generated"] == 3

    def test_service_name(self, voice_service):
        assert voice_service.service_name == "voice_generation"

    def test_audio_dir_created(self, tmp_project_dir):
        svc = VoiceGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
        )
        assert svc.audio_dir.exists()

    def test_cache_dir_created(self, tmp_project_dir):
        svc = VoiceGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
        )
        assert svc.cache_dir.exists()
