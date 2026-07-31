"""
Auto-resolves and downloads Piper TTS voice models for non-English languages.

Models are stored in the same directory as the configured English model.
On first use for a given language the .onnx + .onnx.json are downloaded from
the rhasspy/piper-voices HuggingFace repository (verified paths).
"""

import asyncio
import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
_MANIFEST_URL = f"{HF_BASE}/voices.json"
_MANIFEST_TTL_SECONDS = 7 * 24 * 3600

# 2-letter ISO code -> (model_stem, hf_path_without_extension)
# All paths verified against https://huggingface.co/rhasspy/piper-voices/tree/main
PIPER_VOICES: Dict[str, Tuple[str, str]] = {
    # Indian languages — all male voices
    "te": ("te_IN-venkatesh-medium", "te/te_IN/venkatesh/medium/te_IN-venkatesh-medium"),
    "hi": ("hi_IN-rohan-medium",     "hi/hi_IN/rohan/medium/hi_IN-rohan-medium"),
    "ml": ("ml_IN-arjun-medium",     "ml/ml_IN/arjun/medium/ml_IN-arjun-medium"),
    "ur": ("ur_PK-fasih-medium",     "ur/ur_PK/fasih/medium/ur_PK-fasih-medium"),
    # Middle East — male
    "ar": ("ar_JO-kareem-medium",    "ar/ar_JO/kareem/medium/ar_JO-kareem-medium"),
    # European — all male voices
    "de": ("de_DE-thorsten-medium",  "de/de_DE/thorsten/medium/de_DE-thorsten-medium"),
    "fr": ("fr_FR-tom-medium",       "fr/fr_FR/tom/medium/fr_FR-tom-medium"),
    "es": ("es_ES-carlfm-x_low",    "es/es_ES/carlfm/x_low/es_ES-carlfm-x_low"),
    "pt": ("pt_BR-edresson-low",     "pt/pt_BR/edresson/low/pt_BR-edresson-low"),
    "it": ("it_IT-riccardo-x_low",   "it/it_IT/riccardo/x_low/it_IT-riccardo-x_low"),
    "ru": ("ru_RU-denis-medium",     "ru/ru_RU/denis/medium/ru_RU-denis-medium"),
    # East Asian — male
    "zh": ("zh_CN-chaowen-medium",   "zh/zh_CN/chaowen/medium/zh_CN-chaowen-medium"),
}


def _lang_key(language: str) -> str:
    """'te_IN' -> 'te', 'zh-CN' -> 'zh', 'te' -> 'te'."""
    return language.lower().replace("-", "_").split("_")[0]


def _manifest_cache_path() -> Path:
    from app.config import get_settings
    return get_settings().TEMP_DIR / "piper_voices_manifest.json"


async def _load_manifest() -> Dict[str, Any]:
    """Loads the full rhasspy/piper-voices catalog (voices.json), downloading a
    fresh copy if the cached copy is missing or older than 7 days. Falls back to
    a stale cached copy — or an empty catalog — if the network is unavailable,
    rather than raising."""
    cache_path = _manifest_cache_path()
    is_stale = (
        not cache_path.exists()
        or (time.time() - cache_path.stat().st_mtime) > _MANIFEST_TTL_SECONDS
    )
    if is_stale:
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, _download_file, _MANIFEST_URL, cache_path)
        except Exception as exc:
            if not cache_path.exists():
                logger.warning("Could not download Piper voice manifest: %s", exc)
                return {}
            logger.warning("Could not refresh Piper voice manifest, using stale cache: %s", exc)

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Could not read Piper voice manifest: %s", exc)
        return {}


async def fetch_voice_catalog(language: str) -> List[Dict[str, Any]]:
    """Named, single-speaker Piper voices available for `language`, for a UI
    picker. Excludes multi-speaker models (e.g. en_US-libritts-high has 904
    anonymous numbered speakers) — only voices with exactly one named speaker
    are offered, since an anonymous speaker ID isn't a meaningful choice."""
    key = _lang_key(language)
    manifest = await _load_manifest()
    catalog: List[Dict[str, Any]] = []
    for voice_id, entry in manifest.items():
        lang_info = entry.get("language") or {}
        if lang_info.get("family") != key:
            continue
        if entry.get("num_speakers", 1) != 1:
            continue
        catalog.append({
            "id": voice_id,
            "label": entry.get("name", voice_id),
            "quality": entry.get("quality", ""),
            "region": lang_info.get("region", ""),
        })
    catalog.sort(key=lambda v: str(v["id"]))
    return catalog


