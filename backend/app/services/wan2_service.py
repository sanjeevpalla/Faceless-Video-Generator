"""
Wan2VideoService — animates FLUX scene images using Wan2GP's MCP HTTP API.

Wan2GP MUST be started in MCP mode (not Gradio mode) for this to work:

  cd D:\\LLMs\\Wan2GP
  python wgp.py --mcp --mcp-transport streamable-http --mcp-host 0.0.0.0 --mcp-port 8889

Default model: ltx2_19B (LTX-Video 2) — generates clips in seconds.
Wan2GP auto-downloads the model on first use (~4 GB).

Alternative fast model (1-3 min/clip instead of seconds):
  python wgp.py --i2v-1-3B --mcp --mcp-transport streamable-http --mcp-host 0.0.0.0 --mcp-port 8889
  Set model_type="fun_inp_1.3B"

Pipeline per scene:
  1. MCP: wangp_generate(source, wait=False) → job_id
  2. Poll: wangp_get_job(job_id)             → status / generated_files
  3. Copy: artifacts[0].path               → clips/scene_XXX.mp4
"""
import asyncio
import json
import math
import shutil
import subprocess
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

from app.core.exceptions import ServiceError
from app.services.base import BaseService


class Wan2VideoService(BaseService):
    service_name = "wan2_video"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        wan2gp_url: str = "http://localhost:8889",
        model_type: str = "fun_inp_1.3B",  # Wan2.1 Fun-InP 1.3B — fits in 16GB VRAM, no device mismatch
        default_num_frames: int = 129,     # fallback: 8s @ 16fps (scene duration used when available)
        steps: int = 20,                   # 20 steps: good quality for fun_inp, ~1-2 min/clip
        resolution: str = "832x480",
        guidance_scale: float = 3.5,
        seed: int = -1,
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.mcp_base = wan2gp_url.rstrip("/")
        self.model_type = model_type
        self.default_num_frames = default_num_frames
        self.steps = steps
        self.resolution = resolution
        self.guidance_scale = guidance_scale
        self.seed = seed
        self.clips_dir = self.get_output_dir("clips")
        self._mcp_session_id: Optional[str] = None

        # Frame constraints and FPS vary by model family
        if model_type.startswith("ltx2"):
            self.OUTPUT_FPS = 24
            self.MIN_FRAMES = 17
            self.MAX_FRAMES = 257
            self._frames_step = 8
            self._frames_offset = 17
        elif model_type.startswith("ltxv"):
            self.OUTPUT_FPS = 24
            self.MIN_FRAMES = 9
            self.MAX_FRAMES = 257
            self._frames_step = 8
            self._frames_offset = 1
        else:
            # Wan2.1 family (i2v, i2v_nvfp4, fun_inp_1.3B, etc.)
            self.OUTPUT_FPS = 16
            self.MIN_FRAMES = 9
            self.MAX_FRAMES = 225
            self._frames_step = 4
            self._frames_offset = 1

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    async def execute(self) -> Dict[str, Any]:
        return await self.animate_all()

    async def animate_all(
        self,
        selected_scene_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Generate clips for all scenes via Wan2GP I2V.

        selected_scene_ids: if provided, only those scenes get Wan2GP animation;
        the rest get Ken Burns animated clips (pan/zoom on the static image).
        Pass None to animate every scene with Wan2GP.
        """
        images_dir = self.project_dir / "images"
        image_files = sorted(images_dir.glob("scene_*.png"))

        if not image_files:
            raise ServiceError(self.service_name, "No scene images found — generate images first.")

        ltx_set: Optional[Set[int]] = set(selected_scene_ids) if selected_scene_ids is not None else None

        # Only establish MCP session if we'll actually send anything to Wan2GP
        if ltx_set is None or ltx_set:
            await self._ensure_mcp_session()

        image_prompts = self._read_prompts()
        scenes_meta = self._load_scenes_json()
        total = len(image_files)
        results: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        await self.report_progress(0, f"Starting Wan2GP animation for {total} scenes")

        for idx, image_path in enumerate(image_files):
            await self.check_cancelled()

            scene_id = int(image_path.stem.split("_")[1])
            raw_prompt = image_prompts[idx] if idx < len(image_prompts) else ""
            scene_meta = scenes_meta[idx] if idx < len(scenes_meta) else {}

            # WAV duration takes priority over scenes.json metadata
            duration = self._wav_duration(scene_id)
            if duration <= 0:
                duration = float(scene_meta.get("duration") or 0)

            num_frames = self._duration_to_frames(duration)
            self.logger.info(
                f"Scene {scene_id}: duration={duration:.2f}s → {num_frames} frames "
                f"({num_frames / self.OUTPUT_FPS:.2f}s at {self.OUTPUT_FPS} fps)"
            )

            clip_path = self.clips_dir / f"scene_{scene_id:03d}.mp4"
            if clip_path.exists():
                results.append({
                    "scene_id": scene_id,
                    "path": str(clip_path),
                    "filename": clip_path.name,
                    "duration": duration,
                    "num_frames": num_frames,
                    "resumed": True,
                })
                await self.report_progress(
                    ((idx + 1) / total) * 100,
                    f"Skipped scene {scene_id} (clip exists) · {idx + 1}/{total}",
                    {"scene_id": scene_id, "completed": idx + 1, "total": total, "resumed": True},
                )
                continue

            use_wan2 = ltx_set is None or scene_id in ltx_set
            succeeded = False
            try:
                if use_wan2:
                    prompt = self._build_animation_prompt(raw_prompt, scene_meta)
                    result = await self.retry_async(
                        lambda ip=image_path, p=prompt, sid=scene_id, cp=clip_path, nf=num_frames:
                            self.animate_scene(sid, ip, p, cp, nf),
                        max_attempts=2,
                        base_delay=5.0,
                        label=f"scene {scene_id} animation",
                    )
                    result["type"] = "wan2"
                else:
                    kb_duration = duration if duration > 0 else 5.0
                    self.logger.info(f"Scene {scene_id}: Ken Burns duration={kb_duration:.2f}s")
                    result = await self.generate_ken_burns_clip(
                        scene_id, image_path, clip_path, kb_duration
                    )
                results.append(result)
                succeeded = True
            except Exception as exc:
                self.logger.error(f"Failed to animate scene {scene_id}: {exc}")
                failed.append({"scene_id": scene_id, "error": str(exc)})

            method = "Wan2GP" if use_wan2 else "Animated"
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

        await self.report_progress(100, f"Animation complete — {len(results)}/{total} clips")
        return manifest

    _KEN_BURNS_FPS = 25
    _KEN_BURNS_STYLES = [
        ("zoom_in",   "zoompan=z='min(zoom+0.0015,1.5)':d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"),
        ("zoom_out",  "zoompan=z='if(eq(on,1),1.5,max(1.001,zoom-0.0015))':d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"),
        ("pan_right", "zoompan=z=1.2:d={n}:fps=25:x='(on-1)/d*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)'"),
        ("pan_left",  "zoompan=z=1.2:d={n}:fps=25:x='(iw-iw/zoom)*(1-(on-1)/d)':y='ih/2-(ih/zoom/2)'"),
        ("pan_down",  "zoompan=z=1.2:d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='(on-1)/d*(ih-ih/zoom)'"),
        ("pan_up",    "zoompan=z=1.2:d={n}:fps=25:x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-(on-1)/d)'"),
    ]

    def _wav_duration(self, scene_id: int) -> float:
        """Return WAV duration for the scene's voice file, or 0.0 if missing."""
        wav_path = self.project_dir / "audio" / f"scene_{scene_id:03d}.wav"
        if not wav_path.exists():
            return 0.0
        try:
            with wave.open(str(wav_path), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.0

    async def generate_ken_burns_clip(
        self,
        scene_id: int,
        image_path: Path,
        output_path: Path,
        duration: float,
    ) -> Dict[str, Any]:
        """Ken Burns (pan/zoom) animated clip via FFmpeg — fallback when Wan2GP isn't used."""
        fps = self._KEN_BURNS_FPS
        style_name, filter_tpl = self._KEN_BURNS_STYLES[scene_id % len(self._KEN_BURNS_STYLES)]
        n_frames = max(1, math.ceil(duration * fps))
        zp_filter = filter_tpl.format(n=n_frames)
        # Use resolution from self.resolution string (e.g. "832x480")
        try:
            w_str, h_str = self.resolution.split("x")
            res_filter = f"scale={w_str}:{h_str}:flags=lanczos,setsar=1"
        except Exception:
            res_filter = "setsar=1"
        vf = f"{zp_filter},{res_filter}"

        wav_path = self.project_dir / "audio" / f"scene_{scene_id:03d}.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if wav_path.exists():
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", str(fps), "-i", str(image_path),
                "-i", str(wav_path),
                "-vf", vf, "-t", f"{duration:.4f}", "-r", str(fps),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest",
                str(output_path),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", str(fps), "-i", str(image_path),
                "-vf", vf, "-t", f"{duration:.4f}", "-r", str(fps),
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
        self.logger.info(f"Ken Burns ({style_name}) clip saved → {output_path}")
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
        frames = num_frames if num_frames is not None else self.default_num_frames
        self.logger.info(
            f"Animating scene {scene_id}: {image_path.name} | "
            f"frames={frames} ({frames / self.OUTPUT_FPS:.1f}s) | prompt={prompt[:80]}…"
        )

        source: Dict[str, Any] = {
            "model_type": self.model_type,
            "prompt": prompt,
            "image_start": str(image_path.resolve()),
            "video_length": frames,
            "num_inference_steps": self.steps,
            "resolution": self.resolution,
        }
        # Wan2.1-specific params — not understood by LTX-2/LTX-Video
        if not self.model_type.startswith("ltx"):
            source["flow_shift"] = 7.0
            source["sample_solver"] = "unipc"
            source["image_prompt_type"] = "S"
        if self.seed >= 0:
            source["seed"] = self.seed

        job_id = await self._submit_generate(source)
        # 2-hour minimum covers first-run LTX-2 model download; after that generation is seconds
        poll_timeout = max(7200, frames * 30)
        generated_path = await self._poll_job(job_id, timeout=poll_timeout)

        shutil.copy2(generated_path, output_path)
        self.logger.info(f"Clip saved → {output_path}")

        return {
            "scene_id": scene_id,
            "path": str(output_path),
            "filename": output_path.name,
            "num_frames": frames,
            "duration_s": round(frames / self.OUTPUT_FPS, 2),
        }

    # ------------------------------------------------------------------
    # MCP HTTP client
    # ------------------------------------------------------------------
    async def _mcp_post(self, payload: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """POST to /mcp and parse the SSE response.

        Wan2GP's MCP server responds with Content-Type: text/event-stream even for
        single request-response calls, so we must use streaming to avoid blocking
        forever waiting for the stream to close.

        Returns the parsed JSON-RPC body dict (may be empty for notifications).
        """
        req_headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._mcp_session_id:
            req_headers["Mcp-Session-Id"] = self._mcp_session_id

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.mcp_base}/mcp/",
                json=payload, headers=req_headers,
            ) as r:
                resp_headers = dict(r.headers)
                if r.status_code not in (200, 202):
                    err = await r.aread()
                    raise ServiceError(
                        self.service_name,
                        f"MCP {payload.get('method', '?')} failed ({r.status_code}): {err.decode()[:300]}",
                    )

                # Read SSE lines; skip server-push notifications, return the
                # JSON-RPC response that matches our request id (has "result" or "error").
                req_id = payload.get("id")
                body: Dict[str, Any] = {}
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        candidate = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    # Notifications have "method" but no "id"; skip them.
                    if "result" in candidate or "error" in candidate:
                        if req_id is None or candidate.get("id") == req_id:
                            body = candidate
                            break
                    # Keep reading for the real response

        # Cache session ID if returned
        sid = resp_headers.get("mcp-session-id")
        if sid and not self._mcp_session_id:
            self._mcp_session_id = sid

        return body

    async def _ensure_mcp_session(self) -> None:
        """One-time MCP initialize handshake; caches session ID."""
        if self._mcp_session_id:
            return
        body = await self._mcp_post({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "wan2service", "version": "1.0"},
            },
            "id": 1,
        }, timeout=15.0)
        if not self._mcp_session_id:
            self._mcp_session_id = str(uuid.uuid4())
        if "error" in body:
            raise ServiceError(self.service_name, f"MCP initialize error: {body['error']}")

        # Notify server that client is ready (fire-and-forget, 202 expected)
        try:
            await self._mcp_post({"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=5.0)
        except Exception:
            pass  # notification response is optional

    async def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Call an MCP tool and return the parsed result content."""
        if not self._mcp_session_id:
            await self._ensure_mcp_session()

        body = await self._mcp_post({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
            "id": str(uuid.uuid4())[:8],
        })
        if "error" in body:
            raise ServiceError(self.service_name, f"MCP error from '{name}': {body['error']}")

        result = body.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "") if isinstance(content[0], dict) else str(content[0])
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return result

    async def _submit_generate(self, source: Dict[str, Any]) -> str:
        """Call wangp_generate (wait=False) and return the job_id.

        Wan2GP processes one job at a time. If a previous job (e.g. from a prior
        run, or still downloading the model) is in progress, we wait with exponential
        backoff until a slot is free.
        """
        backoff = 30.0
        max_wait = 7200.0  # 2 hours — covers initial LTX-2 model download
        waited = 0.0

        while True:
            result = await self._call_tool("wangp_generate", {"source": source, "wait": False, "event_limit": 3})
            if isinstance(result, dict):
                job_id = result.get("job_id") or result.get("id")
                if job_id:
                    self.logger.info(f"Wan2GP job submitted: {job_id}")
                    return job_id

            result_str = str(result)
            if "in progress" in result_str.lower() or "already" in result_str.lower():
                if waited >= max_wait:
                    raise ServiceError(self.service_name, f"Wan2GP remained busy for {max_wait / 3600:.1f}h, giving up")
                self.logger.info(f"Wan2GP busy with another job — waiting {backoff:.0f}s (total waited: {waited:.0f}s)")
                await asyncio.sleep(backoff)
                waited += backoff
                backoff = min(backoff * 2, 300.0)  # cap at 5-min intervals
                continue

            raise ServiceError(self.service_name, f"wangp_generate returned no job id: {result!r}")

    async def _poll_job(self, job_id: str, timeout: int = 300) -> str:
        """Poll wangp_get_job until status=completed; return the generated file path."""
        deadline = time.monotonic() + timeout
        poll_interval = 5.0

        while True:
            if time.monotonic() > deadline:
                raise ServiceError(
                    self.service_name,
                    f"Wan2GP job {job_id} timed out after {timeout}s",
                )
            await self.check_cancelled()

            snapshot = await self._call_tool("wangp_get_job", {"job_id": job_id, "event_limit": 5})

            if not isinstance(snapshot, dict):
                self.logger.debug(f"Job {job_id}: unexpected poll response: {snapshot!r}")
                await asyncio.sleep(poll_interval)
                continue

            done = snapshot.get("done", False)
            self.logger.debug(f"Job {job_id} done={done}")

            if done:
                gen_result = snapshot.get("result") or {}
                if not gen_result.get("success", True) and gen_result.get("errors"):
                    errors = gen_result.get("errors", [])
                    msg = errors[0].get("message") if errors else "unknown error"
                    raise ServiceError(self.service_name, f"Wan2GP job {job_id} failed: {msg}")
                artifacts = gen_result.get("artifacts", [])
                generated = gen_result.get("generated_files", [])
                path = None
                if artifacts:
                    path = artifacts[0].get("path")
                if not path and generated:
                    path = generated[0]
                if not path:
                    raise ServiceError(self.service_name, f"Job {job_id} completed but no output file found")
                return path

            await asyncio.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                async with client.stream(
                    "POST", f"{self.mcp_base}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "healthcheck", "version": "1.0"},
                        },
                        "id": "hc",
                    },
                    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                ) as r:
                    return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def _duration_to_frames(self, duration: float) -> int:
        if duration <= 0:
            return self.default_num_frames
        raw = round(duration * self.OUTPUT_FPS)
        k = max(0, round((raw - self._frames_offset) / self._frames_step))
        frames = self._frames_offset + k * self._frames_step
        return max(self.MIN_FRAMES, min(self.MAX_FRAMES, frames))

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

    def _build_animation_prompt(self, image_prompt: str, scene_meta: Dict) -> str:
        parts: List[str] = []
        visual_desc = (scene_meta.get("visual_description") or "").strip()
        title = (scene_meta.get("title") or "").strip()
        if visual_desc:
            parts.append(visual_desc[:200])
        elif title:
            parts.append(title)
        if image_prompt:
            meaningful = [
                tag.strip()
                for tag in image_prompt.split(",")
                if tag.strip() and tag.strip().lower() not in self._SD_NOISE_TAGS
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
# AI News per-section animation via Wan2GP I2V (same quality as Deep Dive)
# ---------------------------------------------------------------------------

class AiNewsWan2Service(Wan2VideoService):
    """Wan2GP I2V animation for AI News sections.

    Reads:  images/sections/{label}/scene_NNN.png
            audio/sections/{label}/scene_NNN.wav   (clip duration)
            input/sections/{label}/scenes.json
            input/sections/{label}/image_prompts.txt
    Writes: clips/sections/{label}/scene_NNN.mp4
    """

    service_name = "ai_news_wan2"

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
        import wave as _wave
        wav = self.project_dir / "audio" / "sections" / label / f"scene_{scene_id:03d}.wav"
        if not wav.exists():
            return 0.0
        try:
            with _wave.open(str(wav), "rb") as w:
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
        """Animate all scene images in sections/{label} using Wan2GP I2V.

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

        await self._ensure_mcp_session()

        image_prompts = self._read_section_prompts(label)
        scenes_meta   = self._load_section_meta(label)
        total         = len(image_files)
        results: List[Dict[str, Any]] = []
        failed:  List[Dict[str, Any]] = []

        await self.report_progress(0, f"Section '{label}': starting {total} scene clips")

        for idx, image_path in enumerate(image_files):
            await self.check_cancelled()

            scene_id   = int(image_path.stem.split("_")[1])
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
                    max_attempts=1,
                    base_delay=5.0,
                    label=f"section '{label}' scene {scene_id}",
                )
                result["type"] = "wan2"
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
        """Animate all sections in narrative order (intro → story_01…→ outro)."""
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
