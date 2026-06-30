import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.services.base import BaseService
from app.core.exceptions import ServiceError


class MetadataService(BaseService):
    """Reads SEO JSON and writes YouTube-ready metadata."""

    service_name = "metadata_generation"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.output_dir = self.get_output_dir("output")

    async def execute(self) -> Dict[str, Any]:
        return await self.generate_metadata()

    async def generate_metadata(self) -> Dict[str, Any]:
        await self.report_progress(10, "Reading SEO data...")

        seo_data = await self.read_seo_json()
        await self.report_progress(40, "Generating YouTube metadata...")

        youtube_metadata = self._build_youtube_metadata(seo_data)
        await self.report_progress(70, "Writing metadata files...")

        metadata_path = await self.write_youtube_metadata(youtube_metadata)
        await self.report_progress(90, "Writing description file...")

        desc_path = await self._write_description(youtube_metadata)

        await self.report_progress(100, "Metadata generation complete")
        return {
            "metadata_path": str(metadata_path),
            "description_path": str(desc_path),
            "title": youtube_metadata.get("title", ""),
            "tags_count": len(youtube_metadata.get("tags", [])),
        }

    async def read_seo_json(self) -> Dict[str, Any]:
        seo_file = self.project_dir / "input" / "seo.json"
        if not seo_file.exists():
            self.logger.warning("seo.json not found, using defaults")
            return {}
        try:
            with open(seo_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            raise ServiceError(self.service_name, f"Invalid seo.json: {exc}")

    def _build_youtube_metadata(self, seo_data: Dict[str, Any]) -> Dict[str, Any]:
        title = seo_data.get("title", "Untitled Video")
        description = seo_data.get("description", "")
        tags = seo_data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        category_id = seo_data.get("category_id", "22")  # 22 = People & Blogs
        language = seo_data.get("language", "en")
        thumbnail_prompt = seo_data.get("thumbnail_prompt", "")
        chapters = seo_data.get("chapters", [])

        # Build chapter timestamps in description
        chapter_text = ""
        if chapters:
            chapter_text = "\n\n--- Chapters ---\n"
            for ch in chapters:
                if isinstance(ch, dict):
                    ts = ch.get("timestamp", "00:00")
                    name = ch.get("title", "")
                elif isinstance(ch, str):
                    parts = ch.split(" ", 1)
                    ts = parts[0] if len(parts) > 1 and ":" in parts[0] else "00:00"
                    name = parts[1] if len(parts) > 1 and ":" in parts[0] else ch
                else:
                    continue
                chapter_text += f"{ts} {name}\n"

        full_description = f"{description}{chapter_text}"
        if not full_description.strip():
            full_description = title

        return {
            "title": title[:100],  # YouTube title limit
            "description": full_description[:5000],  # YouTube description limit
            "tags": tags[:500],  # YouTube tags limit
            "category_id": category_id,
            "language": language,
            "thumbnail_prompt": thumbnail_prompt,
            "chapters": chapters,
            "privacy_status": "private",
            "made_for_kids": False,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    async def write_youtube_metadata(self, metadata: Dict[str, Any]) -> Path:
        metadata_path = self.output_dir / "youtube_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        self.logger.info(f"YouTube metadata written to {metadata_path}")
        return metadata_path

    async def _write_description(self, metadata: Dict[str, Any]) -> Path:
        desc_path = self.output_dir / "description.txt"
        lines = [
            f"TITLE: {metadata.get('title', '')}",
            "",
            "DESCRIPTION:",
            metadata.get("description", ""),
            "",
            f"TAGS: {', '.join(metadata.get('tags', []))}",
        ]
        with open(desc_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return desc_path
