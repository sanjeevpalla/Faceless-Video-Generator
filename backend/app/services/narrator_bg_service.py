"""
NarratorBgRemoveService — AI background removal for narrator clips.

Uses rembg (u2netp ONNX model) to segment the person frame-by-frame,
then pipes RGBA frames through FFmpeg to produce a *_nobg.webm file
with VP9 alpha channel. The processed clip is used automatically by
VideoGenerationService for overlay compositing.
"""
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional

import cv2
import numpy as np


class NarratorBgRemoveService:
    def __init__(self, progress_callback: Optional[Callable] = None) -> None:
        self.progress_callback = progress_callback

    async def process_clips(self, clips: List[Path]) -> List[Dict]:
        """Remove background from every clip. Returns per-clip result dicts."""
        import asyncio

        results: List[Dict] = []
        loop = asyncio.get_event_loop()

        for idx, clip in enumerate(clips):
            out_path = clip.parent / f"{clip.stem}_nobg.webm"

            if self.progress_callback:
                pct = idx / len(clips) * 95
                await self.progress_callback(
                    pct,
                    f"Removing background: {clip.name} ({idx + 1}/{len(clips)})…",
                    {},
                )

            try:
                await loop.run_in_executor(None, self._process_clip, clip, out_path)
                results.append({"filename": clip.name, "output": out_path.name, "status": "ok"})
            except Exception as exc:
                results.append({"filename": clip.name, "output": None, "status": "error", "error": str(exc)})

        if self.progress_callback:
            await self.progress_callback(100, "Background removal complete", {})

        return results

    # ------------------------------------------------------------------
    def _process_clip(self, clip: Path, out_path: Path) -> None:
        """Process one clip: read frames → rembg → pipe to WebM+alpha."""
        from rembg import new_session, remove
        from PIL import Image

        cap = cv2.VideoCapture(str(clip))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {clip}")

        fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # VP9 WebM with alpha channel — one-time processed output
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "rgba",
            "-r", str(fps),
            "-i", "pipe:0",
            "-c:v", "libvpx-vp9",
            "-auto-alt-ref", "0",   # required for alpha in VP9
            "-pix_fmt", "yuva420p",
            "-b:v", "0", "-crf", "18",
            str(out_path),
        ]
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        session = new_session("u2netp")
        try:
            while True:
                ret, bgr = cap.read()
                if not ret:
                    break

                pil_rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                rgba_pil = remove(pil_rgb, session=session)           # RGBA PIL image
                rgba_np  = np.array(rgba_pil, dtype=np.uint8)         # H×W×4

                # Gentle alpha feathering to soften hard edges
                alpha = rgba_np[:, :, 3].astype(np.float32)
                alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
                rgba_np[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)

                proc.stdin.write(rgba_np.tobytes())

            proc.stdin.close()
            _, stderr_data = proc.communicate(timeout=600)

        except Exception as exc:
            proc.kill()
            cap.release()
            raise RuntimeError(f"FFmpeg pipe failed: {exc}") from exc

        cap.release()

        if proc.returncode != 0:
            err = stderr_data.decode("utf-8", errors="replace")[-400:] if stderr_data else ""
            raise RuntimeError(f"WebM encode failed: {err}")

    # ------------------------------------------------------------------
    @staticmethod
    def nobg_path(clip: Path) -> Path:
        """Return the expected _nobg.webm path for a given .mp4 clip."""
        return clip.parent / f"{clip.stem}_nobg.webm"

    @staticmethod
    def has_nobg(clip: Path) -> bool:
        return NarratorBgRemoveService.nobg_path(clip).exists()
