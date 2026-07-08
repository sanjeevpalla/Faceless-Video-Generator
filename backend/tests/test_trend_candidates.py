"""Tests for ContentGenerationService.discover_trend_candidates (Gemini mocked)."""
import json
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.content_service import ContentGenerationService
from app.core.exceptions import ServiceError


def make_service(project_dir: Path) -> ContentGenerationService:
    return ContentGenerationService(
        project_id="test",
        project_dir=project_dir,
        api_key="fake-key",
        channel_name="Deep Dive AI",
    )


class TestDiscoverTrendCandidates:
    @pytest.mark.asyncio
    async def test_returns_structured_candidates(self, tmp_project_dir, monkeypatch):
        svc = make_service(tmp_project_dir)
        canned = json.dumps([
            {"title": "Topic One", "summary": "Why it matters"},
            {"title": "Topic Two", "summary": "Another reason"},
        ])

        async def fake_call(self, prompt, model_name, with_search=False, **kw):
            return canned

        monkeypatch.setattr(ContentGenerationService, "_call", fake_call)

        result = await svc.discover_trend_candidates(n=10)
        assert len(result) == 2
        assert result[0] == {"id": "0", "title": "Topic One", "summary": "Why it matters"}
        assert result[1]["id"] == "1"

    @pytest.mark.asyncio
    async def test_caps_at_ten_even_if_more_requested(self, tmp_project_dir, monkeypatch):
        svc = make_service(tmp_project_dir)
        canned = json.dumps([{"title": f"T{i}", "summary": "s"} for i in range(15)])

        async def fake_call(self, prompt, model_name, with_search=False, **kw):
            return canned

        monkeypatch.setattr(ContentGenerationService, "_call", fake_call)

        result = await svc.discover_trend_candidates(n=25)
        assert len(result) == 10

    @pytest.mark.asyncio
    async def test_retries_once_on_invalid_json_then_succeeds(self, tmp_project_dir, monkeypatch):
        svc = make_service(tmp_project_dir)
        calls = {"count": 0}

        async def fake_call(self, prompt, model_name, with_search=False, **kw):
            calls["count"] += 1
            if calls["count"] == 1:
                return "not json at all"
            return json.dumps([{"title": "Recovered", "summary": "ok"}])

        monkeypatch.setattr(ContentGenerationService, "_call", fake_call)

        result = await svc.discover_trend_candidates(n=5)
        assert calls["count"] == 2
        assert result[0]["title"] == "Recovered"

    @pytest.mark.asyncio
    async def test_raises_service_error_if_still_invalid_after_retry(self, tmp_project_dir, monkeypatch):
        svc = make_service(tmp_project_dir)

        async def fake_call(self, prompt, model_name, with_search=False, **kw):
            return "still not json"

        monkeypatch.setattr(ContentGenerationService, "_call", fake_call)

        with pytest.raises(ServiceError):
            await svc.discover_trend_candidates(n=5)
