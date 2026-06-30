"""
LTXComfyService — animates FLUX scene images into video clips via ComfyUI + LTX-Video.

Models required (all in ComfyUI shared model paths):
  checkpoints/ltxv-2b-0.9.8-distilled-fp8.safetensors
  vae/ltxv-vae.safetensors
  text_encoders/t5xxl_fp8_e4m3fn.safetensors   (shared with FLUX)

Custom nodes required:
  comfyui-videohelpersuite  (VHS_VideoCombine)

Native ComfyUI nodes used (comfy_extras/nodes_lt.py, ComfyUI 0.25+):
  LTXVImgToVideo, LTXVConditioning, ModelSamplingLTXV, LTXVScheduler
"""
import asyncio
import json
import math
import random
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

from app.core.exceptions import ServiceError
from app.services.base import BaseService

_CHECKPOINT = "ltxv-2b-0.9.8-distilled-fp8.safetensors"
_CLIP = "t5xxl_fp8_e4m3fn.safetensors"

_OUTPUT_FPS = 25
_MIN_FRAMES = 9
_MAX_FRAMES = 257
_FRAMES_STEP = 8
_DEFAULT_FRAMES = 97   # ~3.9 s at 25 fps
_DEFAULT_WIDTH = 1280
_DEFAULT_HEIGHT = 720
_DEFAULT_STEPS = 8     # distilled LTX-Video needs only 4–8 steps

# Ken Burns animation styles — picked deterministically by (scene_id % len)
_KEN_BURNS_STYLES = [
    ("zoom_in",   "zoompan=z='min(zoom+0.0015,1.5)':d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"),
    ("zoom_out",  "zoompan=z='if(eq(on,1),1.5,max(1.001,zoom-0.0015))':d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"),
    ("pan_right", "zoompan=z=1.2:d={n}:fps=25:x='(on-1)/d*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)'"),
    ("pan_left",  "zoompan=z=1.2:d={n}:fps=25:x='(iw-iw/zoom)*(1-(on-1)/d)':y='ih/2-(ih/zoom/2)'"),
    ("pan_down",  "zoompan=z=1.2:d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='(on-1)/d*(ih-ih/zoom)'"),
    ("pan_up",    "zoompan=z=1.2:d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-(on-1)/d)'"),
]


