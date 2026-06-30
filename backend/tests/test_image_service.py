"""Tests for ImageGenerationService."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.image_service import ImageGenerationService
from app.core.exceptions import ServiceError


PROJECT_ID = "test-project-001"


@pytest.fixture
def image_service(tmp_project_dir):
    (tmp_project_dir / "cache" / "images").mkdir(parents=True, exist_ok=True)
    return ImageGenerationService(
        project_id=PROJECT_ID,
        project_dir=tmp_project_dir,
        comfyui_url="http://localhost:8188",
        flux_settings={
            "steps": 5,
            "cfg": 7.0,
            "sampler": "euler",
            "scheduler": "normal",
            "width": 512,
            "height": 512,
        },
    )


class TestImageGenerationService:
    def test_hash_prompt_deterministic(self, image_service):
        h1 = image_service._hash_prompt("test prompt")
        h2 = image_service._hash_prompt("test prompt")
        assert h1 == h2

    def test_hash_prompt_length(self, image_service):
        h = image_service._hash_prompt("any prompt")
        assert len(h) == 16

    def test_hash_prompt_different_for_different_prompts(self, image_service):
        h1 = image_service._hash_prompt("prompt A")
        h2 = image_service._hash_prompt("prompt B")
        assert h1 != h2

    def test_hash_prompt_includes_settings(self, tmp_project_dir):
        svc_a = ImageGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
            flux_settings={"steps": 10},
        )
        svc_b = ImageGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
            flux_settings={"steps": 50},
        )
        # Same prompt but different settings should produce different hashes
        assert svc_a._hash_prompt("same prompt") != svc_b._hash_prompt("same prompt")

    def test_build_workflow_sets_positive_prompt(self, image_service):
        wf = image_service._build_workflow("my test prompt", "ugly")
        assert wf["6"]["inputs"]["text"] == "my test prompt"

    def test_build_workflow_sets_negative_prompt(self, image_service):
        wf = image_service._build_workflow("positive", "ugly negative")
        assert wf["7"]["inputs"]["text"] == "ugly negative"

    def test_build_workflow_applies_flux_settings(self, image_service):
        wf = image_service._build_workflow("prompt", "neg")
        assert wf["13"]["inputs"]["steps"] == 5
        assert wf["13"]["inputs"]["cfg"] == 7.0
        assert wf["13"]["inputs"]["sampler_name"] == "euler"
        assert wf["13"]["inputs"]["scheduler"] == "normal"
        assert wf["10"]["inputs"]["width"] == 512
        assert wf["10"]["inputs"]["height"] == 512

    def test_build_workflow_uses_defaults_for_missing_settings(self, tmp_project_dir):
        svc = ImageGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
            flux_settings={},  # empty — should use defaults
        )
        wf = svc._build_workflow("prompt", "neg")
        assert wf["13"]["inputs"]["steps"] == 20
        assert wf["10"]["inputs"]["width"] == 1920
        assert wf["10"]["inputs"]["height"] == 1080

    def test_build_workflow_sets_random_seed(self, image_service):
        wf = image_service._build_workflow("prompt", "neg")
        assert isinstance(wf["13"]["inputs"]["seed"], int)
        assert wf["13"]["inputs"]["seed"] >= 0

    def test_check_cache_miss(self, image_service):
        result = image_service.check_cache("nonexistent_hash_xyz", 1)
        assert result is None

    def test_check_cache_hit(self, image_service, tmp_project_dir):
        cache_dir = tmp_project_dir / "cache" / "images"
        # Create a fake image and cache entry
        fake_image = tmp_project_dir / "images" / "scene_001.png"
        fake_image.parent.mkdir(parents=True, exist_ok=True)
        fake_image.write_bytes(b"\x89PNG\r\n")
        cache_entry = {
            "scene_id": 1,
            "path": str(fake_image),
            "filename": fake_image.name,
            "prompt_hash": "abc123",
        }
        (cache_dir / "abc123.json").write_text(json.dumps(cache_entry))

        result = image_service.check_cache("abc123", 1)
        assert result is not None
        assert result["scene_id"] == 1
        assert result["prompt_hash"] == "abc123"

    def test_check_cache_ignores_stale_entry_with_missing_file(self, image_service, tmp_project_dir):
        cache_dir = tmp_project_dir / "cache" / "images"
        # Cache entry pointing to a file that does not exist
        cache_entry = {
            "scene_id": 1,
            "path": str(tmp_project_dir / "images" / "nonexistent.png"),
            "filename": "nonexistent.png",
            "prompt_hash": "stale_hash",
        }
        (cache_dir / "stale_hash.json").write_text(json.dumps(cache_entry))

        result = image_service.check_cache("stale_hash", 1)
        assert result is None

    def test_check_cache_handles_corrupt_json(self, image_service, tmp_project_dir):
        cache_dir = tmp_project_dir / "cache" / "images"
        (cache_dir / "bad_hash.json").write_text("{corrupt}")
        result = image_service.check_cache("bad_hash", 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_all_no_prompts_file(self, image_service):
        """Should raise ServiceError when image_prompts.txt is missing."""
        with pytest.raises(ServiceError, match="image_prompts.txt not found"):
            await image_service.generate_all()

    @pytest.mark.asyncio
    async def test_generate_all_empty_prompts_file(self, image_service, tmp_project_dir):
        """Should raise ServiceError when image_prompts.txt is empty."""
        (tmp_project_dir / "input" / "image_prompts.txt").write_text("\n  \n")
        with pytest.raises(ServiceError, match="No prompts found"):
            await image_service.generate_all()

    @pytest.mark.asyncio
    async def test_generate_all_skips_existing_images(
        self, image_service, tmp_project_dir, image_prompts_txt
    ):
        """Resume support: already-generated images should be skipped."""
        # Pre-create scene images
        for i in range(1, 4):
            img = tmp_project_dir / "images" / f"scene_{i:03d}.png"
            img.write_bytes(b"\x89PNG\r\n")

        result = await image_service.generate_all()

        assert result["generated"] == 3
        assert result["total"] == 3
        assert result["failed"] == []
        assert all(r.get("resumed") for r in result["images"])

    @pytest.mark.asyncio
    async def test_generate_all_manifest_written(
        self, image_service, tmp_project_dir, image_prompts_txt
    ):
        """Manifest JSON must be written to images dir after generate_all."""
        # Pre-create images so no ComfyUI call is needed
        for i in range(1, 4):
            img = tmp_project_dir / "images" / f"scene_{i:03d}.png"
            img.write_bytes(b"\x89PNG\r\n")

        await image_service.generate_all()

        manifest_path = tmp_project_dir / "images" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["total"] == 3
        assert manifest["generated"] == 3

    @pytest.mark.asyncio
    async def test_generate_all_partial_resume(
        self, tmp_project_dir, image_prompts_txt
    ):
        """Only missing scenes should call generate_scene; existing ones skipped."""
        svc = ImageGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
            flux_settings={"steps": 5, "cfg": 7.0, "sampler": "euler",
                           "scheduler": "normal", "width": 512, "height": 512},
        )
        # Pre-create scenes 1 and 2 only
        images_dir = tmp_project_dir / "images"
        for i in [1, 2]:
            p = images_dir / f"scene_{i:03d}.png"
            p.write_bytes(b"\x89PNG fake")

        called_scenes = []

        async def mock_generate_scene(scene_id, prompt, negative_prompt=""):
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
    async def test_generate_all_records_failures(
        self, tmp_project_dir, image_prompts_txt
    ):
        """Failed scenes should appear in the 'failed' list, not crash the whole run."""
        svc = ImageGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )

        async def mock_generate_scene(scene_id, prompt, negative_prompt=""):
            raise ServiceError("image_generation", f"Simulated failure for scene {scene_id}")

        svc.generate_scene = mock_generate_scene
        result = await svc.generate_all()

        assert result["total"] == 3
        assert result["generated"] == 0
        assert len(result["failed"]) == 3
        assert all("error" in f for f in result["failed"])

    def test_service_name(self, image_service):
        assert image_service.service_name == "image_generation"

    def test_images_dir_created(self, tmp_project_dir):
        svc = ImageGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        assert svc.images_dir.exists()

    def test_cache_dir_created(self, tmp_project_dir):
        svc = ImageGenerationService(
            project_id=PROJECT_ID,
            project_dir=tmp_project_dir,
            comfyui_url="http://localhost:8188",
        )
        assert svc.cache_dir.exists()
