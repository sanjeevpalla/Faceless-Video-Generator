import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.services.base import BaseService
from app.core.exceptions import ServiceError


class ImageGenerationService(BaseService):
    """Generates scene images via ComfyUI FLUX Dev workflow."""

    service_name = "image_generation"

    # FLUX Dev requires separate loaders — the .safetensors file is transformer-only.
    FLUX_WORKFLOW_TEMPLATE = {
        "1": {
            "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"},
            "class_type": "UNETLoader"
        },
        "2": {
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
                "type": "flux",
                "device": "default"
            },
            "class_type": "DualCLIPLoader"
        },
        "3": {
            "inputs": {"vae_name": "ae.safetensors"},
            "class_type": "VAELoader"
        },
        "6": {
            "inputs": {"text": "", "clip": ["2", 0]},
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {"guidance": 3.5, "conditioning": ["6", 0]},
            "class_type": "FluxGuidance"
        },
        "10": {
            "inputs": {"width": 1920, "height": 1080, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "13": {
            "inputs": {
                "seed": 0,
                "steps": 20,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["8", 0],
                "negative": ["8", 0],
                "latent_image": ["10", 0]
            },
            "class_type": "KSampler"
        },
        "17": {
            "inputs": {"samples": ["13", 0], "vae": ["3", 0]},
            "class_type": "VAEDecode"
        },
        "19": {
            "inputs": {"filename_prefix": "scene", "images": ["17", 0]},
            "class_type": "SaveImage"
        }
    }

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
        self.images_dir = self.get_output_dir("images")
        self.cache_dir = self.get_output_dir("cache/images")
        self.client_id = str(uuid.uuid4())

    async def execute(self) -> Dict[str, Any]:
        return await self.generate_all()

    @staticmethod
    def _parse_prompts(content: str) -> List[Dict[str, Any]]:
        """Parse image_prompts.txt into list of {id, prompt} dicts."""
        scenes: List[Dict[str, Any]] = []
        current_id: Optional[int] = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("SCENE_"):
                try:
                    current_id = int(stripped.split("_", 1)[1])
                except (IndexError, ValueError):
                    current_id = None
            elif stripped.upper().startswith("PROMPT:"):
                prompt = stripped[7:].strip()
                if prompt:
                    sid = current_id if current_id is not None else len(scenes) + 1
                    scenes.append({"id": sid, "prompt": prompt})
                    current_id = None
        if not scenes:
            plain_lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            scenes = [{"id": i + 1, "prompt": ln} for i, ln in enumerate(plain_lines)]
        return scenes

    async def generate_section_images(
        self,
        section_label: str,
        section_prompts_path: Path,
    ) -> Dict[str, Any]:
        """Generate FLUX images for one AI News section.

        Reads prompts from section_prompts_path.
        Saves images to images/sections/{label}/scene_NNN.png.
        """
        if not section_prompts_path.exists():
            raise ServiceError(
                self.service_name,
                f"image_prompts.txt not found for section '{section_label}'",
            )

        content = section_prompts_path.read_text(encoding="utf-8")
        scenes  = self._parse_prompts(content)
        if not scenes:
            raise ServiceError(self.service_name, f"No prompts in {section_label}/image_prompts.txt")

        sec_images_dir = self.images_dir / "sections" / section_label
        sec_images_dir.mkdir(parents=True, exist_ok=True)

        original_images_dir = self.images_dir
        self.images_dir = sec_images_dir

        total = len(scenes)
        results, failed = [], []
        try:
            for idx, scene in enumerate(scenes):
                await self.check_cancelled()
                scene_id = scene["id"]
                prompt   = scene["prompt"]
                neg      = "ugly, blurry, watermark, text, low quality, distorted, nsfw"

                existing = sec_images_dir / f"scene_{scene_id:03d}.png"
                if existing.exists():
                    results.append({"scene_id": scene_id, "path": str(existing),
                                    "filename": existing.name, "resumed": True})
                    try:
                        await self.report_progress(
                            (idx + 1) / total * 100,
                            f"Skipped {section_label} scene {scene_id} (exists)",
                            {"scene_id": scene_id, "completed": idx + 1, "total": total, "resumed": True},
                        )
                    except Exception:
                        pass
                    continue

                try:
                    results.append(await self.generate_scene(scene_id, prompt, neg))
                except Exception as exc:
                    self.logger.error("Image gen failed %s scene %d: %s", section_label, scene_id, exc)
                    failed.append({"scene_id": scene_id, "error": str(exc)})

                try:
                    await self.report_progress(
                        (idx + 1) / total * 100,
                        f"Section '{section_label}': image {idx + 1}/{total}",
                        {"scene_id": scene_id, "completed": idx + 1, "total": total},
                    )
                except Exception:
                    pass
        finally:
            self.images_dir = original_images_dir

        await self.report_progress(100, f"Section '{section_label}' images done — {len(results)}/{total}")
        return {"label": section_label, "total": total, "generated": len(results),
                "failed": failed, "images": results}

    async def generate_all(self) -> Dict[str, Any]:
        prompts_file = self.project_dir / "input" / "image_prompts.txt"
        if not prompts_file.exists():
            raise ServiceError(self.service_name, "image_prompts.txt not found in project input directory")

        content = prompts_file.read_text(encoding="utf-8")
        scenes  = self._parse_prompts(content)

        if not scenes:
            raise ServiceError(self.service_name, "No prompts found in image_prompts.txt")
        total = len(scenes)
        results = []
        failed = []

        # Resume support: skip already-generated scenes
        already_done = [
            s["id"] for s in scenes
            if (self.images_dir / f"scene_{s['id']:03d}.png").exists()
        ]
        if already_done:
            self.logger.info(f"Resuming: {len(already_done)}/{total} scenes already generated")

        await self.report_progress(0, f"Starting image generation for {total} scenes")

        for idx, scene in enumerate(scenes):
            await self.check_cancelled()
            scene_id = scene["id"]
            prompt = scene["prompt"]
            negative_prompt = "ugly, blurry, watermark, text, low quality, distorted, nsfw"

            # Skip already-generated scenes (resume support)
            existing_path = self.images_dir / f"scene_{scene_id:03d}.png"
            if existing_path.exists():
                results.append({
                    "scene_id": scene_id,
                    "path": str(existing_path),
                    "filename": existing_path.name,
                    "prompt_hash": self._hash_prompt(prompt),
                    "resumed": True,
                })
                progress = ((idx + 1) / total) * 100
                await self.report_progress(
                    progress,
                    f"Skipped scene {scene_id} (already generated) · {idx + 1}/{total}",
                    {"scene_id": scene_id, "completed": idx + 1, "total": total, "resumed": True},
                )
                continue

            try:
                result = await self.generate_scene(scene_id, prompt, negative_prompt)
                results.append(result)
            except Exception as exc:
                self.logger.error(f"Failed to generate scene {scene_id}: {exc}")
                failed.append({"scene_id": scene_id, "error": str(exc)})

            progress = ((idx + 1) / total) * 100
            await self.report_progress(
                progress,
                f"Generated scene {idx + 1}/{total}",
                {"scene_id": scene_id, "completed": idx + 1, "total": total},
            )

        # Write generation manifest
        manifest = {
            "total": total,
            "generated": len(results),
            "failed": failed,
            "images": results,
        }
        manifest_path = self.images_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        await self.report_progress(100, f"Image generation complete — {len(results)}/{total} generated")
        return manifest

    async def generate_scene(
        self,
        scene_id: Any,
        prompt: str,
        negative_prompt: str = "",
    ) -> Dict[str, Any]:
        prompt_hash = self._hash_prompt(prompt)
        cached = self.check_cache(prompt_hash, scene_id)
        if cached:
            expected_path = self.images_dir / f"scene_{int(scene_id):03d}.png"
            if expected_path.exists():
                self.logger.info(f"Cache hit for scene {scene_id}")
                return cached
            # Cache recorded a different output directory — don't skip, regenerate
            self.logger.info(f"Cache stale for scene {scene_id} (image missing at expected path) — regenerating")

        workflow = self._build_workflow(prompt, negative_prompt)
        comfy_job_id = await self.submit_to_comfyui(workflow)
        output_images = await self.poll_comfyui_job(comfy_job_id)

        if not output_images:
            raise ServiceError(self.service_name, f"No images returned for scene {scene_id}")

        dest_path = self.images_dir / f"scene_{int(scene_id):03d}.png"
        await self.download_image(output_images[0], dest_path)

        result = {
            "scene_id": scene_id,
            "path": str(dest_path),
            "filename": dest_path.name,
            "prompt_hash": prompt_hash,
        }

        # Write cache entry so next run can skip this scene
        cache_file = self.cache_dir / f"{prompt_hash}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f)

        return result

    def check_cache(self, prompt_hash: str, scene_id: Any) -> Optional[Dict[str, Any]]:
        cache_file = self.cache_dir / f"{prompt_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                image_path = Path(data.get("path", ""))
                if image_path.exists():
                    return data
            except Exception:
                pass
        return None

    def _hash_prompt(self, prompt: str) -> str:
        settings_str = json.dumps(self.flux_settings, sort_keys=True)
        combined = f"{prompt}|{settings_str}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _build_workflow(self, prompt: str, negative_prompt: str) -> Dict[str, Any]:
        workflow = json.loads(json.dumps(self.FLUX_WORKFLOW_TEMPLATE))
        workflow["6"]["inputs"]["text"] = prompt
        workflow["8"]["inputs"]["guidance"] = self.flux_settings.get("cfg", 3.5)
        workflow["13"]["inputs"]["seed"] = int(time.time() * 1000) % (2**31)
        workflow["13"]["inputs"]["steps"] = self.flux_settings.get("steps", 20)
        workflow["13"]["inputs"]["sampler_name"] = self.flux_settings.get("sampler", "euler")
        workflow["13"]["inputs"]["scheduler"] = self.flux_settings.get("scheduler", "simple")
        workflow["10"]["inputs"]["width"] = self.flux_settings.get("width", 1920)
        workflow["10"]["inputs"]["height"] = self.flux_settings.get("height", 1080)
        workflow["19"]["inputs"]["filename_prefix"] = f"fvg_{int(time.time())}"
        return workflow

    async def submit_to_comfyui(self, workflow: Dict[str, Any]) -> str:
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

    async def _clear_comfyui_job(self, client: httpx.AsyncClient, job_id: str) -> None:
        """Interrupt ComfyUI and remove this specific job from its queue."""
        try:
            await client.post(f"{self.comfyui_url}/interrupt")
        except Exception as exc:
            self.logger.warning("ComfyUI /interrupt failed: %s", exc)
        try:
            await client.post(f"{self.comfyui_url}/queue", json={"delete": [job_id]})
        except Exception as exc:
            self.logger.warning("ComfyUI queue delete failed for %s: %s", job_id, exc)

    async def poll_comfyui_job(
        self, job_id: str, timeout: int = 3600, poll_interval: float = 2.0
    ) -> List[str]:
        deadline = time.time() + timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.time() < deadline:
                try:
                    await self.check_cancelled()
                except Exception:
                    await self._clear_comfyui_job(client, job_id)
                    raise
                await asyncio.sleep(poll_interval)
                try:
                    response = await client.get(f"{self.comfyui_url}/history/{job_id}")
                    if response.status_code == 200:
                        history = response.json()
                        if job_id in history:
                            job = history[job_id]
                            status = job.get("status", {})
                            # Fail fast on ComfyUI execution errors
                            if status.get("status_str") == "error":
                                messages = status.get("messages", [])
                                err_msg = next(
                                    (m[1].get("exception_message", "unknown error")
                                     for m in messages if m[0] == "execution_error"),
                                    "ComfyUI execution failed"
                                )
                                raise ServiceError(self.service_name, f"ComfyUI error: {err_msg}")
                            outputs = job.get("outputs", {})
                            image_urls = []
                            for node_id, node_output in outputs.items():
                                for img in node_output.get("images", []):
                                    filename = img.get("filename", "")
                                    subfolder = img.get("subfolder", "")
                                    url = f"{self.comfyui_url}/view?filename={filename}&subfolder={subfolder}&type=output"
                                    image_urls.append(url)
                            if image_urls:
                                return image_urls
                except ServiceError:
                    raise
                except Exception as exc:
                    self.logger.warning(f"Error polling ComfyUI: {exc}")
        raise ServiceError(self.service_name, f"ComfyUI job {job_id} timed out after {timeout}s")

    async def download_image(self, url: str, dest_path: Path) -> None:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(response.content)
        self.logger.info(f"Downloaded image to {dest_path}")

    async def retry_failed(self, failed_scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for scene_info in failed_scenes:
            scene_id = scene_info.get("scene_id")
            prompt = scene_info.get("prompt", "")
            try:
                result = await self.generate_scene(scene_id, prompt)
                results.append(result)
            except Exception as exc:
                self.logger.error(f"Retry failed for scene {scene_id}: {exc}")
        return {"retried": len(failed_scenes), "succeeded": len(results)}