class LTXComfyService(BaseService):
    service_name = "ltx_comfy_video"

    # Poll-timeout controls: subclasses can override.
    # timeout = max(_CLIP_TIMEOUT_MIN, frames * _CLIP_TIMEOUT_MULT)
    _CLIP_TIMEOUT_MIN: int = 300   # baseline seconds per clip (5 min — sufficient for RTX 5060 Ti 8-step)
    _CLIP_TIMEOUT_MULT: int = 3    # extra seconds per frame

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        comfyui_url: str = "http://localhost:8188",
        steps: int = _DEFAULT_STEPS,
        width: int = _DEFAULT_WIDTH,
        height: int = _DEFAULT_HEIGHT,
        cfg: float = 3.0,
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.comfyui_url = comfyui_url.rstrip("/")
        self.steps = steps
        self.width = width
        self.height = height
        self.cfg = cfg
        self.clips_dir = self.get_output_dir("clips")
        self.client_id = f"ltx-{project_id[:8]}"

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    async def execute(self) -> Dict[str, Any]:
        return await self.animate_all()

    async def animate_all(self, selected_scene_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """Generate clips for all scenes.

        selected_scene_ids: if provided, only those scenes get LTX-Video AI animation;
        the rest get Ken Burns animated clips (pan/zoom on the static image).
        Pass None to use LTX-Video for all scenes (original behaviour).
        """
        images_dir = self.project_dir / "images"
        image_files = sorted(images_dir.glob("scene_*.png"))

        if not image_files:
            raise ServiceError(self.service_name, "No scene images found — generate images first.")

        ltx_set: Optional[Set[int]] = set(selected_scene_ids) if selected_scene_ids is not None else None
        image_prompts = self._read_prompts()
        scenes_meta = self._load_scenes_json()
        total = len(image_files)
        results: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        if ltx_set is None:
            start_msg = f"Starting LTX-Video animation for {total} scenes"
        else:
            anim_count = sum(1 for img in image_files if int(img.stem.split("_")[1]) not in ltx_set)
            start_msg = f"Starting clip generation: {len(ltx_set)} LTX-Video, {anim_count} animated"
        await self.report_progress(0, start_msg)

        for idx, image_path in enumerate(image_files):
            await self.check_cancelled()

            scene_id = int(image_path.stem.split("_")[1])
            scene_meta = scenes_meta[idx] if idx < len(scenes_meta) else {}

            duration = self._wav_duration(scene_id)
            if duration <= 0:
                duration = float(scene_meta.get("duration") or 0)

            clip_path = self.clips_dir / f"scene_{scene_id:03d}.mp4"
            if clip_path.exists():
                results.append({
                    "scene_id": scene_id,
                    "path": str(clip_path),
                    "filename": clip_path.name,
                    "duration": duration,
                    "resumed": True,
                })
                await self.report_progress(
                    ((idx + 1) / total) * 100,
                    f"Skipped scene {scene_id} (clip exists) · {idx + 1}/{total}",
                    {"scene_id": scene_id, "completed": idx + 1, "total": total, "resumed": True},
                )
                continue

            use_ltx = ltx_set is None or scene_id in ltx_set
            succeeded = False
            try:
                if use_ltx:
                    raw_prompt = image_prompts[idx] if idx < len(image_prompts) else ""
                    prompt = self._build_animation_prompt(raw_prompt, scene_meta)
                    num_frames = self._duration_to_frames(duration)
                    self.logger.info(
                        f"Scene {scene_id}: LTX duration={duration:.2f}s → {num_frames} frames"
                    )
                    result = await self.retry_async(
                        lambda ip=image_path, p=prompt, sid=scene_id, cp=clip_path, nf=num_frames:
                            self.animate_scene(sid, ip, p, cp, nf),
                        max_attempts=2,
                        base_delay=5.0,
                        label=f"scene {scene_id} animation",
                    )
                    result["type"] = "ltx"
                else:
                    # Use exact WAV duration; fall back to scenes.json or 5 s if audio not yet generated.
                    kb_duration = duration if duration > 0 else 5.0
                    self.logger.info(f"Scene {scene_id}: Ken Burns duration={kb_duration:.2f}s")
                    result = await self.generate_ken_burns_clip(
                        scene_id, image_path, clip_path, kb_duration
                    )
                results.append(result)
                succeeded = True
            except Exception as exc:
                self.logger.error(f"Failed to generate clip for scene {scene_id}: {exc}")
                failed.append({"scene_id": scene_id, "error": str(exc)})

            method = "LTX" if use_ltx else "Animated"
            await self.report_progress(
                ((idx + 1) / total) * 100,
                f"{'Done' if succeeded else 'Failed'} [{method}] scene {scene_id} · {idx + 1}/{total}",
                {"scene_id": scene_id, "completed": idx + 1, "total": total},
            )

        manifest = {
            "total": total,
            "animated": len(results),
            "failed": failed,
            "clips": results,
        }
        (self.clips_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        await self.report_progress(100, f"Clip generation complete — {len(results)}/{total} clips")
        return manifest

    async def generate_ken_burns_clip(
        self,
        scene_id: int,
        image_path: Path,
        output_path: Path,
        duration: float,
    ) -> Dict[str, Any]:
        """Generate a Ken Burns (pan/zoom) animated clip from a static image using FFmpeg."""
        style_name, filter_tpl = _KEN_BURNS_STYLES[scene_id % len(_KEN_BURNS_STYLES)]
        # ceil so the zoompan animation fully covers every frame; -t clips the output to the
        # exact WAV duration so the clip never overshoots.
        n_frames = max(1, math.ceil(duration * _OUTPUT_FPS))
        zp_filter = filter_tpl.format(n=n_frames)
        vf = f"{zp_filter},scale={self.width}:{self.height}:flags=lanczos,setsar=1"

        wav_path = self.project_dir / "audio" / f"scene_{scene_id:03d}.wav"
        has_wav = wav_path.exists()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if has_wav:
            # Single-pass: mux WAV alongside the animated video so the clip is self-contained.
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", str(_OUTPUT_FPS), "-i", str(image_path),
                "-i", str(wav_path),
                "-vf", vf,
                "-t", f"{duration:.4f}",
                "-r", str(_OUTPUT_FPS),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(output_path),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", str(_OUTPUT_FPS), "-i", str(image_path),
                "-vf", vf,
                "-t", f"{duration:.4f}",
                "-r", str(_OUTPUT_FPS),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                str(output_path),
            ]

        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise ServiceError(
                self.service_name,
                f"Ken Burns clip failed for scene {scene_id}: {result.stderr[-200:]}",
            )
        self.logger.info(
            f"Ken Burns ({style_name}) clip saved → {output_path}"
            + (" [with WAV]" if has_wav else " [video-only]")
        )
        return {
            "scene_id": scene_id,
            "path": str(output_path),
            "filename": output_path.name,
            "duration_s": round(duration, 2),
            "type": "animated",
            "style": style_name,
        }

    async def animate_scene(
        self,
        scene_id: int,
        image_path: Path,
        prompt: str,
        output_path: Path,
        num_frames: Optional[int] = None,
    ) -> Dict[str, Any]:
        frames = num_frames if num_frames is not None else _DEFAULT_FRAMES
        self.logger.info(
            f"Animating scene {scene_id}: {image_path.name} | "
            f"frames={frames} ({frames / _OUTPUT_FPS:.1f}s) | prompt={prompt[:80]}…"
        )

        image_name = await self._upload_image(image_path)
        seed = random.randint(0, 2**31 - 1)
        workflow = self._build_workflow(
            image_name=image_name,
            prompt=prompt,
            neg_prompt=(
                "worst quality, blurry, jittery, distorted, motion blur, ugly, "
                "text, letters, words, writing, typography, readable text, "
                "captions, subtitles, watermark, characters, glyphs, symbols, "
                "alphabet, numbers, digits, font, script, language"
            ),
            width=self.width,
            height=self.height,
            num_frames=frames,
            seed=seed,
        )
        job_id = await self._submit_workflow(workflow)
        self.logger.info(f"Scene {scene_id} → ComfyUI prompt_id={job_id}")

        timeout = max(self._CLIP_TIMEOUT_MIN, frames * self._CLIP_TIMEOUT_MULT)
        self.logger.info(f"Scene {scene_id}: poll timeout={timeout}s")
        video_url = await self._poll_job(job_id, timeout=timeout)

        await self._download_video(video_url, output_path)
        self.logger.info(f"Clip saved → {output_path}")

        await self._mux_wav_into_clip(output_path, scene_id)

        return {
            "scene_id": scene_id,
            "path": str(output_path),
            "filename": output_path.name,
            "num_frames": frames,
            "duration_s": round(frames / _OUTPUT_FPS, 2),
        }

    async def _mux_wav_into_clip(self, clip_path: Path, scene_id: int) -> bool:
        """Mux the scene WAV into an existing video-only clip file in-place.

        Uses stream-copy for video (no re-encode) so it's fast.
        Falls back silently and keeps the video-only file if WAV is missing or mux fails.
        """
        wav_path = self.project_dir / "audio" / f"scene_{scene_id:03d}.wav"
        if not wav_path.exists():
            self.logger.debug(f"Scene {scene_id}: no WAV yet — clip stays video-only")
            return False

        tmp = clip_path.with_suffix(".mux_tmp.mp4")
        clip_path.rename(tmp)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(tmp),
            "-i", str(wav_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(clip_path),
        ]
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            tmp.unlink(missing_ok=True)
            self.logger.info(f"Scene {scene_id}: WAV synced into clip")
            return True
        else:
            tmp.rename(clip_path)  # Restore video-only clip
            self.logger.warning(
                f"Scene {scene_id}: WAV mux failed, keeping video-only — {result.stderr[-120:]}"
            )
            return False

    # ------------------------------------------------------------------
    # ComfyUI HTTP helpers
    # ------------------------------------------------------------------
    async def _upload_image(self, image_path: Path) -> str:
        """Upload an image to ComfyUI's input dir; return the assigned filename.

        A millisecond timestamp is appended to the stem so every upload gets a
        unique name.  This bypasses ComfyUI's LoadImage node cache, which keys
        on filename and can serve a stale tensor even when the file was
        overwritten on disk.
        """
        ts = int(time.time() * 1000)
        upload_name = f"{image_path.stem}_{ts}{image_path.suffix}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(image_path, "rb") as f:
                r = await client.post(
                    f"{self.comfyui_url}/upload/image",
                    files={"image": (upload_name, f, "image/png")},
                    data={"type": "input"},
                )
            r.raise_for_status()
        result = r.json()
        name = result.get("name", "")
        if not name:
            raise ServiceError(self.service_name, f"ComfyUI image upload returned no filename: {result}")
        return name

    async def _submit_workflow(self, workflow: Dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id},
            )
            r.raise_for_status()
        data = r.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ServiceError(self.service_name, f"ComfyUI /prompt returned no prompt_id: {data}")
        return prompt_id

    async def _cancel_comfyui_job(self, job_id: str) -> None:
        """Ask ComfyUI to cancel a pending/running prompt. Best-effort — never raises."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{self.comfyui_url}/queue",
                    json={"delete": [job_id]},
                )
        except Exception as exc:
            self.logger.warning(f"Could not cancel ComfyUI job {job_id}: {exc}")

    async def _poll_job(self, job_id: str, timeout: int = 900, poll_interval: float = 3.0) -> str:
        """Poll /history/{job_id} until complete; return the video download URL."""
        deadline = time.monotonic() + timeout
        start = time.monotonic()
        heartbeat_interval = 15.0  # emit a progress log every N seconds
        last_heartbeat = start

        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                now = time.monotonic()
                elapsed = now - start

                if now > deadline:
                    await self._cancel_comfyui_job(job_id)
                    raise ServiceError(
                        self.service_name,
                        f"ComfyUI job {job_id} timed out after {timeout}s — cancelled",
                    )

                await self.check_cancelled()

                # Heartbeat: log every 15 s so the LiveLogPanel shows the job is alive
                if now - last_heartbeat >= heartbeat_interval:
                    remaining = max(0, int(deadline - now))
                    self.logger.info(
                        f"ComfyUI job {job_id}: rendering… {elapsed:.0f}s elapsed "
                        f"(timeout in {remaining}s)"
                    )
                    last_heartbeat = now

                r = await client.get(f"{self.comfyui_url}/history/{job_id}")
                r.raise_for_status()
                history = r.json()

                job = history.get(job_id)
                if not job:
                    await asyncio.sleep(poll_interval)
                    continue

                status_obj = job.get("status", {})
                if status_obj.get("status_str") == "error":
                    msgs = status_obj.get("messages", [])
                    detail = msgs[-1] if msgs else "unknown error"
                    raise ServiceError(self.service_name, f"ComfyUI job {job_id} failed: {detail}")

                if not status_obj.get("completed", False):
                    await asyncio.sleep(poll_interval)
                    continue

                # VHS_VideoCombine stores .mp4 under "gifs" key (even for mp4)
                outputs = job.get("outputs", {})
                for node_out in outputs.values():
                    for item in node_out.get("gifs", []):
                        fn = item.get("filename", "")
                        sub = item.get("subfolder", "")
                        if fn:
                            return f"{self.comfyui_url}/view?filename={fn}&subfolder={sub}&type=output"
                    for item in node_out.get("videos", []):
                        fn = item.get("filename", "")
                        sub = item.get("subfolder", "")
                        if fn:
                            return f"{self.comfyui_url}/view?filename={fn}&subfolder={sub}&type=output"

                raise ServiceError(
                    self.service_name,
                    f"ComfyUI job {job_id} completed but no video output found. Outputs: {outputs}",
                )

    async def _download_video(self, url: str, dest_path: Path) -> None:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

    # ------------------------------------------------------------------
    # Workflow builder
    # ------------------------------------------------------------------
    def _build_workflow(
        self,
        image_name: str,
        prompt: str,
        neg_prompt: str,
        width: int,
        height: int,
        num_frames: int,
        seed: int,
    ) -> Dict[str, Any]:
        return {
            # LTX-Video combined checkpoint: MODEL at [0], VAE at [2]
            # (the distilled .safetensors bundles transformer + video VAE together)
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": _CHECKPOINT},
            },
            # T5 text encoder — loaded separately, type "ltxv" required for LTX-Video
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": _CLIP, "type": "ltxv"},
            },
            # Positive conditioning
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["2", 0]},
            },
            # Negative conditioning
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": neg_prompt, "clip": ["2", 0]},
            },
            # Load uploaded scene image (scaled to width×height by LTXVImgToVideo)
            "6": {
                "class_type": "LoadImage",
                "inputs": {"image": image_name},
            },
            # I2V latent conditioning — outputs: (positive, negative, latent)
            # VAE comes from checkpoint slot 2 (the bundled LTX-Video causal video VAE)
            "7": {
                "class_type": "LTXVImgToVideo",
                "inputs": {
                    "positive": ["4", 0],
                    "negative": ["5", 0],
                    "vae": ["1", 2],
                    "image": ["6", 0],
                    "width": width,
                    "height": height,
                    "length": num_frames,
                    "batch_size": 1,
                    "strength": 1.0,
                },
            },
            # Inject frame rate into conditioning
            "8": {
                "class_type": "LTXVConditioning",
                "inputs": {
                    "positive": ["7", 0],
                    "negative": ["7", 1],
                    "frame_rate": float(_OUTPUT_FPS),
                },
            },
            # LTX-specific sigma scaling applied to the model
            "9": {
                "class_type": "ModelSamplingLTXV",
                "inputs": {
                    "model": ["1", 0],
                    "max_shift": 2.05,
                    "base_shift": 0.95,
                    "latent": ["7", 2],
                },
            },
            # Distilled-model-compatible sigma schedule
            "10": {
                "class_type": "LTXVScheduler",
                "inputs": {
                    "steps": self.steps,
                    "max_shift": 2.05,
                    "base_shift": 0.95,
                    "stretch": True,
                    "terminal": 0.1,
                    "latent": ["7", 2],
                },
            },
            # Euler sampler
            "11": {
                "class_type": "KSamplerSelect",
                "inputs": {"sampler_name": "euler"},
            },
            # Noise source
            "12": {
                "class_type": "RandomNoise",
                "inputs": {"noise_seed": seed},
            },
            # CFG guidance
            "13": {
                "class_type": "CFGGuider",
                "inputs": {
                    "model": ["9", 0],
                    "positive": ["8", 0],
                    "negative": ["8", 1],
                    "cfg": self.cfg,
                },
            },
            # Advanced sampler (required for LTXVScheduler sigmas)
            "14": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["12", 0],
                    "guider": ["13", 0],
                    "sampler": ["11", 0],
                    "sigmas": ["10", 0],
                    "latent_image": ["7", 2],
                },
            },
            # Decode video latent → frame batch (same VAE from checkpoint)
            "15": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["14", 0],
                    "vae": ["1", 2],
                },
            },
            # Combine frames into .mp4 (VHS_VideoCombine from comfyui-videohelpersuite)
            "16": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["15", 0],
                    "frame_rate": _OUTPUT_FPS,
                    "loop_count": 0,
                    "filename_prefix": "ltx_scene",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True,
                },
            },
        }

    # ------------------------------------------------------------------
    # Utilities (shared logic from wan2_service)
    # ------------------------------------------------------------------
    def _wav_duration(self, scene_id: int) -> float:
        """Return the actual duration of the generated voice WAV for this scene, or 0.0 if missing."""
        wav_path = self.project_dir / "audio" / f"scene_{scene_id:03d}.wav"
        if not wav_path.exists():
            return 0.0
        try:
            with wave.open(str(wav_path), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception as exc:
            self.logger.warning(f"Could not read WAV duration for scene {scene_id}: {exc}")
            return 0.0

    def _duration_to_frames(self, duration: float) -> int:
        if duration <= 0:
            return _DEFAULT_FRAMES
        raw = duration * _OUTPUT_FPS
        k = max(0, math.ceil((raw - _MIN_FRAMES) / _FRAMES_STEP))
        frames = _MIN_FRAMES + k * _FRAMES_STEP
        return max(_MIN_FRAMES, min(_MAX_FRAMES, frames))

    _SD_NOISE_TAGS = frozenset({
        "masterpiece", "best quality", "high quality", "ultra quality",
        "ultra detailed", "highly detailed", "extremely detailed",
        "8k", "4k", "hd", "uhd", "hdr", "raw photo", "sharp focus",
        "photorealistic", "hyperrealistic", "realistic", "photo realistic",
        "professional photography", "professional photo", "award winning",
        "cinematic lighting", "dramatic lighting", "studio lighting",
        "depth of field", "bokeh", "dof",
        "intricate", "detailed", "high resolution", "high detail",
        "octane render", "unreal engine", "ray tracing",
    })

    # Single-word tags that cause LTX-Video to render garbled pseudo-text
    _TEXT_INDUCING_TAGS = frozenset({
        "code", "coding", "programming", "script", "terminal", "console",
        "ide", "vscode", "editor", "compiler", "debugging", "syntax",
        "letters", "words", "typography", "captions", "subtitle",
        "readable", "font", "glyph", "alphabet", "watermark", "caption",
    })

    # Multi-word phrase replacements: swap text-heavy descriptions for
    # abstract visual equivalents that LTX-Video can render without glyphs.
    _TEXT_PHRASE_REPLACEMENTS = [
        ("code editor",               "dark screen with glowing colored patterns"),
        ("source code",               "abstract data streams on dark background"),
        ("command line",              "dark screen with glowing abstract patterns"),
        ("syntax highlighting",       "colorful abstract light patterns"),
        ("text on screen",            "abstract glowing interface"),
        ("screen with text",          "dark atmospheric digital display"),
        ("monitor with text",         "dark glowing digital interface"),
        ("laptop screen",             "dark digital interface with ambient glow"),
        ("screen with code",          "dark screen with glowing abstract lines"),
        ("programming language",      "abstract digital visualization"),
        ("computer screen",           "dark glowing digital display"),
        ("lines of code",             "streams of glowing abstract light"),
        ("written text",              "abstract glowing symbols"),
        ("readable text",             "abstract glowing patterns"),
    ]

    def _sanitize_text_triggers(self, text: str) -> str:
        """Replace phrases that cause LTX-Video to hallucinate garbled text glyphs."""
        import re
        for phrase, replacement in self._TEXT_PHRASE_REPLACEMENTS:
            text = re.sub(re.escape(phrase), replacement, text, flags=re.IGNORECASE)
        return text

    def _build_animation_prompt(self, image_prompt: str, scene_meta: Dict) -> str:
        parts: List[str] = []
        visual_desc = (scene_meta.get("visual_description") or "").strip()
        title = (scene_meta.get("title") or "").strip()
        if visual_desc:
            parts.append(self._sanitize_text_triggers(visual_desc)[:200])
        elif title:
            parts.append(title)
        if image_prompt:
            meaningful = [
                tag.strip()
                for tag in image_prompt.split(",")
                if tag.strip()
                and tag.strip().lower() not in self._SD_NOISE_TAGS
                and tag.strip().lower() not in self._TEXT_INDUCING_TAGS
            ]
            if meaningful:
                parts.append(", ".join(meaningful[:8]))
        parts.append("smooth cinematic motion, gentle camera movement, high quality video")
        return ", ".join(filter(None, parts))

    def _load_scenes_json(self) -> List[Dict]:
        p = self.project_dir / "input" / "scenes.json"
        if not p.exists():
            return []
        try:
            _d = json.loads(p.read_text(encoding="utf-8"))
            return _d if isinstance(_d, list) else _d.get("scenes", [])
        except Exception as exc:
            self.logger.warning(f"Could not read scenes.json: {exc}")
            return []

    def _read_prompts(self) -> List[str]:
        f = self.project_dir / "input" / "image_prompts.txt"
        if not f.exists():
            return []
        content = f.read_text(encoding="utf-8")
        prompts = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("PROMPT:"):
                p = stripped[7:].strip()
                if p:
                    prompts.append(p)
        if not prompts:
            prompts = [ln.strip() for ln in content.splitlines() if ln.strip()]
        return prompts


# ---------------------------------------------------------------------------
# AI News per-section LTX animation
# ---------------------------------------------------------------------------

class AiNewsLTXService(LTXComfyService):
    """Generates per-scene LTX video clips for all sections of an AI News project.

    Input images:   images/sections/{label}/scene_NNN.png
    Audio (timing): audio/sections/{label}/scene_NNN.wav  (for clip duration)
    Per-section metadata: input/sections/{label}/scenes.json
                          input/sections/{label}/image_prompts.txt
    Output clips:   clips/sections/{label}/scene_NNN.mp4  (video-only)

    Clips are video-only — narration is added later by AiNewsClipService /
    AiNewsShortsService / _build_ai_news_video().
    """

    service_name = "ai_news_ltx"

    # Tighter timeouts: 768×512 distilled (8 steps) on RTX 5060 Ti ≤ 5 min
    _CLIP_TIMEOUT_MIN: int = 300   # 5 min minimum (covers cold model-load)
    _CLIP_TIMEOUT_MULT: int = 2    # 2 s/frame for the smaller 768×512 resolution

    @staticmethod
    def _section_sort_key(label: str) -> tuple:
        if label == "intro":
            return (0, 0)
        if label == "outro":
            return (2, 0)
        if label.startswith("story_"):
            try:
                return (1, int(label.split("_", 1)[1]))
            except (IndexError, ValueError):
                pass
        return (1, 999)

    def _section_wav_duration(self, label: str, scene_id: int) -> float:
        wav = self.project_dir / "audio" / "sections" / label / f"scene_{scene_id:03d}.wav"
        if not wav.exists():
            return 0.0
        try:
            with wave.open(str(wav), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.0

    def _load_section_meta(self, label: str) -> List[Dict]:
        p = self.project_dir / "input" / "sections" / label / "scenes.json"
        if not p.exists():
            return []
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else d.get("scenes", [])
        except Exception:
            return []

    def _read_section_prompts(self, label: str) -> List[str]:
        f = self.project_dir / "input" / "sections" / label / "image_prompts.txt"
        if not f.exists():
            return []
        content = f.read_text(encoding="utf-8")
        prompts = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("PROMPT:"):
                p = stripped[7:].strip()
                if p:
                    prompts.append(p)
        if not prompts:
            prompts = [ln.strip() for ln in content.splitlines() if ln.strip()]
        return prompts

    async def generate_section(self, label: str) -> Dict[str, Any]:
        """Animate all scene images in one section label → clips/sections/{label}/.

        Skips scenes that already have a clip (resume-safe).
        """
        images_dir = self.project_dir / "images" / "sections" / label
        if not images_dir.exists():
            raise ServiceError(self.service_name, f"No images directory for section '{label}'")

        image_files = sorted(images_dir.glob("scene_*.png"))
        if not image_files:
            raise ServiceError(self.service_name, f"No scene images for section '{label}'")

        out_dir = self.project_dir / "clips" / "sections" / label
        out_dir.mkdir(parents=True, exist_ok=True)

        image_prompts = self._read_section_prompts(label)
        scenes_meta   = self._load_section_meta(label)
        total         = len(image_files)
        results: List[Dict[str, Any]] = []
        failed:  List[Dict[str, Any]] = []

        await self.report_progress(0, f"Section '{label}': starting {total} scene clips")

        for idx, image_path in enumerate(image_files):
            await self.check_cancelled()

            scene_id  = int(image_path.stem.split("_")[1])
            scene_meta = scenes_meta[idx] if idx < len(scenes_meta) else {}

            duration = self._section_wav_duration(label, scene_id)
            if duration <= 0:
                duration = float(scene_meta.get("duration") or 5.0)
            if duration <= 0:
                duration = 5.0

            clip_path = out_dir / f"scene_{scene_id:03d}.mp4"
            if clip_path.exists():
                results.append({
                    "scene_id": scene_id, "path": str(clip_path),
                    "filename": clip_path.name, "duration": duration, "resumed": True,
                })
                await self.report_progress(
                    int(((idx + 1) / total) * 100),
                    f"Section '{label}': scene {scene_id} already exists ({idx+1}/{total})",
                    {"section": label, "scene_id": scene_id, "completed": idx + 1, "total": total},
                )
                continue

            succeeded = False
            try:
                raw_prompt = image_prompts[idx] if idx < len(image_prompts) else ""
                prompt     = self._build_animation_prompt(raw_prompt, scene_meta)
                num_frames = self._duration_to_frames(duration)
                self.logger.info(
                    f"Section '{label}' scene {scene_id}: {duration:.2f}s → {num_frames} frames"
                )
                result = await self.retry_async(
                    lambda ip=image_path, p=prompt, sid=scene_id, cp=clip_path, nf=num_frames:
                        self.animate_scene(sid, ip, p, cp, nf),
                    max_attempts=1,  # fail fast — surface ComfyUI errors immediately
                    base_delay=5.0,
                    label=f"section '{label}' scene {scene_id}",
                )
                result["type"] = "ltx"
                results.append(result)
                succeeded = True
            except Exception as exc:
                self.logger.error(f"Section '{label}' scene {scene_id} failed: {exc}")
                failed.append({"scene_id": scene_id, "error": str(exc)})

            await self.report_progress(
                int(((idx + 1) / total) * 100),
                f"Section '{label}': {'done' if succeeded else 'failed'} scene {scene_id} ({idx+1}/{total})",
                {"section": label, "scene_id": scene_id, "completed": idx + 1, "total": total},
            )

        await self.report_progress(100, f"Section '{label}': {len(results)}/{total} clips done")
        return {"label": label, "total": total, "animated": len(results), "failed": failed}

    async def generate_all_sections(self) -> Dict[str, Any]:
        """Animate all sections in narrative order."""
        sections_root = self.project_dir / "images" / "sections"
        if not sections_root.exists():
            raise ServiceError(self.service_name, "No images/sections directory found")

        section_dirs = sorted(
            [d for d in sections_root.iterdir() if d.is_dir()],
            key=lambda d: self._section_sort_key(d.name),
        )
        if not section_dirs:
            raise ServiceError(self.service_name, "No section image directories found")

        total_sections = len(section_dirs)
        all_results: Dict[str, Any] = {}

        for i, sec_dir in enumerate(section_dirs):
            label = sec_dir.name
            await self.report_progress(
                int((i / total_sections) * 100),
                f"Processing section '{label}' ({i+1}/{total_sections})",
            )
            try:
                result = await self.generate_section(label)
                all_results[label] = result
            except Exception as exc:
                self.logger.error(f"Section '{label}' failed: {exc}")
                all_results[label] = {"label": label, "error": str(exc)}

        await self.report_progress(100, f"All {total_sections} sections processed")
        return {"sections": all_results, "total_sections": total_sections}
