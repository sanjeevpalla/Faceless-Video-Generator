"""Tests for MetadataService."""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.metadata_service import MetadataService


class TestMetadataService:
    # ── read_seo_json ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_read_seo_json(self, tmp_project_dir, seo_json):
        svc = MetadataService("test", tmp_project_dir)
        data = await svc.read_seo_json()
        assert data["title"] == "Test Video Title Under 100 Chars"
        assert isinstance(data["tags"], list)
        assert "ai" in data["tags"]

    @pytest.mark.asyncio
    async def test_read_seo_json_missing_returns_empty(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        # No seo.json present
        data = await svc.read_seo_json()
        assert data == {}

    @pytest.mark.asyncio
    async def test_read_seo_json_invalid_raises(self, tmp_project_dir):
        from app.core.exceptions import ServiceError
        (tmp_project_dir / "input" / "seo.json").write_text("{invalid json", encoding="utf-8")
        svc = MetadataService("test", tmp_project_dir)
        with pytest.raises(ServiceError, match="Invalid seo.json"):
            await svc.read_seo_json()

    @pytest.mark.asyncio
    async def test_read_seo_json_complete_data(self, tmp_project_dir):
        seo = {
            "title": "A Complete SEO Entry",
            "description": "Full description here.",
            "tags": ["tag1", "tag2", "tag3"],
            "chapters": [{"timestamp": "0:00", "title": "Intro"}],
            "category_id": "28",
            "language": "en",
        }
        (tmp_project_dir / "input" / "seo.json").write_text(
            json.dumps(seo), encoding="utf-8"
        )
        svc = MetadataService("test", tmp_project_dir)
        data = await svc.read_seo_json()
        assert data["category_id"] == "28"
        assert len(data["tags"]) == 3

    # ── _build_youtube_metadata ──────────────────────────────────────────────

    def test_build_youtube_metadata_trims_title(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "A" * 150, "description": "desc", "tags": ["t1"]}
        yt = svc._build_youtube_metadata(seo)
        assert len(yt["title"]) <= 100

    def test_build_youtube_metadata_trims_description(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "Title", "description": "D" * 6000, "tags": []}
        yt = svc._build_youtube_metadata(seo)
        assert len(yt["description"]) <= 5000

    def test_build_youtube_metadata_chapter_timestamps(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        seo = {
            "title": "Title",
            "description": "Desc",
            "tags": [],
            "chapters": [
                {"timestamp": "0:00", "title": "Intro"},
                {"timestamp": "2:30", "title": "Main"},
            ],
        }
        yt = svc._build_youtube_metadata(seo)
        assert "0:00 Intro" in yt["description"]
        assert "2:30 Main" in yt["description"]

    def test_build_youtube_metadata_no_chapters(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "Title", "description": "Plain desc", "tags": []}
        yt = svc._build_youtube_metadata(seo)
        assert "Chapters" not in yt["description"]
        assert "Plain desc" in yt["description"]

    def test_build_youtube_metadata_tags_as_csv_string(self, tmp_project_dir):
        """Tags field can be a comma-separated string and should be split."""
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "T", "description": "D", "tags": "tag1, tag2, tag3"}
        yt = svc._build_youtube_metadata(seo)
        assert isinstance(yt["tags"], list)
        assert "tag1" in yt["tags"]
        assert "tag3" in yt["tags"]

    def test_build_youtube_metadata_default_title_when_missing(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        yt = svc._build_youtube_metadata({})
        assert yt["title"] == "Untitled Video"

    def test_build_youtube_metadata_default_privacy_status(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "T", "description": "D", "tags": []}
        yt = svc._build_youtube_metadata(seo)
        assert yt["privacy_status"] == "private"

    def test_build_youtube_metadata_generated_at_present(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "T", "description": "D", "tags": []}
        yt = svc._build_youtube_metadata(seo)
        assert "generated_at" in yt
        assert "Z" in yt["generated_at"]  # ISO format ends with Z

    def test_build_youtube_metadata_made_for_kids_false(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "T", "description": "D", "tags": []}
        yt = svc._build_youtube_metadata(seo)
        assert yt["made_for_kids"] is False

    def test_build_youtube_metadata_fallback_description(self, tmp_project_dir):
        """When description is empty the title is used as fallback."""
        svc = MetadataService("test", tmp_project_dir)
        seo = {"title": "My Title", "description": "", "tags": []}
        yt = svc._build_youtube_metadata(seo)
        assert "My Title" in yt["description"]

    # ── write_youtube_metadata ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_write_youtube_metadata_creates_file(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        metadata = {"title": "Test", "description": "desc", "tags": ["a", "b"]}
        path = await svc.write_youtube_metadata(metadata)
        assert path.exists()

    @pytest.mark.asyncio
    async def test_write_youtube_metadata_valid_json(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        metadata = {"title": "Test", "description": "desc", "tags": ["a", "b"]}
        path = await svc.write_youtube_metadata(metadata)
        saved = json.loads(path.read_text())
        assert saved["title"] == "Test"
        assert saved["tags"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_write_youtube_metadata_filename(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        path = await svc.write_youtube_metadata({"title": "x"})
        assert path.name == "youtube_metadata.json"

    @pytest.mark.asyncio
    async def test_write_youtube_metadata_in_output_dir(self, tmp_project_dir):
        svc = MetadataService("test", tmp_project_dir)
        path = await svc.write_youtube_metadata({"title": "x"})
        assert path.parent.name == "output"

    # ── generate_metadata (full pipeline) ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_metadata_full_pipeline(self, tmp_project_dir, seo_json):
        svc = MetadataService("test", tmp_project_dir)
        result = await svc.generate_metadata()
        assert "metadata_path" in result
        assert "description_path" in result
        assert Path(result["metadata_path"]).exists()
        assert Path(result["description_path"]).exists()
        assert result["title"] == "Test Video Title Under 100 Chars"

    @pytest.mark.asyncio
    async def test_generate_metadata_creates_description_file(
        self, tmp_project_dir, seo_json
    ):
        svc = MetadataService("test", tmp_project_dir)
        result = await svc.generate_metadata()
        desc_path = Path(result["description_path"])
        content = desc_path.read_text(encoding="utf-8")
        assert "TITLE:" in content
        assert "DESCRIPTION:" in content
        assert "TAGS:" in content

    @pytest.mark.asyncio
    async def test_generate_metadata_tags_count(self, tmp_project_dir, seo_json):
        svc = MetadataService("test", tmp_project_dir)
        result = await svc.generate_metadata()
        # seo_json fixture has 3 tags
        assert result["tags_count"] == 3
