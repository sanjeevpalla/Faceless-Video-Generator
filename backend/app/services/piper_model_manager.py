"""
Auto-resolves and downloads Piper TTS voice models for non-English languages.

Models are stored in the same directory as the configured English model.
On first use for a given language the .onnx + .onnx.json are downloaded from
the rhasspy/piper-voices HuggingFace repository (verified paths).
"""

import asyncio
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

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
) -> str:
    """
    Returns the Piper model path for `language`, downloading from HuggingFace
    if the .onnx + .onnx.json are not already present alongside base_model_path.

    Falls back to base_model_path for English or languages not in PIPER_VOICES.
    Raises ServiceError on download failure.
    """
    from app.core.exceptions import ServiceError

    if not language or language == "en":
        return base_model_path

    key = _lang_key(language)
    if key not in PIPER_VOICES:
        logger.warning("No Piper voice for '%s', falling back to English model", language)
        return base_model_path

    if not base_model_path:
        raise ServiceError(
            "voice_generation",
            "Piper model path not configured — open Settings → Voice and set the model path first",
        )

    stem, hf_path = PIPER_VOICES[key]
    model_dir = Path(base_model_path).parent
    onnx = model_dir / f"{stem}.onnx"
    onnx_json = model_dir / f"{stem}.onnx.json"

    if onnx.exists() and onnx_json.exists():
        logger.info("Piper model for '%s' already present: %s", language, onnx)
        return str(onnx)

    logger.info("Downloading Piper model for '%s': %s", language, stem)
    if progress_callback:
        await progress_callback(2, f"Downloading Piper voice model for {language}…", {})

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None, _download_file, f"{HF_BASE}/{hf_path}.onnx", onnx
        )
        if progress_callback:
            await progress_callback(4, "Downloading voice model config…", {})
        await loop.run_in_executor(
            None, _download_file, f"{HF_BASE}/{hf_path}.onnx.json", onnx_json
        )
    except Exception as exc:
        onnx.unlink(missing_ok=True)
        onnx_json.unlink(missing_ok=True)
        raise ServiceError(
            "voice_generation",
            f"Failed to download Piper model for '{language}': {exc}",
        )

    logger.info("Piper model ready: %s", onnx)
    return str(onnx)


def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("GET %s", url)
    urllib.request.urlretrieve(url, str(dest))
