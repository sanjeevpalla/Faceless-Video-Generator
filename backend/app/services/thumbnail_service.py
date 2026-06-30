import hashlib
import json
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.services.base import BaseService
from app.core.exceptions import ServiceError

# Windows font candidates for Latin text (bold/impact) and Unicode (Indic, CJK, Arabic)
_LATIN_FONTS = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_UNICODE_FONTS = [
    "C:/Windows/Fonts/NirmalaB.ttf",   # bold Nirmala UI — covers all Indic scripts
    "C:/Windows/Fonts/Nirmala.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size: int, text: str = ""):
    from PIL import ImageFont
    has_unicode = any(ord(c) > 127 for c in text)
    for path in (_UNICODE_FONTS if has_unicode else _LATIN_FONTS):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


class ThumbnailGenerationService(BaseService):
    """Generates video thumbnail via ComfyUI FLUX Dev."""

    service_name = "thumbnail_generation"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        comfyui_url: str = "http://127.0.0.1:8188",
        flux_settings: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.comfyui_url = comfyui_url.rstrip("/")
        self.flux_settings = flux_settings or {}
        self.thumbnail_dir = self.get_output_dir("thumbnail")
        self.cache_dir = self.get_output_dir("cache/thumbnail")
        self.client_id = str(uuid.uuid4())

    async def execute(self) -> Dict[str, Any]:
        return await self.generate()

    async def generate(self) -> Dict[str, Any]:
        thumbnail_prompt_file = self.project_dir / "input" / "thumbnail_prompt.txt"
        seo_file = self.project_dir / "input" / "seo.json"

        prompt = ""
        if thumbnail_prompt_file.exists():
            with open(thumbnail_prompt_file, "r", encoding="utf-8") as f:
                prompt = f.read().strip()

        seo_data: Dict[str, Any] = {}
        if seo_file.exists():
            with open(seo_file, "r", encoding="utf-8") as f:
                seo_data = json.load(f)

        if not prompt:
            prompt = seo_data.get("title", "")

        if not prompt:
            prompt = "Professional YouTube thumbnail, eye-catching, vibrant colors, high quality"

        prompt_hash = self._hash_prompt(prompt)
        cached = self.check_cache(prompt_hash)
        if cached:
            await self.report_progress(100, "Thumbnail loaded from cache")
            return cached

        await self.report_progress(10, "Submitting thumbnail to ComfyUI...")
        workflow = self._build_thumbnail_workflow(prompt)

        comfy_job_id = await self._submit_to_comfyui(workflow)
        await self.report_progress(30, "Waiting for ComfyUI to render thumbnail...")

        output_images = await self._poll_comfyui_job(comfy_job_id)
        if not output_images:
            raise ServiceError(self.service_name, "No thumbnail image returned from ComfyUI")

        await self.report_progress(80, "Downloading thumbnail...")
        dest_path = self.thumbnail_dir / "thumbnail.png"
        await self._download_image(output_images[0], dest_path)

        await self.report_progress(90, "Adding text overlay...")
        title = seo_data.get("title", "")
        tags: List[str] = seo_data.get("tags", [])
        if title or tags:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._overlay_keywords, dest_path, title, tags)

        result = {
            "path": str(dest_path),
            "filename": dest_path.name,
            "prompt": prompt,
            "prompt_hash": prompt_hash,
        }

        cache_file = self.cache_dir / f"{prompt_hash}.json"
        with open(cache_file, "w") as f:
            json.dump(result, f)

        await self.report_progress(100, "Thumbnail generation complete")
        return result

    def check_cache(self, prompt_hash: str) -> Optional[Dict[str, Any]]:
        cache_file = self.cache_dir / f"{prompt_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                if Path(data.get("path", "")).exists():
                    return data
            except Exception:
                pass
        return None

    def _hash_prompt(self, prompt: str) -> str:
        settings_str = json.dumps(self.flux_settings, sort_keys=True)
        combined = f"{prompt}|{settings_str}|thumbnail"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _build_thumbnail_workflow(self, prompt: str) -> Dict[str, Any]:
        return {
            "1": {
                "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"},
                "class_type": "UNETLoader",
            },
            "2": {
                "inputs": {
                    "clip_name1": "clip_l.safetensors",
                    "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
                    "type": "flux",
                    "device": "default",
                },
                "class_type": "DualCLIPLoader",
            },
            "3": {
                "inputs": {"vae_name": "ae.safetensors"},
                "class_type": "VAELoader",
            },
            "6": {"inputs": {"text": prompt, "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
            "8": {
                "inputs": {"guidance": self.flux_settings.get("cfg", 3.5), "conditioning": ["6", 0]},
                "class_type": "FluxGuidance",
            },
            "10": {"inputs": {"width": 1280, "height": 720, "batch_size": 1}, "class_type": "EmptyLatentImage"},
            "13": {
                "inputs": {
                    "seed": int(time.time() * 1000) % (2**31),
                    "steps": self.flux_settings.get("steps", 20),
                    "cfg": 1.0,
                    "sampler_name": self.flux_settings.get("sampler", "euler"),
                    "scheduler": self.flux_settings.get("scheduler", "simple"),
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["8", 0],
                    "negative": ["8", 0],
                    "latent_image": ["10", 0],
                },
                "class_type": "KSampler",
            },
            "17": {"inputs": {"samples": ["13", 0], "vae": ["3", 0]}, "class_type": "VAEDecode"},
            "19": {
                "inputs": {"filename_prefix": f"thumbnail_{int(time.time())}", "images": ["17", 0]},
                "class_type": "SaveImage",
            },
        }

    async def _submit_to_comfyui(self, workflow: Dict[str, Any]) -> str:
        payload = {"prompt": workflow, "client_id": self.client_id}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.comfyui_url}/prompt", json=payload)
            if response.status_code != 200:
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text
                self.logger.error(f"ComfyUI /prompt rejected with {response.status_code}: {json.dumps(detail)}")
                response.raise_for_status()
            data = response.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise ServiceError(self.service_name, "ComfyUI did not return a prompt_id")
            return prompt_id

    async def _poll_comfyui_job(self, job_id: str, timeout: int = 300) -> list:
        import asyncio
        deadline = time.time() + timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.time() < deadline:
                await self.check_cancelled()
                await asyncio.sleep(2.0)
                try:
                    response = await client.get(f"{self.comfyui_url}/history/{job_id}")
                    if response.status_code == 200:
                        history = response.json()
                        if job_id in history:
                            outputs = history[job_id].get("outputs", {})
                            for node_output in outputs.values():
                                imgs = node_output.get("images", [])
                                if imgs:
                                    urls = []
                                    for img in imgs:
                                        fn = img.get("filename", "")
                                        sf = img.get("subfolder", "")
                                        urls.append(f"{self.comfyui_url}/view?filename={fn}&subfolder={sf}&type=output")
                                    return urls
                except Exception as exc:
                    self.logger.warning(f"Polling error: {exc}")
        raise ServiceError(self.service_name, f"Thumbnail ComfyUI job {job_id} timed out")

    def _overlay_keywords(self, image_path: Path, title: str, tags: List[str]) -> None:
        from PIL import Image, ImageDraw

        img = Image.open(image_path).convert("RGB")
        W, H = img.size

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Dark gradient band across the bottom third for title legibility
        band_h = H // 3
        for row in range(band_h):
            alpha = int(210 * (row / band_h))
            draw.rectangle([0, H - band_h + row, W, H - band_h + row + 1],
                           fill=(0, 0, 0, alpha))

        # ── Title text (large, centered, bottom area) ────────────────────
        title_font = _load_font(72, title)
        lines = textwrap.wrap(title, width=28)[:2]
        ty = H - band_h + 30
        line_h = 82
        for line in lines:
            # Black outline (8-direction)
            for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3),
                           (-3, 0), (3, 0), (0, -3), (0, 3)]:
                draw.text((W // 2 + dx, ty + dy), line, font=title_font,
                          fill=(0, 0, 0, 255), anchor="mt")
            draw.text((W // 2, ty), line, font=title_font,
                      fill=(255, 255, 255, 255), anchor="mt")
            ty += line_h

        # ── Keyword badges (top-left, YouTube red) ───────────────────────
        kw_font = _load_font(30, " ".join(tags))
        keywords = [t.strip() for t in tags if t.strip()][:4]
        bx, by = 18, 18
        pad_x, pad_y = 14, 8
        for kw in keywords:
            kw_upper = kw.upper() if all(ord(c) < 128 for c in kw) else kw
            bbox = draw.textbbox((0, 0), kw_upper, font=kw_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            rx1, ry1 = bx, by
            rx2, ry2 = bx + tw + pad_x * 2, by + th + pad_y * 2
            # Red badge with slight shadow
            draw.rounded_rectangle([rx1 + 2, ry1 + 2, rx2 + 2, ry2 + 2],
                                   radius=7, fill=(0, 0, 0, 140))
            draw.rounded_rectangle([rx1, ry1, rx2, ry2],
                                   radius=7, fill=(220, 30, 30, 230))
            draw.text((bx + pad_x, by + pad_y), kw_upper, font=kw_font,
                      fill=(255, 255, 255, 255))
            bx = rx2 + 10
            if bx > W - 180:
                bx = 18
                by = ry2 + 8

        # Composite and save
        base = img.convert("RGBA")
        out = Image.alpha_composite(base, overlay).convert("RGB")
        out.save(image_path, format="PNG", optimize=False)
        self.logger.info(f"Thumbnail text overlay applied: {image_path}")

    async def _download_image(self, url: str, dest_path: Path) -> None:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(response.content)
