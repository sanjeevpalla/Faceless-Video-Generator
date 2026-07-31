"""Tests for DurationSyncService."""
import wave
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.duration_sync_service import DurationSyncService, _wav_duration


PROJECT_ID = "test-duration-sync-001"
SR = 8000


def make_wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(b"\x01\x00" * int(seconds * SR))


class TestDurationSyncService:
    async def test_single_language_noop(self, tmp_project_dir):
        svc = DurationSyncService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            languages=["en"], project_language="en",
        )
        result = await svc.sync()
        assert result == {"scenes_padded": 0, "sections": 0}

    async def test_pads_shorter_language_to_match_longer(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        te_dir = audio_dir / "te"

        make_wav(audio_dir / "scene_001.wav", 3.0)   # English, primary
        make_wav(te_dir / "scene_001.wav", 5.0)       # Telugu, longer

        svc = DurationSyncService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            languages=["en", "te"], project_language="en",
        )
        result = await svc.sync()

        assert result["scenes_padded"] == 1
        en_dur = _wav_duration(audio_dir / "scene_001.wav")
        te_dur = _wav_duration(te_dir / "scene_001.wav")
        assert en_dur == pytest.approx(5.0, abs=0.05)
        assert te_dur == pytest.approx(5.0, abs=0.05)

    async def test_ignores_negligible_difference(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        te_dir = audio_dir / "te"

        make_wav(audio_dir / "scene_001.wav", 3.00)
        make_wav(te_dir / "scene_001.wav", 3.01)  # under MIN_PAD_SECONDS

        svc = DurationSyncService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            languages=["en", "te"], project_language="en",
        )
        result = await svc.sync()
        assert result["scenes_padded"] == 0

    async def test_remerges_narration_after_padding(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        te_dir = audio_dir / "te"

        make_wav(audio_dir / "scene_001.wav", 2.0)
        make_wav(audio_dir / "scene_002.wav", 2.0)
        make_wav(te_dir / "scene_001.wav", 3.0)
        make_wav(te_dir / "scene_002.wav", 1.0)

        svc = DurationSyncService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            languages=["en", "te"], project_language="en",
        )
        await svc.sync()

        merged_en = audio_dir / "narration_merged.wav"
        merged_te = te_dir / "narration_merged.wav"
        assert merged_en.exists()
        assert merged_te.exists()
        # Both languages: scene1(target 3.0) + scene2(target 2.0) = 5.0s total
        assert _wav_duration(merged_en) == pytest.approx(5.0, abs=0.1)
        assert _wav_duration(merged_te) == pytest.approx(5.0, abs=0.1)

    async def test_ai_news_section_layout(self, tmp_project_dir):
        audio_dir = tmp_project_dir / "audio"
        te_dir = audio_dir / "te"

        make_wav(audio_dir / "sections" / "story_01" / "scene_001.wav", 2.0)
        make_wav(te_dir / "sections" / "story_01" / "scene_001.wav", 4.0)

        svc = DurationSyncService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            languages=["en", "te"], project_language="en",
        )
        result = await svc.sync()

        assert result["sections"] == 1
        assert result["scenes_padded"] == 1
        assert (audio_dir / "sections" / "story_01" / "narration.wav").exists()
        en_dur = _wav_duration(audio_dir / "sections" / "story_01" / "scene_001.wav")
        assert en_dur == pytest.approx(4.0, abs=0.05)

    def test_service_name(self, tmp_project_dir):
        svc = DurationSyncService(
            project_id=PROJECT_ID, project_dir=tmp_project_dir,
            languages=["en"], project_language="en",
        )
        assert svc.service_name == "duration_sync"
