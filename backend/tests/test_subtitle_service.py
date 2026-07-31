"""Tests for SubtitleGenerationService."""
import json
import wave
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.subtitle_service import SubtitleGenerationService


def make_wav(path: Path, duration_frames: int = 8000, framerate: int = 8000) -> None:
    """Write a minimal valid WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
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

    # ── Known-text subtitles (bypasses Whisper for TTS-generated narration) ──

    def test_scene_based_segments_uses_exact_narration_text(self, tmp_project_dir):
        """The known scenes.json narration text must be used verbatim, not
        re-derived via ASR — this is the fix for Whisper hallucinating wrong
        text/script for lower-resource languages like Telugu."""
        scenes = [
            {"scene_id": 1, "narration": "తన సృష్టికర్తలనే తెలివితేటలతో ఓడించిన AI", "duration": 5},
            {"scene_id": 2, "narration": "రెండవ దృశ్యం ఇక్కడ ఉంది", "duration": 5},
        ]
        (tmp_project_dir / "input" / "scenes.json").write_text(
            json.dumps({"scenes": scenes}), encoding="utf-8"
        )
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav", duration_frames=8000, framerate=8000)  # 1.0s
        make_wav(audio_dir / "scene_002.wav", duration_frames=16000, framerate=8000)  # 2.0s

        svc = SubtitleGenerationService(project_id="test", project_dir=tmp_project_dir)
        segments = svc._scene_based_segments(svc._scenes_json_path(), audio_dir)

        assert segments is not None
        texts = [s["text"] for s in segments]
        assert "తన సృష్టికర్తలనే తెలివితేటలతో ఓడించిన AI" in texts
        assert "రెండవ దృశ్యం ఇక్కడ ఉంది" in texts

    def test_scene_based_segments_timed_to_actual_scene_durations(self, tmp_project_dir):
        scenes = [
            {"scene_id": 1, "narration": "First scene text", "duration": 5},
            {"scene_id": 2, "narration": "Second scene text", "duration": 5},
        ]
        (tmp_project_dir / "input" / "scenes.json").write_text(
            json.dumps({"scenes": scenes}), encoding="utf-8"
        )
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav", duration_frames=8000, framerate=8000)   # 1.0s
        make_wav(audio_dir / "scene_002.wav", duration_frames=24000, framerate=8000)  # 3.0s

        svc = SubtitleGenerationService(project_id="test", project_dir=tmp_project_dir)
        segments = svc._scene_based_segments(svc._scenes_json_path(), audio_dir)

        assert segments[0]["start"] == pytest.approx(0.0, abs=0.01)
        assert segments[0]["end"] == pytest.approx(1.0, abs=0.01)
        # Second scene starts exactly where the first (1.0s) ends
        assert segments[1]["start"] == pytest.approx(1.0, abs=0.01)
        assert segments[1]["end"] == pytest.approx(4.0, abs=0.01)

    def test_scene_based_segments_skips_empty_narration(self, tmp_project_dir):
        """Filler/silent scenes should produce no subtitle entry."""
        scenes = [
            {"scene_id": 1, "narration": "Only this scene has text", "duration": 5},
            {"scene_id": 2, "narration": "", "duration": 5},
        ]
        (tmp_project_dir / "input" / "scenes.json").write_text(
            json.dumps({"scenes": scenes}), encoding="utf-8"
        )
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav")
        make_wav(audio_dir / "scene_002.wav")

        svc = SubtitleGenerationService(project_id="test", project_dir=tmp_project_dir)
        segments = svc._scene_based_segments(svc._scenes_json_path(), audio_dir)

        assert len(segments) == 1
        assert segments[0]["text"] == "Only this scene has text"

    def test_scene_based_segments_none_without_scene_wavs(self, tmp_project_dir):
        """No per-scene WAVs (e.g. a single uploaded narration file) — no
        reliable per-line timing, so this must fall back to Whisper (None)."""
        scenes = [{"scene_id": 1, "narration": "Some text", "duration": 5}]
        (tmp_project_dir / "input" / "scenes.json").write_text(
            json.dumps({"scenes": scenes}), encoding="utf-8"
        )
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "narration_merged.wav")  # uploaded, no scene_*.wav

        svc = SubtitleGenerationService(project_id="test", project_dir=tmp_project_dir)
        result = svc._scene_based_segments(svc._scenes_json_path(), audio_dir)
        assert result is None

    def test_scene_based_segments_none_without_scenes_json(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav")
        svc = SubtitleGenerationService(project_id="test", project_dir=tmp_project_dir)
        result = svc._scene_based_segments(svc._scenes_json_path(), audio_dir)
        assert result is None

    def test_is_primary_true_without_audio_dir_override(self, tmp_project_dir):
        svc = SubtitleGenerationService(project_id="test", project_dir=tmp_project_dir)
        assert svc._is_primary() is True
        assert svc._scenes_json_path() == tmp_project_dir / "input" / "scenes.json"

    def test_is_primary_false_with_audio_dir_override(self, tmp_project_dir):
        svc = SubtitleGenerationService(
            project_id="test", project_dir=tmp_project_dir, language="te",
            audio_dir_override=tmp_project_dir / "audio" / "te",
        )
        assert svc._is_primary() is False
        assert svc._scenes_json_path() == tmp_project_dir / "input" / "te" / "scenes.json"

    def test_split_narration_short_text_single_chunk(self):
        result = SubtitleGenerationService._split_narration("Short line.", 0.0, 5.0)
        assert len(result) == 1
        assert result[0][0] == "Short line."
        assert result[0][1] == 0.0
        assert result[0][2] == 5.0

    def test_split_narration_splits_long_text_proportionally(self):
        text = "First sentence here. " + ("Second sentence is much much longer than the first one here. ")
        result = SubtitleGenerationService._split_narration(text.strip(), 0.0, 10.0)
        assert len(result) >= 2
        # Chunks should be contiguous and end exactly at the scene's end time
        assert result[0][1] == pytest.approx(0.0, abs=0.01)
        assert result[-1][2] == pytest.approx(10.0, abs=0.01)
        for a, b in zip(result, result[1:]):
            assert a[2] == pytest.approx(b[1], abs=0.01)

    @pytest.mark.asyncio
    async def test_generate_uses_scene_text_over_whisper(self, tmp_project_dir):
        """End-to-end: generate() should return the known-text path and never
        touch Whisper when per-scene audio + scenes.json are both present."""
        scenes = [{"scene_id": 1, "narration": "Exact known narration", "duration": 5}]
        (tmp_project_dir / "input" / "scenes.json").write_text(
            json.dumps({"scenes": scenes}), encoding="utf-8"
        )
        audio_dir = tmp_project_dir / "audio"
        make_wav(audio_dir / "scene_001.wav")

        svc = SubtitleGenerationService(project_id="test", project_dir=tmp_project_dir)

        async def _boom(*args, **kwargs):
            raise AssertionError("Whisper should not be invoked when scene text is available")
        svc._load_model = _boom  # type: ignore[assignment]

        result = await svc.generate()
        assert result["source"] == "scene_text"
        assert result["segment_count"] == 1
        assert "Exact known narration" in Path(result["srt_path"]).read_text(encoding="utf-8")
