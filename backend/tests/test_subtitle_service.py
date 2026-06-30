"""Tests for SubtitleGenerationService."""
import wave
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.subtitle_service import SubtitleGenerationService


def make_wav(path: Path, duration_frames: int = 8000) -> None:
    """Write a minimal valid WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * duration_frames)


class TestSubtitleService:
    # ── Static time-formatting helpers ──────────────────────────────────────

    def test_seconds_to_srt_time_zero(self):
        result = SubtitleGenerationService._seconds_to_srt_time(0.0)
        assert result == "00:00:00,000"

    def test_seconds_to_srt_time_90_seconds(self):
        result = SubtitleGenerationService._seconds_to_srt_time(90.5)
        assert result == "00:01:30,500"

    def test_seconds_to_srt_time_over_one_hour(self):
        result = SubtitleGenerationService._seconds_to_srt_time(3661.123)
        assert result == "01:01:01,123"

    def test_seconds_to_srt_time_millis_precision(self):
        # 1.999 → 999 ms
        result = SubtitleGenerationService._seconds_to_srt_time(1.999)
        assert result == "00:00:01,999"

    def test_seconds_to_vtt_time_zero(self):
        result = SubtitleGenerationService._seconds_to_vtt_time(0.0)
        assert result == "00:00:00.000"

    def test_seconds_to_vtt_time_over_one_hour(self):
        result = SubtitleGenerationService._seconds_to_vtt_time(3661.123)
        assert result == "01:01:01.123"

    def test_seconds_to_vtt_time_millis_precision(self):
        result = SubtitleGenerationService._seconds_to_vtt_time(2.5)
        assert result == "00:00:02.500"

    # ── SRT export ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_export_srt_creates_file(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
            whisper_model="base",
        )
        segments = [
            {"id": 1, "start": 0.0, "end": 3.5, "text": "Hello world"},
            {"id": 2, "start": 3.5, "end": 7.0, "text": "Goodbye world"},
        ]
        path = await svc.export_srt(segments)
        assert path.exists()

    @pytest.mark.asyncio
    async def test_export_srt_content(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        segments = [
            {"id": 1, "start": 0.0, "end": 3.5, "text": "Hello world"},
            {"id": 2, "start": 3.5, "end": 7.0, "text": "Goodbye world"},
        ]
        path = await svc.export_srt(segments)
        content = path.read_text(encoding="utf-8")
        assert "Hello world" in content
        assert "Goodbye world" in content
        assert "00:00:00,000 --> 00:00:03,500" in content
        assert "00:00:03,500 --> 00:00:07,000" in content

    @pytest.mark.asyncio
    async def test_export_srt_sequential_numbers(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        segments = [
            {"id": 1, "start": 0.0, "end": 2.0, "text": "One"},
            {"id": 2, "start": 2.0, "end": 4.0, "text": "Two"},
            {"id": 3, "start": 4.0, "end": 6.0, "text": "Three"},
        ]
        path = await svc.export_srt(segments)
        content = path.read_text(encoding="utf-8")
        # Block numbers 1, 2, 3 must appear
        assert "\n1\n" in content or content.startswith("1\n")
        assert "2\n" in content
        assert "3\n" in content

    # ── VTT export ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_export_vtt_creates_file(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        segments = [{"id": 1, "start": 0.0, "end": 2.0, "text": "Test"}]
        path = await svc.export_vtt(segments)
        assert path.exists()

    @pytest.mark.asyncio
    async def test_export_vtt_header(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        segments = [{"id": 1, "start": 0.0, "end": 2.0, "text": "Test"}]
        path = await svc.export_vtt(segments)
        content = path.read_text(encoding="utf-8")
        assert "WEBVTT" in content

    @pytest.mark.asyncio
    async def test_export_vtt_timestamps(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        segments = [{"id": 1, "start": 0.0, "end": 2.0, "text": "Test"}]
        path = await svc.export_vtt(segments)
        content = path.read_text(encoding="utf-8")
        assert "00:00:00.000 --> 00:00:02.000" in content

    @pytest.mark.asyncio
    async def test_export_vtt_text_content(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        segments = [
            {"id": 1, "start": 0.0, "end": 3.0, "text": "Subtitle line alpha"},
            {"id": 2, "start": 3.0, "end": 6.0, "text": "Subtitle line beta"},
        ]
        path = await svc.export_vtt(segments)
        content = path.read_text(encoding="utf-8")
        assert "Subtitle line alpha" in content
        assert "Subtitle line beta" in content

    # ── Audio file detection ─────────────────────────────────────────────────

    def test_find_audio_file_returns_none_when_empty(self, tmp_project_dir):
        svc = SubtitleGenerationService("test", tmp_project_dir)
        # audio dir exists (created by fixture) but is empty
        result = svc._find_audio_file()
        assert result is None

    def test_find_audio_file_finds_wav(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        wav = audio_dir / "scene_001.wav"
        make_wav(wav)
        svc = SubtitleGenerationService("test", tmp_project_dir)
        found = svc._find_audio_file()
        assert found is not None
        assert found.suffix == ".wav"

    def test_find_audio_file_prefers_merged(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav")
        merged = audio_dir / "narration_merged.wav"
        make_wav(merged)

        svc = SubtitleGenerationService("test", tmp_project_dir)
        found = svc._find_audio_file()
        assert found is not None
        assert "merged" in found.name

    def test_find_audio_file_prefers_narration(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav")
        narration = audio_dir / "narration.wav"
        make_wav(narration)

        svc = SubtitleGenerationService("test", tmp_project_dir)
        found = svc._find_audio_file()
        assert found is not None
        assert "narration" in found.name

    # ── Audio hashing ────────────────────────────────────────────────────────

    def test_hash_audio_deterministic(self, tmp_project_dir):
        svc = SubtitleGenerationService("test", tmp_project_dir)
        path = tmp_project_dir / "audio" / "test.wav"
        make_wav(path)
        h1 = svc._hash_audio(path)
        h2 = svc._hash_audio(path)
        assert h1 == h2

    def test_hash_audio_changes_with_content(self, tmp_project_dir):
        svc = SubtitleGenerationService("test", tmp_project_dir)
        path = tmp_project_dir / "audio" / "test.wav"
        path.write_bytes(b"content_v1")
        h1 = svc._hash_audio(path)
        path.write_bytes(b"content_v2_different")
        h2 = svc._hash_audio(path)
        assert h1 != h2

    def test_hash_audio_length(self, tmp_project_dir):
        svc = SubtitleGenerationService("test", tmp_project_dir)
        path = tmp_project_dir / "audio" / "test.wav"
        make_wav(path)
        h = svc._hash_audio(path)
        assert len(h) == 16

    # ── Cache logic ──────────────────────────────────────────────────────────

    def test_check_cache_miss(self, tmp_project_dir):
        svc = SubtitleGenerationService("test", tmp_project_dir)
        result = svc.check_cache("nonexistent_xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_cache_hit(self, tmp_project_dir):
        import json
        svc = SubtitleGenerationService("test", tmp_project_dir)

        # First produce real SRT and VTT files
        segments = [{"id": 1, "start": 0.0, "end": 2.0, "text": "Cached segment"}]
        srt_path = await svc.export_srt(segments)
        vtt_path = await svc.export_vtt(segments)

        cache_data = {
            "srt_path": str(srt_path),
            "vtt_path": str(vtt_path),
            "segment_count": 1,
            "audio_hash": "cache_hit_hash",
            "segments": segments,
        }
        cache_file = svc.cache_dir / "cache_hit_hash.json"
        cache_file.write_text(json.dumps(cache_data))

        result = svc.check_cache("cache_hit_hash")
        assert result is not None
        assert result["segment_count"] == 1
