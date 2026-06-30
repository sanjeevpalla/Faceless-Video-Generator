import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "config" / "default.json"


def load_default_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Faceless Video Generator"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Paths
    BASE_DIR: Path = BASE_DIR
    PROJECTS_DIR: Path = BASE_DIR / "projects"
    DB_PATH: Path = BASE_DIR / "database" / "faceless.db"
    LOG_DIR: Path = BASE_DIR / "logs"
    TEMP_DIR: Path = BASE_DIR / "temp"

    # ComfyUI / FLUX
    COMFYUI_URL: str = "http://127.0.0.1:8188"
    FLUX_STEPS: int = 20
    FLUX_CFG: float = 7.0
    FLUX_SAMPLER: str = "euler"
    FLUX_SCHEDULER: str = "normal"
    FLUX_WIDTH: int = 1920
    FLUX_HEIGHT: int = 1080

    # Piper TTS
    PIPER_MODEL_PATH: str = str(BASE_DIR / "models" / "piper" / "en_US-lessac-medium.onnx")
    PIPER_EXECUTABLE: str = "piper"
    PIPER_SPEED: float = 1.0

    # Whisper
    WHISPER_MODEL: str = "base"
    WHISPER_LANGUAGE: str = "en"
    WHISPER_DEVICE: str = "cpu"

    # Video
    VIDEO_FPS: int = 30
    VIDEO_RESOLUTION: str = "1920x1080"
    VIDEO_CODEC: str = "libx264"
    AUDIO_CODEC: str = "aac"
    VIDEO_BITRATE: str = "8000k"
    AUDIO_BITRATE: str = "192k"

    # Ken Burns effect
    ZOOM_AMOUNT: float = 0.05
    TRANSITION_DURATION: float = 0.5

    # Output
    OUTPUT_DIR: str = str(BASE_DIR / "output")
    NAMING_CONVENTION: str = "{project_name}_{timestamp}"

    # Queue
    MAX_CONCURRENT_JOBS: int = 1
    JOB_TIMEOUT: int = 3600

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True}

    @model_validator(mode="after")
    def create_required_dirs(self) -> "Settings":
        for path in [self.PROJECTS_DIR, self.LOG_DIR, self.TEMP_DIR]:
            path.mkdir(parents=True, exist_ok=True)
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return self

    def get_db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.DB_PATH}"

    def get_video_width(self) -> int:
        return int(self.VIDEO_RESOLUTION.split("x")[0])

    def get_video_height(self) -> int:
        return int(self.VIDEO_RESOLUTION.split("x")[1])


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        defaults = load_default_config()
        env_overrides = {}
        for key, value in defaults.items():
            env_key = key.upper()
            if env_key not in os.environ:
                env_overrides[env_key] = str(value)
        for k, v in env_overrides.items():
            os.environ.setdefault(k, v)
        _settings_instance = Settings()
    return _settings_instance
