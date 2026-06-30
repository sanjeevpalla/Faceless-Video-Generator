"""Tests for ProjectValidationService."""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.validation_service import ProjectValidationService


def make_service(project_dir: Path) -> ProjectValidationService:
    return ProjectValidationService(project_dir)


class TestValidationService:
    def test_all_missing_returns_invalid(self, tmp_path):
        pdir = tmp_path / "empty_project"
        (pdir / "input").mkdir(parents=True)
        svc = make_service(pdir)
        result = svc.validate_all()
        assert result["all_valid"] is False
        for file_type in ["script", "scenes", "image_prompts", "thumbnail_prompt", "seo", "music"]:
            assert result["results"][file_type]["valid"] is False

    def test_valid_scenes_json(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        scenes = {
            "scenes": [
                {"scene_id": 1, "narration": "Hello world", "duration": 5},
                {"scene_id": 2, "narration": "Goodbye world", "duration": 5},
            ]
        }
        (pdir / "input" / "scenes.json").write_text(json.dumps(scenes))
        svc = make_service(pdir)
        result = svc._validate_scenes()
        assert result.valid is True
        assert result.info["scene_count"] == 2

    def test_invalid_scenes_json_bad_json(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        (pdir / "input" / "scenes.json").write_text("{ bad json }")
        svc = make_service(pdir)
        result = svc._validate_scenes()
        assert result.valid is False
        assert any("Invalid JSON" in e for e in result.errors)

    def test_scenes_missing_required_field(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        # scene missing 'narration' and 'duration'
        scenes = {"scenes": [{"scene_id": 1, "title": "No narration"}]}
        (pdir / "input" / "scenes.json").write_text(json.dumps(scenes))
        svc = make_service(pdir)
        result = svc._validate_scenes()
        assert result.valid is False
        # Should mention both missing fields
        all_errors = " ".join(result.errors)
        assert "narration" in all_errors

    def test_scenes_missing_scene_id_field(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        scenes = {"scenes": [{"narration": "hello", "duration": 5}]}  # missing scene_id
        (pdir / "input" / "scenes.json").write_text(json.dumps(scenes))
        svc = make_service(pdir)
        result = svc._validate_scenes()
        assert result.valid is False
        assert any("scene_id" in e for e in result.errors)

    def test_scenes_missing_file(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        # No scenes.json
        svc = make_service(pdir)
        result = svc._validate_scenes()
        assert result.valid is False
        assert any("scenes.json" in e for e in result.errors)

    def test_scenes_empty_list(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        (pdir / "input" / "scenes.json").write_text(json.dumps({"scenes": []}))
        svc = make_service(pdir)
        result = svc._validate_scenes()
        assert result.valid is False
        assert any("No scenes" in e for e in result.errors)

    def test_image_prompts_valid(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        lines = ["A beautiful sunset over the ocean", "A futuristic city skyline"]
        (pdir / "input" / "image_prompts.txt").write_text("\n".join(lines))
        svc = make_service(pdir)
        result = svc._validate_image_prompts()
        assert result.valid is True
        assert result.info["prompt_count"] == 2

    def test_image_prompts_count_mismatch_warns(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        # 2 prompts
        (pdir / "input" / "image_prompts.txt").write_text(
            "A prompt longer than ten chars here\nAnother prompt longer than ten chars"
        )
        # 3 scenes
        scenes = {
            "scenes": [
                {"scene_id": i, "narration": f"n{i}", "duration": 5} for i in range(1, 4)
            ]
        }
        (pdir / "input" / "scenes.json").write_text(json.dumps(scenes))
        svc = make_service(pdir)
        result = svc._validate_image_prompts()
        assert result.valid is True  # count mismatch is a warning, not an error
        assert len(result.warnings) > 0

    def test_image_prompts_empty_file(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        (pdir / "input" / "image_prompts.txt").write_text("")
        svc = make_service(pdir)
        result = svc._validate_image_prompts()
        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_image_prompts_missing_file(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        svc = make_service(pdir)
        result = svc._validate_image_prompts()
        assert result.valid is False
        assert any("image_prompts.txt" in e for e in result.errors)

    def test_seo_title_too_long_warns(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        seo = {"title": "A" * 110, "description": "desc", "tags": ["tag1"]}
        (pdir / "input" / "seo.json").write_text(json.dumps(seo))
        svc = make_service(pdir)
        result = svc._validate_seo()
        assert result.valid is True
        assert any("100 chars" in w for w in result.warnings)

    def test_seo_missing_required_fields(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        seo = {"title": "Title only"}  # missing description and tags
        (pdir / "input" / "seo.json").write_text(json.dumps(seo))
        svc = make_service(pdir)
        result = svc._validate_seo()
        assert result.valid is False

    def test_seo_valid(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        seo = {
            "title": "A Great Video",
            "description": "This is a description.",
            "tags": ["tag1", "tag2"],
        }
        (pdir / "input" / "seo.json").write_text(json.dumps(seo))
        svc = make_service(pdir)
        result = svc._validate_seo()
        assert result.valid is True
        assert result.info["tag_count"] == 2

    def test_seo_invalid_json(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        (pdir / "input" / "seo.json").write_text("{broken json")
        svc = make_service(pdir)
        result = svc._validate_seo()
        assert result.valid is False
        assert any("Invalid JSON" in e for e in result.errors)

    def test_seo_missing_file(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        svc = make_service(pdir)
        result = svc._validate_seo()
        assert result.valid is False
        assert any("seo.json" in e for e in result.errors)

    def test_music_file_found(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        music_path = pdir / "input" / "bg_music.mp3"
        music_path.write_bytes(b"\xff\xfb" * 1000)  # fake mp3 content (>1KB)
        svc = make_service(pdir)
        result = svc._validate_music()
        assert result.valid is True
        assert result.info["filename"] == "bg_music.mp3"

    def test_music_file_too_small(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        music_path = pdir / "input" / "bg_music.mp3"
        music_path.write_bytes(b"\xff\xfb")  # only 2 bytes — corrupt
        svc = make_service(pdir)
        result = svc._validate_music()
        assert result.valid is False
        assert any("empty or corrupt" in e for e in result.errors)

    def test_music_missing_file(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        svc = make_service(pdir)
        result = svc._validate_music()
        assert result.valid is False

    def test_thumbnail_prompt_valid(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        (pdir / "input" / "thumbnail_prompt.txt").write_text(
            "A stunning professional YouTube thumbnail with bright colors"
        )
        svc = make_service(pdir)
        result = svc._validate_thumbnail_prompt()
        assert result.valid is True

    def test_thumbnail_prompt_empty_invalid(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        (pdir / "input" / "thumbnail_prompt.txt").write_text("   ")  # whitespace only
        svc = make_service(pdir)
        result = svc._validate_thumbnail_prompt()
        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_thumbnail_prompt_missing_file(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        svc = make_service(pdir)
        result = svc._validate_thumbnail_prompt()
        assert result.valid is False
        assert any("thumbnail_prompt.txt" in e for e in result.errors)

    def test_script_valid(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        content = "This is a long enough script file that has more than fifty characters total here."
        (pdir / "input" / "script.md").write_text(content)
        svc = make_service(pdir)
        result = svc._validate_script()
        assert result.valid is True
        assert result.info["char_count"] == len(content)

    def test_script_txt_accepted(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        content = "This is a plain text script with plenty of characters to pass validation checks here."
        (pdir / "input" / "script.txt").write_text(content)
        svc = make_service(pdir)
        result = svc._validate_script()
        assert result.valid is True

    def test_script_very_short_warns(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        (pdir / "input" / "script.md").write_text("Hi")
        svc = make_service(pdir)
        result = svc._validate_script()
        assert result.valid is True
        assert any("short" in w.lower() for w in result.warnings)

    def test_validate_all_returns_all_keys(self, tmp_path):
        pdir = tmp_path / "proj"
        (pdir / "input").mkdir(parents=True)
        svc = make_service(pdir)
        result = svc.validate_all()
        assert "all_valid" in result
        assert "results" in result
        expected_keys = {"script", "scenes", "image_prompts", "thumbnail_prompt", "seo", "music"}
        assert expected_keys == set(result["results"].keys())

    def test_file_validation_result_to_dict(self, tmp_path):
        from app.services.validation_service import FileValidationResult
        r = FileValidationResult("test")
        r.add_error("Something broke")
        r.add_warning("Something looks odd")
        r.info["key"] = "value"
        d = r.to_dict()
        assert d["file_type"] == "test"
        assert d["valid"] is False
        assert "Something broke" in d["errors"]
        assert "Something looks odd" in d["warnings"]
        assert d["info"]["key"] == "value"
