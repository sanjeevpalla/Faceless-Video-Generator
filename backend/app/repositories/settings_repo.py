from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import Setting
from app.schemas.settings import FluxSettings, GeminiSettings, GoogleTTSSettings, PiperSettings, VideoSettings, OutputSettings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SETTINGS = {
    "flux.steps": 20,
    "flux.cfg": 7.0,
    "flux.sampler": "euler",
    "flux.scheduler": "normal",
    "flux.width": 1920,
    "flux.height": 1080,
    "flux.comfyui_url": "http://127.0.0.1:8188",
    "gemini.api_key": "",
    "gemini.pro_model": "gemini-2.5-flash",
    "gemini.script_model": "gemma-4-31b-it",
    "gemini.flash_model": "gemini-3.1-flash-lite",
    "gemini.image_model": "gemini-3.1-flash-image",
    "gemini.image_backend": "flux",
    "gemini.search_grounding": True,
    "piper.model_path": "",
    "piper.voice": "en_US-lessac-medium",
    "piper.speed": 1.0,
    "piper.executable": "piper",
    "video.fps": 30,
    "video.resolution": "1920x1080",
    "video.codec": "libx264",
    "video.audio_codec": "aac",
    "video.bitrate": "8000k",
    "video.audio_bitrate": "192k",
    "video.zoom_amount": 0.05,
    "video.transition_duration": 0.5,
    "video.template": "documentary",
    "video.burn_subtitles": True,
    "video.narrator_enabled": False,
    "video.narrator_clips_dir": "",
    "video.narrator_position": "bottom_right",
    "video.narrator_width": 320,
    "video.narrator_margin": 20,
    "video.narrator_bottom_margin": 120,
    "video.narrator_shape": "circle",
    "video.logo_path": "",
    "video.logo_opacity": 1.0,
    "video.logo_scale": 0.10,
    "video.logo_margin": 20,
    "output.export_folder": "",
    "output.naming_convention": "{project_name}_{timestamp}",
    "output.export_format": "mp4",
    "whisper.model": "base",
    "whisper.language": "en",
    "whisper.device": "cuda",
    "tts.engine": "piper",
    "google_tts.api_key": "",
    "google_tts.voice_name": "",
    "google_tts.language_code": "",
    "google_tts.speaking_rate": 1.0,
}


class SettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> Dict[str, Any]:
        result = await self.db.execute(select(Setting))
        settings = result.scalars().all()
        return {s.key: s.value for s in settings}

    async def get_by_key(self, key: str) -> Optional[Any]:
        result = await self.db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            return setting.value
        return DEFAULT_SETTINGS.get(key)

    async def set_value(self, key: str, value: Any, category: Optional[str] = None) -> Setting:
        result = await self.db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
            if category:
                setting.category = category
        else:
            setting = Setting(
                key=key,
                value=value,
                updated_at=datetime.utcnow(),
                category=category or key.split(".")[0],
            )
            self.db.add(setting)
        await self.db.flush()
        return setting

    async def set_bulk(self, settings_dict: Dict[str, Any]) -> None:
        for key, value in settings_dict.items():
            await self.set_value(key, value, category=key.split(".")[0])

    async def init_defaults(self) -> None:
        existing = await self.get_all()
        for key, value in DEFAULT_SETTINGS.items():
            if key not in existing:
                await self.set_value(key, value, category=key.split(".")[0])
        logger.info("Settings defaults initialized.")

    async def get_gemini_settings(self) -> GeminiSettings:
        all_settings = await self.get_all()
        merged = {**{k.replace("gemini.", ""): v for k, v in DEFAULT_SETTINGS.items() if k.startswith("gemini.")}}
        merged.update({k.replace("gemini.", ""): v for k, v in all_settings.items() if k.startswith("gemini.")})
        return GeminiSettings(**merged)

    async def get_flux_settings(self) -> FluxSettings:
        all_settings = await self.get_all()
        merged = {**{k.replace("flux.", ""): v for k, v in DEFAULT_SETTINGS.items() if k.startswith("flux.")}}
        merged.update({k.replace("flux.", ""): v for k, v in all_settings.items() if k.startswith("flux.")})
        return FluxSettings(**merged)

    async def get_piper_settings(self) -> PiperSettings:
        all_settings = await self.get_all()
        merged = {**{k.replace("piper.", ""): v for k, v in DEFAULT_SETTINGS.items() if k.startswith("piper.")}}
        merged.update({k.replace("piper.", ""): v for k, v in all_settings.items() if k.startswith("piper.")})
        return PiperSettings(**merged)

    async def get_video_settings(self) -> VideoSettings:
        all_settings = await self.get_all()
        merged = {**{k.replace("video.", ""): v for k, v in DEFAULT_SETTINGS.items() if k.startswith("video.")}}
        merged.update({k.replace("video.", ""): v for k, v in all_settings.items() if k.startswith("video.")})
        return VideoSettings(**merged)

    async def get_output_settings(self) -> OutputSettings:
        all_settings = await self.get_all()
        merged = {**{k.replace("output.", ""): v for k, v in DEFAULT_SETTINGS.items() if k.startswith("output.")}}
        merged.update({k.replace("output.", ""): v for k, v in all_settings.items() if k.startswith("output.")})
        return OutputSettings(**merged)

    async def get_google_tts_settings(self) -> GoogleTTSSettings:
        all_settings = await self.get_all()
        merged = {**{k.replace("google_tts.", ""): v for k, v in DEFAULT_SETTINGS.items() if k.startswith("google_tts.")}}
        merged.update({k.replace("google_tts.", ""): v for k, v in all_settings.items() if k.startswith("google_tts.")})
        return GoogleTTSSettings(**merged)
