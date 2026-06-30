import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends

from app.config import get_settings as get_app_settings
from app.core.dependencies import get_settings_repo
from app.repositories.settings_repo import SettingsRepository
from app.schemas.settings import (
    FluxSettings,
    GeminiSettings,
    GoogleTTSSettings,
    OutputSettings,
    PiperSettings,
    SettingsResponse,
    SettingsUpdate,
    VideoSettings,
)

router = APIRouter()


def _default_narrator_dir() -> str:
    cfg = get_app_settings()
    d = cfg.BASE_DIR / "narrator"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


@router.get("/narrator-default-dir")
async def narrator_default_dir():
    """Return the default narrator clips folder (app_root/narrator)."""
    return {"path": _default_narrator_dir()}


def _open_folder_dialog(initial_dir: str) -> str:
    """Open a native OS folder picker (runs in thread pool)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(
            title="Select Narrator Clips Folder",
            initialdir=initial_dir if initial_dir else "/",
        )
        root.destroy()
        return path or ""
    except Exception:
        return ""


@router.post("/browse-folder")
async def browse_folder():
    """Open a native folder picker dialog and return the chosen path."""
    initial = _default_narrator_dir()
    path = await asyncio.get_event_loop().run_in_executor(None, _open_folder_dialog, initial)
    return {"path": path}


def _open_file_dialog(title: str, filetypes: list) -> str:
    """Open a native OS file picker."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return path or ""
    except Exception:
        return ""


@router.post("/browse-logo")
async def browse_logo():
    """Open a native file picker for selecting a logo image."""
    path = await asyncio.get_event_loop().run_in_executor(
        None,
        _open_file_dialog,
        "Select Logo Image",
        [("Image files", "*.png *.jpg *.jpeg *.webp *.gif"), ("PNG files", "*.png"), ("All files", "*.*")],
    )
    return {"path": path}


@router.get("", response_model=SettingsResponse)
async def get_settings(
    repo: SettingsRepository = Depends(get_settings_repo),
):
    flux = await repo.get_flux_settings()
    piper = await repo.get_piper_settings()
    google_tts = await repo.get_google_tts_settings()
    video = await repo.get_video_settings()
    output = await repo.get_output_settings()
    gemini = await repo.get_gemini_settings()
    whisper_model = await repo.get_by_key("whisper.model") or "base"
    whisper_language = await repo.get_by_key("whisper.language") or "en"
    whisper_device = await repo.get_by_key("whisper.device") or "cpu"
    tts_engine = await repo.get_by_key("tts.engine") or "piper"

    return SettingsResponse(
        flux=flux,
        piper=piper,
        google_tts=google_tts,
        tts_engine=str(tts_engine),
        video=video,
        output=output,
        gemini=gemini,
        whisper_model=str(whisper_model),
        whisper_language=str(whisper_language),
        whisper_device=str(whisper_device),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    data: SettingsUpdate,
    repo: SettingsRepository = Depends(get_settings_repo),
):
    if data.flux:
        flux_dict = {f"flux.{k}": v for k, v in data.flux.model_dump().items()}
        await repo.set_bulk(flux_dict)

    if data.piper:
        piper_dict = {f"piper.{k}": v for k, v in data.piper.model_dump().items()}
        await repo.set_bulk(piper_dict)

    if data.google_tts:
        gtts_dict = {f"google_tts.{k}": v for k, v in data.google_tts.model_dump().items()}
        await repo.set_bulk(gtts_dict)

    if data.tts_engine is not None:
        await repo.set_value("tts.engine", data.tts_engine, category="tts")

    if data.video:
        video_data = data.video.model_dump()
        subtitle_style = video_data.pop("subtitle_style", {})
        video_dict = {f"video.{k}": v for k, v in video_data.items()}
        video_dict["video.subtitle_style"] = subtitle_style
        await repo.set_bulk(video_dict)

    if data.output:
        output_dict = {f"output.{k}": v for k, v in data.output.model_dump().items()}
        await repo.set_bulk(output_dict)

    if data.gemini:
        gemini_dict = {f"gemini.{k}": v for k, v in data.gemini.model_dump().items()}
        await repo.set_bulk(gemini_dict)

    if data.whisper_model is not None:
        await repo.set_value("whisper.model", data.whisper_model, category="whisper")

    if data.whisper_language is not None:
        await repo.set_value("whisper.language", data.whisper_language, category="whisper")

    if data.whisper_device is not None:
        await repo.set_value("whisper.device", data.whisper_device, category="whisper")

    return await get_settings(repo=repo)


@router.get("/gemini/image-models")
async def list_gemini_image_models(
    repo: SettingsRepository = Depends(get_settings_repo),
):
    """List Gemini API models that can generate images, for the settings UI model picker."""
    from fastapi import HTTPException

    gemini = await repo.get_gemini_settings()
    if not gemini.api_key:
        raise HTTPException(status_code=400, detail="Gemini API key not configured")

    try:
        from google import genai as google_genai
        client = google_genai.Client(api_key=gemini.api_key)

        def _list() -> list:
            out = []
            for m in client.models.list():
                raw_name = m.name or ""
                short = raw_name.replace("models/", "")
                methods = list(getattr(m, "supported_generation_methods", None) or [])
                out.append({
                    "name": short,
                    "display_name": getattr(m, "display_name", short) or short,
                    "methods": methods,
                    "image_capable": (
                        "generateImages" in methods
                        or "image" in short.lower()
                    ),
                })
            return out

        import asyncio
        models = await asyncio.get_event_loop().run_in_executor(None, _list)
        image_models = [m for m in models if m["image_capable"]]
        return {"models": image_models, "all_count": len(models)}

    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/reset", response_model=SettingsResponse)
async def reset_settings(
    repo: SettingsRepository = Depends(get_settings_repo),
):
    from app.repositories.settings_repo import DEFAULT_SETTINGS
    await repo.set_bulk(DEFAULT_SETTINGS)
    return await get_settings(repo=repo)
