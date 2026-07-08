"""Tests for PipelineService's step-retry, WhatsApp pause, and failure-alert behavior."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pipeline_service import (
    PipelineService, AwaitingExternalInputError, DEEP_DIVE_STEPS,
)
from app.core.exceptions import ServiceError


def make_pipeline(project_dir: Path, project_type: str = "deep_dive") -> PipelineService:
    gemini = type("G", (), {
        "api_key": "", "pro_model": "m", "script_model": "m", "flash_model": "m",
        "search_grounding": False, "image_backend": "flux",
    })()
    flux = type("F", (), {"model_dump": lambda self: {}})()
    piper = type("P", (), {"executable": "piper", "model_path": "", "speed": 1.0})()
    video = type("V", (), {})()
    google_tts = type("GT", (), {"api_key": "", "voice_name": "", "language_code": "", "speaking_rate": 1.0})()

    return PipelineService(
        project_id="proj-1",
        project_dir=project_dir,
        project_type=project_type,
        project_language="en",
        gemini_settings=gemini,
        flux_settings=flux,
        piper_settings=piper,
        video_settings=video,
        whisper_model="base",
        whisper_device="cpu",
        tts_engine="piper",
        google_tts_settings=google_tts,
        channel_name="Test Channel",
        comfyui_url="http://127.0.0.1:8188",
    )


class TestDispatchWithRetry:
    @pytest.mark.asyncio
    async def test_awaiting_external_input_is_not_retried(self, tmp_project_dir, monkeypatch):
        svc = make_pipeline(tmp_project_dir)
        calls = {"n": 0}

        async def fake_dispatch(step_name, sub_cb):
            calls["n"] += 1
            raise AwaitingExternalInputError("waiting")

        monkeypatch.setattr(svc, "_dispatch", fake_dispatch)

        with pytest.raises(AwaitingExternalInputError):
            await svc._dispatch_with_retry("trend_discovery", lambda *a, **k: None)

        assert calls["n"] == 1  # no retries for a deliberate pause signal

    @pytest.mark.asyncio
    async def test_generic_failure_is_retried_up_to_max_attempts(self, tmp_project_dir, monkeypatch):
        svc = make_pipeline(tmp_project_dir)
        calls = {"n": 0}

        async def fake_dispatch(step_name, sub_cb):
            calls["n"] += 1
            raise RuntimeError("boom")

        monkeypatch.setattr(svc, "_dispatch", fake_dispatch)
        monkeypatch.setattr("asyncio.sleep", lambda *_: _noop())

        with pytest.raises(RuntimeError):
            await svc._dispatch_with_retry("research", lambda *a, **k: None, max_attempts=3, base_delay=0.001)

        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_succeeds_after_transient_failure(self, tmp_project_dir, monkeypatch):
        svc = make_pipeline(tmp_project_dir)
        calls = {"n": 0}

        async def fake_dispatch(step_name, sub_cb):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("transient")

        monkeypatch.setattr(svc, "_dispatch", fake_dispatch)

        await svc._dispatch_with_retry("research", lambda *a, **k: None, max_attempts=3, base_delay=0.001)
        assert calls["n"] == 2


async def _noop():
    return None


class TestRunStepsPauseAndAlert:
    @pytest.mark.asyncio
    async def test_run_steps_returns_awaiting_input_without_raising(self, tmp_project_dir, monkeypatch):
        svc = make_pipeline(tmp_project_dir)

        async def fake_dispatch(step_name, sub_cb):
            raise AwaitingExternalInputError("waiting on WhatsApp")

        monkeypatch.setattr(svc, "_dispatch", fake_dispatch)

        result = await svc._run_steps(DEEP_DIVE_STEPS[:1])  # just trend_discovery
        assert result["status"] == "awaiting_input"
        assert result["step_name"] == "trend_discovery"

    @pytest.mark.asyncio
    async def test_run_steps_sends_alert_on_final_failure(self, tmp_project_dir, monkeypatch):
        svc = make_pipeline(tmp_project_dir)
        alert_calls = []

        async def fake_dispatch(step_name, sub_cb):
            raise RuntimeError("permanent failure")

        async def fake_alert(step_label, exc):
            alert_calls.append((step_label, str(exc)))

        monkeypatch.setattr(svc, "_dispatch", fake_dispatch)
        monkeypatch.setattr(svc, "_send_failure_alert", fake_alert)

        with pytest.raises(ServiceError):
            await svc._run_steps([("research", "Research & Script Generation")])

        assert len(alert_calls) == 1
        assert alert_calls[0][0] == "Research & Script Generation"

    @pytest.mark.asyncio
    async def test_run_steps_does_not_alert_on_awaiting_input(self, tmp_project_dir, monkeypatch):
        svc = make_pipeline(tmp_project_dir)
        alert_calls = []

        async def fake_dispatch(step_name, sub_cb):
            raise AwaitingExternalInputError("waiting")

        async def fake_alert(step_label, exc):
            alert_calls.append(step_label)

        monkeypatch.setattr(svc, "_dispatch", fake_dispatch)
        monkeypatch.setattr(svc, "_send_failure_alert", fake_alert)

        result = await svc._run_steps([("trend_discovery", "Trend Discovery (WhatsApp Approval)")])
        assert result["status"] == "awaiting_input"
        assert alert_calls == []
