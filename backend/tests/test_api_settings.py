"""Integration tests for the /api/v1/settings REST API."""
import pytest
from httpx import AsyncClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSettingsAPI:
    # ── GET /settings ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_settings_returns_200(self, client: AsyncClient):
        r = await client.get("/api/v1/settings")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_get_settings_returns_defaults(self, client: AsyncClient):
        r = await client.get("/api/v1/settings")
        assert r.status_code == 200
        data = r.json()
        assert "flux" in data
        assert "piper" in data
        assert "video" in data
        assert "output" in data

    @pytest.mark.asyncio
    async def test_get_settings_flux_defaults(self, client: AsyncClient):
        r = await client.get("/api/v1/settings")
        flux = r.json()["flux"]
        assert flux["steps"] == 20
        assert flux["cfg"] == 7.0
        assert flux["sampler"] == "euler"
        assert flux["scheduler"] == "normal"
        assert flux["width"] == 1920
        assert flux["height"] == 1080

    @pytest.mark.asyncio
    async def test_get_settings_video_defaults(self, client: AsyncClient):
        r = await client.get("/api/v1/settings")
        video = r.json()["video"]
        assert video["fps"] == 30
        assert video["resolution"] == "1920x1080"

    @pytest.mark.asyncio
    async def test_get_settings_whisper_defaults(self, client: AsyncClient):
        r = await client.get("/api/v1/settings")
        data = r.json()
        assert data["whisper_model"] == "base"
        assert data["whisper_language"] == "en"
        assert data["whisper_device"] == "cuda"

    @pytest.mark.asyncio
    async def test_get_settings_piper_defaults(self, client: AsyncClient):
        r = await client.get("/api/v1/settings")
        piper = r.json()["piper"]
        assert piper["speed"] == 1.0
        assert "executable" in piper

    # ── PUT /settings ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_flux_steps(self, client: AsyncClient):
        r = await client.put(
            "/api/v1/settings",
            json={
                "flux": {
                    "steps": 30,
                    "cfg": 7.0,
                    "sampler": "euler",
                    "scheduler": "normal",
                    "width": 1920,
                    "height": 1080,
                    "comfyui_url": "http://127.0.0.1:8188",
                }
            },
        )
        assert r.status_code == 200
        assert r.json()["flux"]["steps"] == 30

    @pytest.mark.asyncio
    async def test_update_flux_cfg(self, client: AsyncClient):
        r = await client.put(
            "/api/v1/settings",
            json={
                "flux": {
                    "steps": 20,
                    "cfg": 9.5,
                    "sampler": "euler",
                    "scheduler": "normal",
                    "width": 1920,
                    "height": 1080,
                    "comfyui_url": "http://127.0.0.1:8188",
                }
            },
        )
        assert r.status_code == 200
        assert r.json()["flux"]["cfg"] == 9.5

    @pytest.mark.asyncio
    async def test_update_whisper_model(self, client: AsyncClient):
        r = await client.put("/api/v1/settings", json={"whisper_model": "small"})
        assert r.status_code == 200
        assert r.json()["whisper_model"] == "small"

    @pytest.mark.asyncio
    async def test_update_whisper_language(self, client: AsyncClient):
        r = await client.put(
            "/api/v1/settings", json={"whisper_language": "de"}
        )
        assert r.status_code == 200
        assert r.json()["whisper_language"] == "de"

    @pytest.mark.asyncio
    async def test_update_video_fps(self, client: AsyncClient):
        r = await client.put(
            "/api/v1/settings",
            json={
                "video": {
                    "fps": 60,
                    "resolution": "1920x1080",
                    "codec": "libx264",
                    "audio_codec": "aac",
                    "bitrate": "8000k",
                    "audio_bitrate": "192k",
                    "zoom_amount": 0.05,
                    "transition_duration": 0.5,
                    "template": "documentary",
                }
            },
        )
        assert r.status_code == 200
        assert r.json()["video"]["fps"] == 60

    @pytest.mark.asyncio
    async def test_update_output_naming(self, client: AsyncClient):
        r = await client.put(
            "/api/v1/settings",
            json={
                "output": {
                    "naming_convention": "{project_name}_v2_{timestamp}",
                    "export_format": "mp4",
                    "export_folder": "",
                }
            },
        )
        assert r.status_code == 200
        assert r.json()["output"]["naming_convention"] == "{project_name}_v2_{timestamp}"

    @pytest.mark.asyncio
    async def test_update_partial_flux_only(self, client: AsyncClient):
        """Sending only flux should not break other settings."""
        r = await client.put(
            "/api/v1/settings",
            json={
                "flux": {
                    "steps": 15,
                    "cfg": 7.0,
                    "sampler": "euler",
                    "scheduler": "normal",
                    "width": 1920,
                    "height": 1080,
                    "comfyui_url": "http://127.0.0.1:8188",
                }
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["flux"]["steps"] == 15
        # Other sections still present
        assert "video" in data
        assert "piper" in data

    @pytest.mark.asyncio
    async def test_update_piper_speed(self, client: AsyncClient):
        r = await client.put(
            "/api/v1/settings",
            json={
                "piper": {
                    "model_path": "/models/voice.onnx",
                    "voice": "en_US-lessac-medium",
                    "speed": 1.2,
                    "executable": "piper",
                }
            },
        )
        assert r.status_code == 200
        assert r.json()["piper"]["speed"] == 1.2

    # ── POST /settings/reset ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_reset_settings_returns_200(self, client: AsyncClient):
        r = await client.post("/api/v1/settings/reset")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_settings_restores_defaults(self, client: AsyncClient):
        # Change something first
        await client.put(
            "/api/v1/settings",
            json={
                "flux": {
                    "steps": 99,
                    "cfg": 7.0,
                    "sampler": "euler",
                    "scheduler": "normal",
                    "width": 1920,
                    "height": 1080,
                    "comfyui_url": "http://127.0.0.1:8188",
                }
            },
        )
        # Verify it was changed
        r = await client.get("/api/v1/settings")
        assert r.json()["flux"]["steps"] == 99

        # Reset
        r = await client.post("/api/v1/settings/reset")
        assert r.status_code == 200
        assert r.json()["flux"]["steps"] == 20

    @pytest.mark.asyncio
    async def test_reset_settings_whisper_model(self, client: AsyncClient):
        await client.put("/api/v1/settings", json={"whisper_model": "large"})
        r = await client.post("/api/v1/settings/reset")
        assert r.status_code == 200
        assert r.json()["whisper_model"] == "base"

    @pytest.mark.asyncio
    async def test_reset_settings_returns_all_sections(self, client: AsyncClient):
        r = await client.post("/api/v1/settings/reset")
        data = r.json()
        assert "flux" in data
        assert "piper" in data
        assert "video" in data
        assert "output" in data
        assert "whisper_model" in data
