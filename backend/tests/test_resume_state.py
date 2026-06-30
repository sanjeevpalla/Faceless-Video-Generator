"""Tests for resume-state behaviour (services skip already-completed work)."""
import json
import wave
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.voice_service import VoiceGenerationService
from app.services.image_service import ImageGenerationService


def make_wav(path: Path, duration_frames: int = 8000) -> None:
    """Write a minimal valid WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * duration_frames)


class TestResumeState:
    # ── ImageGenerationService ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_image_service_resumes_partial(
        self, tmp_project_dir, image_prompts_txt
    ):
        """If scene_001.png and scene_002.png exist, only scene_003 should be generated."""
        images_dir = tmp_project_dir / "images"
        for i in [1, 2]:
            p = images_dir / f"scene_{i:03d}.png"
            p.write_bytes(b"\x89PNG fake")

        svc = ImageGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )

        called_scenes = []

        async def mock_generate_scene(scene_id, prompt, neg=""):
            called_scenes.append(scene_id)
            out = images_dir / f"scene_{int(scene_id):03d}.png"
            out.write_bytes(b"\x89PNG mock")
            return {
                "scene_id": scene_id,
                "path": str(out),
                "filename": out.name,
                "prompt_hash": "mock",
            }

        svc.generate_scene = mock_generate_scene
        result = await svc.generate_all()

        assert result["total"] == 3
        assert result["generated"] == 3
        assert called_scenes == [3]  # only scene 3 was actually generated

    @pytest.mark.asyncio
    async def test_image_service_all_existing_skips_all_calls(
        self, tmp_project_dir, image_prompts_txt
    ):
        """If all images already exist, generate_scene should never be called."""
        images_dir = tmp_project_dir / "images"
        for i in range(1, 4):
            (images_dir / f"scene_{i:03d}.png").write_bytes(b"\x89PNG fake")

        svc = ImageGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )

        called_scenes = []

        async def mock_generate_scene(scene_id, prompt, neg=""):
            called_scenes.append(scene_id)
            return {"scene_id": scene_id, "path": "", "filename": "", "prompt_hash": ""}

        svc.generate_scene = mock_generate_scene
        result = await svc.generate_all()

        assert called_scenes == []
        assert result["generated"] == 3
        assert all(r.get("resumed") for r in result["images"])

    @pytest.mark.asyncio
    async def test_image_service_no_existing_generates_all(
        self, tmp_project_dir, image_prompts_txt
    ):
        """If no images exist, all scenes must be generated."""
        images_dir = tmp_project_dir / "images"

        svc = ImageGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )

        called_scenes = []

        async def mock_generate_scene(scene_id, prompt, neg=""):
            called_scenes.append(scene_id)
            out = images_dir / f"scene_{int(scene_id):03d}.png"
            out.write_bytes(b"\x89PNG mock")
            return {
                "scene_id": scene_id,
                "path": str(out),
                "filename": out.name,
                "prompt_hash": "mock",
            }

        svc.generate_scene = mock_generate_scene
        result = await svc.generate_all()

        assert sorted(called_scenes) == [1, 2, 3]
        assert result["total"] == 3
        assert result["generated"] == 3

    @pytest.mark.asyncio
    async def test_image_service_resumed_entries_marked(
        self, tmp_project_dir, image_prompts_txt
    ):
        """Resumed entries must carry resumed=True; newly generated must not."""
        images_dir = tmp_project_dir / "images"
        # Only scene 1 pre-exists
        (images_dir / "scene_001.png").write_bytes(b"\x89PNG existing")

        svc = ImageGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )

        async def mock_generate_scene(scene_id, prompt, neg=""):
            out = images_dir / f"scene_{int(scene_id):03d}.png"
            out.write_bytes(b"\x89PNG new")
            return {
                "scene_id": scene_id,
                "path": str(out),
                "filename": out.name,
                "prompt_hash": "new_hash",
            }

        svc.generate_scene = mock_generate_scene
        result = await svc.generate_all()

        resumed_ids = [r["scene_id"] for r in result["images"] if r.get("resumed")]
        new_ids = [r["scene_id"] for r in result["images"] if not r.get("resumed")]
        assert 1 in resumed_ids
        assert 2 in new_ids
        assert 3 in new_ids

    # ── VoiceGenerationService ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_voice_service_resumes_partial(self, tmp_project_dir, scenes_json):
        """If scene_001.wav and scene_002.wav exist, only scene_003 should run Piper."""
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
            project_id="test",
            project_dir=tmp_project_dir,
        )
        svc._run_piper_batch = mock_run_piper_batch

        result = await svc.generate_all()
        assert result["generated"] == 3
        assert len(piper_calls) == 1  # only 1 scene synthesised

    @pytest.mark.asyncio
    async def test_voice_service_all_existing_skips_piper(
        self, tmp_project_dir, scenes_json
    ):
        """If all WAVs already exist, Piper should never be called."""
        audio_dir = tmp_project_dir / "audio"
        for i in range(1, 4):
            make_wav(audio_dir / f"scene_{i:03d}.wav")

        piper_calls = []

        async def mock_run_piper_batch(texts, output_dir):
            piper_calls.extend(texts)
            return []

        svc = VoiceGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        svc._run_piper_batch = mock_run_piper_batch

        result = await svc.generate_all()
        assert piper_calls == []
        assert result["generated"] == 3
        assert all(r.get("resumed") for r in result["audio_files"])

    @pytest.mark.asyncio
    async def test_voice_service_no_existing_generates_all(
        self, tmp_project_dir, scenes_json
    ):
        """If no WAVs exist, all scenes must pass through Piper batch."""
        audio_dir = tmp_project_dir / "audio"
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
            project_id="test",
            project_dir=tmp_project_dir,
        )
        svc._run_piper_batch = mock_run_piper_batch

        result = await svc.generate_all()
        assert len(piper_calls) == 3
        assert result["generated"] == 3

    @pytest.mark.asyncio
    async def test_voice_service_zero_size_wav_is_not_resumed(
        self, tmp_project_dir, scenes_json
    ):
        """A zero-byte WAV file must NOT be treated as already generated."""
        audio_dir = tmp_project_dir / "audio"
        # Write zero-byte files (simulate partial/failed previous run)
        for i in range(1, 4):
            (audio_dir / f"scene_{i:03d}.wav").write_bytes(b"")

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
            project_id="test",
            project_dir=tmp_project_dir,
        )
        svc._run_piper_batch = mock_run_piper_batch

        result = await svc.generate_all()
        # All 3 scenes should regenerate since size==0
        assert len(piper_calls) == 3

    @pytest.mark.asyncio
    async def test_voice_service_resumed_entries_have_duration(
        self, tmp_project_dir, scenes_json
    ):
        """Resumed audio entries must include a duration field derived from the WAV."""
        audio_dir = tmp_project_dir / "audio"
        for i in range(1, 4):
            make_wav(audio_dir / f"scene_{i:03d}.wav", duration_frames=16000)

        svc = VoiceGenerationService(
            project_id="test",
            project_dir=tmp_project_dir,
        )
        result = await svc.generate_all()
        for af in result["audio_files"]:
            assert af.get("resumed") is True
            assert af["duration"] > 0.0
