from pathlib import Path
from typing import Any, Dict, List
import json
from app.core.logging import get_logger

logger = get_logger(__name__)


class FileValidationResult:
    def __init__(self, file_type: str):
        self.file_type = file_type
        self.valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: Dict[str, Any] = {}

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def to_dict(self) -> Dict:
        return {
            "file_type": self.file_type,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
        }


class ProjectValidationService:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.input_dir = project_dir / "input"

    def validate_all(self) -> Dict[str, Any]:
        results = {
            "script": self._validate_script(),
            "scenes": self._validate_scenes(),
            "image_prompts": self._validate_image_prompts(),
            "thumbnail_prompt": self._validate_thumbnail_prompt(),
            "seo": self._validate_seo(),
        }
        all_valid = all(r.valid for r in results.values())
        return {
            "all_valid": all_valid,
            "results": {k: v.to_dict() for k, v in results.items()},
        }

    def _validate_script(self) -> FileValidationResult:
        r = FileValidationResult("script")
        # Accept script.md or script.txt
        path = None
        for name in ["script.md", "script.txt"]:
            p = self.input_dir / name
            if p.exists():
                path = p
                break
        if not path:
            r.add_error("script.md not found in input/")
            return r
        try:
            text = path.read_text(encoding="utf-8")
            r.info["word_count"] = len(text.split())
            r.info["char_count"] = len(text)
            if len(text.strip()) < 50:
                r.add_warning("Script is very short (< 50 characters)")
        except Exception as e:
            r.add_error(f"Cannot read script file: {e}")
        return r

    def _validate_scenes(self) -> FileValidationResult:
        r = FileValidationResult("scenes")
        path = self.input_dir / "scenes.json"
        if not path.exists():
            r.add_error("scenes.json not found in input/")
            return r
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            r.add_error(f"Invalid JSON: {e}")
            return r

        if isinstance(data, list):
            scenes = data
            video_title = ""
            total_duration = 0
        else:
            scenes = data.get("scenes", [])
            video_title = data.get("video_title", "")
            total_duration = data.get("total_duration", 0)

        if not scenes:
            r.add_error("No scenes found in scenes.json")
            return r

        r.info["scene_count"] = len(scenes)
        r.info["video_title"] = video_title
        r.info["total_duration"] = total_duration

        required_fields = ["scene_id", "narration", "duration"]
        for i, scene in enumerate(scenes):
            for field in required_fields:
                if field not in scene:
                    r.add_error(f"Scene {i+1} missing required field: '{field}'")
            narration = scene.get("narration", "").strip()
            if not narration:
                r.add_warning(f"Scene {i+1} has empty narration")
            duration = scene.get("duration", 0)
            if not isinstance(duration, (int, float)) or duration <= 0:
                r.add_warning(f"Scene {i+1} has invalid duration: {duration}")
        return r

    def _validate_image_prompts(self) -> FileValidationResult:
        r = FileValidationResult("image_prompts")
        path = self.input_dir / "image_prompts.txt"
        if not path.exists():
            r.add_error("image_prompts.txt not found in input/")
            return r
        try:
            lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except Exception as e:
            r.add_error(f"Cannot read image_prompts.txt: {e}")
            return r

        if not lines:
            r.add_error("image_prompts.txt is empty")
            return r

        r.info["prompt_count"] = len(lines)

        # Cross-validate against scenes.json
        scenes_path = self.input_dir / "scenes.json"
        if scenes_path.exists():
            try:
                scenes_data = json.loads(scenes_path.read_text(encoding="utf-8"))
                scene_count = len(scenes_data if isinstance(scenes_data, list) else scenes_data.get("scenes", []))
                if scene_count > 0 and len(lines) != scene_count:
                    r.add_warning(
                        f"Prompt count ({len(lines)}) differs from scene count ({scene_count}). "
                        "Each line maps to one scene."
                    )
            except Exception:
                pass

        for i, line in enumerate(lines):
            if len(line) < 10:
                r.add_warning(f"Prompt {i+1} is very short: '{line[:40]}'")
        return r

    def _validate_thumbnail_prompt(self) -> FileValidationResult:
        r = FileValidationResult("thumbnail_prompt")
        path = self.input_dir / "thumbnail_prompt.txt"
        if not path.exists():
            r.add_error("thumbnail_prompt.txt not found in input/")
            return r
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception as e:
            r.add_error(f"Cannot read thumbnail_prompt.txt: {e}")
            return r
        if not text:
            r.add_error("thumbnail_prompt.txt is empty")
            return r
        r.info["char_count"] = len(text)
        if len(text) < 10:
            r.add_warning("Thumbnail prompt is very short")
        return r

    def _validate_seo(self) -> FileValidationResult:
        r = FileValidationResult("seo")
        path = self.input_dir / "seo.json"
        if not path.exists():
            r.add_error("seo.json not found in input/")
            return r
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            r.add_error(f"Invalid JSON: {e}")
            return r

        required = ["title", "description", "tags"]
        for field in required:
            if not data.get(field):
                r.add_error(f"seo.json missing required field: '{field}'")

        title = data.get("title", "")
        if len(title) > 100:
            r.add_warning(f"Title exceeds YouTube limit of 100 chars ({len(title)} chars)")
        desc = data.get("description", "")
        if len(desc) > 5000:
            r.add_warning(f"Description exceeds YouTube limit of 5000 chars ({len(desc)} chars)")
        tags = data.get("tags", [])
        if isinstance(tags, list):
            r.info["tag_count"] = len(tags)
        r.info["title"] = title[:80]
        return r

