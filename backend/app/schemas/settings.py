from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GeminiSettings(BaseModel):
    api_key: str = Field(default="")
    pro_model: str = Field(default="gemini-2.5-flash")           # Steps 1-2: search grounding
    script_model: str = Field(default="gemma-4-31b-it")        # Step 3: heavy reasoning
    flash_model: str = Field(default="gemini-3.1-flash-lite")  # Steps 4-7: fast bulk text
    image_model: str = Field(default="gemini-2.5-flash-preview-image-generation") # Image generation (Gemini backend)
    image_backend: str = Field(default="flux")                 # "flux" | "gemini"
    search_grounding: bool = Field(default=True)


class FluxSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    steps: int = Field(default=20, ge=1, le=100)
    cfg: float = Field(default=3.5, ge=0.0, le=20.0)
    sampler: str = Field(default="euler")
    scheduler: str = Field(default="simple")
    width: int = Field(default=1920)
    height: int = Field(default=1080)
    comfyui_url: str = Field(default="http://127.0.0.1:8188")


class PiperSettings(BaseModel):
    model_path: str = Field(default="")
    voice: str = Field(default="en_US-lessac-medium")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    executable: str = Field(default="piper")


class GoogleTTSSettings(BaseModel):
    api_key: str = Field(default="")
    voice_name: str = Field(default="")
    language_code: str = Field(default="")
    speaking_rate: float = Field(default=1.0, ge=0.25, le=4.0)


class SubtitleStyleSettings(BaseModel):
    font: str = "Arial"
    font_size: int = 24
    color: str = "white"
    stroke_color: str = "black"
    stroke_width: int = 2
    position: str = "bottom"
    background: bool = False
    background_color: str = "rgba(0,0,0,0.5)"


class VideoSettings(BaseModel):
    fps: int = Field(default=30, ge=1, le=60)
    resolution: str = Field(default="1920x1080")
    codec: str = Field(default="libx264")
    audio_codec: str = Field(default="aac")
    bitrate: str = Field(default="8000k")
    audio_bitrate: str = Field(default="192k")
    zoom_amount: float = Field(default=0.05, ge=0.0, le=0.3)
    transition_duration: float = Field(default=0.5, ge=0.0, le=0.5)
    subtitle_style: SubtitleStyleSettings = Field(default_factory=SubtitleStyleSettings)
    template: str = Field(default="documentary")
    burn_subtitles: bool = Field(default=True)
    narrator_enabled: bool = Field(default=False)
    narrator_clips_dir: str = Field(default="")
    narrator_position: str = Field(default="bottom_right")
    narrator_width: int = Field(default=320, ge=100, le=800)
    narrator_margin: int = Field(default=20, ge=0, le=100)
    narrator_bottom_margin: int = Field(default=120, ge=0, le=300)
    narrator_shape: str = Field(default="circle")
    logo_path: str = Field(default="")
    logo_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    logo_scale: float = Field(default=0.10, ge=0.02, le=0.5)
    logo_margin: int = Field(default=20, ge=0, le=100)


class OutputSettings(BaseModel):
    export_folder: str = Field(default="")
    naming_convention: str = Field(default="{project_name}_{timestamp}")
    export_format: str = Field(default="mp4")


class SettingsUpdate(BaseModel):
    flux: Optional[FluxSettings] = None
    piper: Optional[PiperSettings] = None
    google_tts: Optional[GoogleTTSSettings] = None
    tts_engine: Optional[str] = None      # "piper" | "google"
    video: Optional[VideoSettings] = None
    output: Optional[OutputSettings] = None
    gemini: Optional[GeminiSettings] = None
    whisper_model: Optional[str] = None
    whisper_language: Optional[str] = None
    whisper_device: Optional[str] = None


class SettingsResponse(BaseModel):
    flux: FluxSettings = Field(default_factory=FluxSettings)
    piper: PiperSettings = Field(default_factory=PiperSettings)
    google_tts: GoogleTTSSettings = Field(default_factory=GoogleTTSSettings)
    tts_engine: str = "piper"
    video: VideoSettings = Field(default_factory=VideoSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    whisper_model: str = "base"
    whisper_language: str = "en"
    whisper_device: str = "cpu"
