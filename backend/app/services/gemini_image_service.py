"""
GeminiImageService — generates scene images via gemini-2.5-flash-preview-image-generation.

Free tier: 15 RPM / 1,500 RPD → enforces ≥4s between requests.
Images are saved as PNG to project/images/scene_NNN.png.
"""
from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path
from typing import Callable, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

_API_TIMEOUT = 120.0   # seconds per image request before giving up


class GeminiImageService:
    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        api_key: str,
        model: str = "gemini-2.5-flash-preview-image-generation",
        progress_callback: Optional[Callable] = None,
    ) -> None:
        self.project_id = project_id
        self.project_dir = project_dir
        self.api_key = api_key
        self.model = model
        self.progress_callback = progress_callback
        self.images_dir = project_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._last_call: float = 0.0

    async def _rate_limit(self) -> None:
        """Enforce minimum 4s between requests (≤15 RPM free tier)."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < 4.0:
            await asyncio.sleep(4.0 - elapsed)
        self._last_call = time.monotonic()

    async def _report(self, progress: float, message: str, data: Optional[dict] = None) -> None:
        if self.progress_callback:
            await self.progress_callback(progress, message, data or {})

    async def _generate_async(self, prompt: str) -> bytes:
        """Returns raw PNG bytes. Detects Imagen vs Gemini model and uses the right API."""
        from google import genai as google_genai
        from google.genai import types as gtypes

        client = google_genai.Client(api_key=self.api_key)

        # Imagen models (imagen-*) use generate_images; Gemini models use generate_content
        if self.model.startswith("imagen"):
            response = await asyncio.wait_for(
                client.aio.models.generate_images(
                    model=self.model,
                    prompt=prompt,
                    config=gtypes.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="16:9",
                        output_mime_type="image/png",
                    ),
                ),
                timeout=_API_TIMEOUT,
            )
            for img in (response.generated_images or []):
                raw = getattr(img.image, "image_bytes", None)
                if raw:
                    return bytes(raw) if not isinstance(raw, bytes) else raw
            raise RuntimeError(f"Imagen model '{self.model}' returned no image bytes")

        # Gemini multimodal image generation (gemini-* models)
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=gtypes.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            ),
            timeout=_API_TIMEOUT,
        )
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    data = part.inline_data.data
                    if isinstance(data, (bytes, bytearray)):
                        return bytes(data)
                    if isinstance(data, str):
                        return base64.b64decode(data)
        raise RuntimeError(
            f"Model '{self.model}' returned no image. "
            "Go to Settings → Gemini AI → click 'Fetch' to discover available image models."
        )

    async def generate_scene(self, scene_id: int, prompt: str) -> dict:
        """Generate one scene image. Returns result dict."""
        await self._rate_limit()
        logger.info("Generating scene %d via Gemini (%s)…", scene_id, self.model)
        image_bytes = await self._generate_async(prompt)
        filename = f"scene_{scene_id:03d}.png"
        dest = self.images_dir / filename
        dest.write_bytes(image_bytes)
        return {"scene_id": scene_id, "filename": filename, "size": dest.stat().st_size}

    async def generate_section_images(
        self,
        section_label: str,
        section_prompts_path: "Path",
    ) -> dict:
        """Generate Gemini images for one AI News section.

        Reads prompts from section_prompts_path.
        Saves images to images/sections/{label}/scene_NNN.png.
        """
        from pathlib import Path as _Path
        if not section_prompts_path.exists():
            raise RuntimeError(f"image_prompts.txt not found for section '{section_label}'")

        content = section_prompts_path.read_text(encoding="utf-8")
        # Parse PROMPT: blocks or plain lines
        prompts: List[str] = []
        current_prompt: str = ""
        for line in content.splitlines():
            s = line.strip()
            if s.upper().startswith("PROMPT:"):
                current_prompt = s[7:].strip()
                if current_prompt:
                    prompts.append(current_prompt)
                    current_prompt = ""
        if not prompts:
            prompts = [ln.strip() for ln in content.splitlines() if ln.strip()
                       and not ln.strip().upper().startswith(("SCENE_", "IMAGE_FILE:"))]

        if not prompts:
            raise RuntimeError(f"No prompts in {section_label}/image_prompts.txt")

        sec_images_dir = self.images_dir / "sections" / section_label
        sec_images_dir.mkdir(parents=True, exist_ok=True)

        original_images_dir = self.images_dir
        self.images_dir = sec_images_dir

        total = len(prompts)
        generated = 0
        errors: list = []
        try:
            for i, prompt in enumerate(prompts):
                scene_id = i + 1
                dest = sec_images_dir / f"scene_{scene_id:03d}.png"
                if dest.exists():
                    generated += 1
                    await self._report(
                        generated / total * 100,
                        f"Skipped {section_label} scene {scene_id} (exists)",
                        {"scene_id": scene_id, "completed": generated, "total": total, "resumed": True},
                    )
                    continue
                await self._report(
                    generated / total * 100,
                    f"Section '{section_label}': image {scene_id}/{total}…",
                    {"scene_id": scene_id},
                )
                try:
                    await self.generate_scene(scene_id, prompt)
                    generated += 1
                    await self._report(
                        generated / total * 100,
                        f"Section '{section_label}': image {scene_id} done",
                        {"scene_id": scene_id, "completed": generated, "total": total},
                    )
                except Exception as exc:
                    errors.append({"scene_id": scene_id, "error": str(exc)})
                    logger.error("Section %s image %d failed: %s", section_label, scene_id, exc)
        finally:
            self.images_dir = original_images_dir

        await self._report(100, f"Section '{section_label}' images done — {generated}/{total}")
        return {"label": section_label, "total": total, "generated": generated, "errors": errors}

    async def generate_all(self, prompts: List[str]) -> dict:
        """Generate images for all prompts sequentially with rate limiting and resume support."""
        total = len(prompts)
        generated = 0
        errors: list = []

        # Count already-done scenes for resume
        already_done = sum(
            1 for i in range(total)
            if (self.images_dir / f"scene_{i + 1:03d}.png").exists()
        )
        if already_done:
            logger.info("Resuming Gemini image generation: %d/%d already done", already_done, total)

        await self._report(
            (already_done / total) * 100 if total else 0,
            f"Starting Gemini image generation ({total - already_done} remaining of {total})…",
        )

        for i, prompt in enumerate(prompts):
            scene_id = i + 1

            # Resume: skip already-generated scenes
            dest = self.images_dir / f"scene_{scene_id:03d}.png"
            if dest.exists():
                generated += 1
                await self._report(
                    (generated / total) * 100,
                    f"Skipped scene {scene_id}/{total} (already generated)",
                    {"scene_id": scene_id, "completed": generated, "total": total, "resumed": True},
                )
                continue

            # Report BEFORE the API call so the UI shows which scene is being worked on
            await self._report(
                ((generated + already_done) / total) * 100,
                f"Generating scene {scene_id}/{total}…",
                {"scene_id": scene_id},
            )

            try:
                result = await self.generate_scene(scene_id, prompt)
                generated += 1
                logger.info("Scene %d done — %s", scene_id, result["filename"])
                await self._report(
                    (generated / total) * 100,
                    f"Scene {scene_id} done · {generated}/{total} complete",
                    {"scene_id": scene_id, "completed": generated, "total": total},
                )
            except asyncio.TimeoutError:
                msg = f"Scene {scene_id} timed out after {int(_API_TIMEOUT)}s — skipping"
                logger.error(msg)
                errors.append({"scene_id": scene_id, "error": "timeout"})
                await self._report(
                    (generated / total) * 100,
                    f"Scene {scene_id} timed out — continuing",
                    {"scene_id": scene_id, "error": "timeout"},
                )
            except Exception as exc:
                err_str = str(exc)
                logger.error("Scene %d failed: %s", scene_id, err_str)
                errors.append({"scene_id": scene_id, "error": err_str})
                await self._report(
                    (generated / total) * 100,
                    f"Scene {scene_id} failed: {err_str[:120]}",
                    {"scene_id": scene_id, "error": err_str},
                )

        await self._report(
            100,
            f"Done — {generated}/{total} images generated"
            + (f" · {len(errors)} failed" if errors else ""),
            {"generated": generated, "errors": len(errors)},
        )
        return {"total": total, "generated": generated, "errors": errors}