async def _resolve_voice_files(voice_id: str) -> Optional[Tuple[str, str, str]]:
    """Returns (stem, onnx_relative_path, onnx_json_relative_path) for an
    explicit voice_id looked up in the manifest, or None if not found."""
    manifest = await _load_manifest()
    entry = manifest.get(voice_id)
    if not entry:
        return None
    files = entry.get("files", {})
    onnx_path = next((p for p in files if p.endswith(".onnx")), None)
    onnx_json_path = next((p for p in files if p.endswith(".onnx.json")), None)
    if not onnx_path or not onnx_json_path:
        return None
    return voice_id, onnx_path, onnx_json_path


async def _download_voice(
    stem: str, onnx_url: str, onnx_json_url: str, model_dir: Path,
    progress_callback=None, label: str = "",
) -> str:
    from app.core.exceptions import ServiceError

    onnx = model_dir / f"{stem}.onnx"
    onnx_json = model_dir / f"{stem}.onnx.json"

    if onnx.exists() and onnx_json.exists():
        logger.info("Piper model '%s' already present: %s", label or stem, onnx)
        return str(onnx)

    logger.info("Downloading Piper model '%s': %s", label or stem, stem)
    if progress_callback:
        await progress_callback(2, f"Downloading Piper voice model for {label or stem}…", {})

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _download_file, onnx_url, onnx)
        if progress_callback:
            await progress_callback(4, "Downloading voice model config…", {})
        await loop.run_in_executor(None, _download_file, onnx_json_url, onnx_json)
    except Exception as exc:
        onnx.unlink(missing_ok=True)
        onnx_json.unlink(missing_ok=True)
        raise ServiceError(
            "voice_generation",
            f"Failed to download Piper model for '{label or stem}': {exc}",
        )

    logger.info("Piper model ready: %s", onnx)
    return str(onnx)


def voice_label(language: str) -> str:
    """Display name of the Piper voice that would be used for `language`,
    without downloading or touching the filesystem — for read-only previews."""
    if not language or language == "en":
        return "English (base model)"
    key = _lang_key(language)
    entry = PIPER_VOICES.get(key)
    if not entry:
        return "unsupported — falls back to English model"
    stem, _ = entry
    return stem


def resolve_model_path(language: str, base_model_path: str) -> Optional[str]:
    """
    Returns the on-disk path of the language model if it already exists.
    Returns base_model_path unchanged for English or unsupported languages.
    Returns None when a language model is expected but not yet downloaded.
    """
    if not language or language == "en":
        return base_model_path or None

    key = _lang_key(language)
    if key not in PIPER_VOICES:
        logger.warning("No Piper voice registered for '%s', using English model", language)
        return base_model_path or None

    if not base_model_path:
        return None

    stem, _ = PIPER_VOICES[key]
    candidate = Path(base_model_path).parent / f"{stem}.onnx"
    return str(candidate) if candidate.exists() else None


async def ensure_model(
    language: str,
    base_model_path: str,
    progress_callback=None,
    voice_id: Optional[str] = None,
) -> str:
    """
    Returns the Piper model path for `language`, downloading from HuggingFace
    if the .onnx + .onnx.json are not already present alongside base_model_path.

    When `voice_id` is given (an explicit user selection, a key into the
    voices.json manifest), it takes precedence over the PIPER_VOICES default —
    falling back to the default if the id can't be resolved. Falls back to
    base_model_path for English or languages with no registered voice.
    Raises ServiceError on download failure.
    """
    from app.core.exceptions import ServiceError

    if not language or language == "en":
        return base_model_path

    if not base_model_path:
        raise ServiceError(
            "voice_generation",
            "Piper model path not configured — open Settings → Voice and set the model path first",
        )
    model_dir = Path(base_model_path).parent

    if voice_id:
        resolved = await _resolve_voice_files(voice_id)
        if resolved:
            stem, onnx_rel, onnx_json_rel = resolved
            return await _download_voice(
                stem, f"{HF_BASE}/{onnx_rel}", f"{HF_BASE}/{onnx_json_rel}",
                model_dir, progress_callback, label=voice_id,
            )
        logger.warning(
            "Explicit Piper voice_id '%s' not found in manifest — falling back to default for '%s'",
            voice_id, language,
        )

    key = _lang_key(language)
    if key not in PIPER_VOICES:
        logger.warning("No Piper voice for '%s', falling back to English model", language)
        return base_model_path

    stem, hf_path = PIPER_VOICES[key]
    return await _download_voice(
        stem, f"{HF_BASE}/{hf_path}.onnx", f"{HF_BASE}/{hf_path}.onnx.json",
        model_dir, progress_callback, label=language,
    )


def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("GET %s", url)
    urllib.request.urlretrieve(url, str(dest))
