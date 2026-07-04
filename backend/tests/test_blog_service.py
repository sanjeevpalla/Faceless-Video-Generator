"""Tests for BlogPostService."""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.blog_service import BlogPostService

_SAMPLE_OUTPUT = """TITLE: The Rise of a New AI Era
SUBTITLE: How a single breakthrough changed everything
TAGS: ai, technology, machine learning, future, innovation
---
## The Breakthrough

It started quietly, the way most revolutions do.

## What It Means

This changes everything for developers and creators alike.

Watch the full video on Deep Dive AI."""


def _make_service(tmp_project_dir: Path) -> BlogPostService:
    return BlogPostService(
        project_id="test",
        project_dir=tmp_project_dir,
        api_key="fake-key",
        channel_name="Deep Dive AI",
    )


class TestParseBlogOutput:
    def test_parses_title_subtitle_tags_body(self):
        title, subtitle, tags, body = BlogPostService._parse_blog_output(_SAMPLE_OUTPUT)
        assert title == "The Rise of a New AI Era"
        assert subtitle == "How a single breakthrough changed everything"
        assert tags == ["ai", "technology", "machine learning", "future", "innovation"]
        assert "## The Breakthrough" in body
        assert "TITLE:" not in body

    def test_missing_marker_falls_back_to_raw_body(self):
        raw = "Just some plain prose with no header markers at all."
        title, subtitle, tags, body = BlogPostService._parse_blog_output(raw)
        assert title == "Untitled Article"
        assert subtitle == ""
        assert tags == []
        assert body == raw


class TestGenerateBlogPost:
    @pytest.mark.asyncio
    async def test_missing_script_raises(self, tmp_project_dir):
        svc = _make_service(tmp_project_dir)
        with pytest.raises(RuntimeError, match="script.md not found"):
            await svc.generate_blog_post()

    @pytest.mark.asyncio
    async def test_full_pipeline_writes_files(self, tmp_project_dir, script_md, monkeypatch):
        svc = _make_service(tmp_project_dir)

        async def fake_call(prompt, model_name, **kwargs):
            return _SAMPLE_OUTPUT

        monkeypatch.setattr(svc, "_call", fake_call)

        result = await svc.generate_blog_post()

        assert Path(result["blog_path"]).exists()
        assert Path(result["meta_path"]).exists()
        assert result["title"] == "The Rise of a New AI Era"
        assert result["word_count"] > 0

        body = Path(result["blog_path"]).read_text(encoding="utf-8")
        assert "## The Breakthrough" in body

        meta = json.loads(Path(result["meta_path"]).read_text(encoding="utf-8"))
        assert meta["tags"] == ["ai", "technology", "machine learning", "future", "innovation"]
        assert meta["subtitle"] == "How a single breakthrough changed everything"

    @pytest.mark.asyncio
    async def test_uses_seo_keywords_in_prompt(self, tmp_project_dir, script_md, seo_json, monkeypatch):
        svc = _make_service(tmp_project_dir)
        captured = {}

        async def fake_call(prompt, model_name, **kwargs):
            captured["prompt"] = prompt
            return _SAMPLE_OUTPUT

        monkeypatch.setattr(svc, "_call", fake_call)
        await svc.generate_blog_post()

        assert "ai" in captured["prompt"]
        assert "TARGET KEYWORDS" in captured["prompt"]

    @pytest.mark.asyncio
    async def test_files_written_in_output_dir(self, tmp_project_dir, script_md, monkeypatch):
        svc = _make_service(tmp_project_dir)

        async def fake_call(prompt, model_name, **kwargs):
            return _SAMPLE_OUTPUT

        monkeypatch.setattr(svc, "_call", fake_call)
        result = await svc.generate_blog_post()

        assert Path(result["blog_path"]).parent.name == "output"
        assert Path(result["meta_path"]).parent.name == "output"
