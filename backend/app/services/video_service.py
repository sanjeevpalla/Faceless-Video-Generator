"""
VideoGenerationService — pure-FFmpeg video pipeline.

Pipeline:
  1. Slideshow  : images → video (concat demuxer for cuts, xfade filter for fades)
  2. Audio mix  : narration + background music via FFmpeg amix
  3. Subtitle burn : FFmpeg subtitles filter

Scene durations come from per-scene WAV files (narration TTS output).
GPU encoding (h264_nvenc) is used automatically when available.
"""
import json
import subprocess
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import asyncio

from app.services.base import BaseService
from app.core.exceptions import ServiceError


# ---------------------------------------------------------------------------
# Style templates
# ---------------------------------------------------------------------------
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "documentary": {
        "transition": "crossfade",
        "animations": [
            "zoom_in", "pan_right", "zoom_out", "pan_left",
            "zoom_in_pan_right", "zoom_in_pan_left",
            "diagonal_zoom_in", "drift_right",
        ],
        "zoom_amount_override": None,
        "color_grade": "cinematic",
        "subtitle_style": "bottom_white",
        "music_volume": 0.12,
        "narration_volume": 1.0,
        "vignette": 0.45,
    },
    "news": {
        "transition": "cut",
        "animations": ["none"],
        "zoom_amount_override": 0.0,
        "color_grade": "neutral",
        "subtitle_style": "lower_third",
        "music_volume": 0.08,
        "narration_volume": 1.0,
        "vignette": 0.0,
    },
    "ai_news": {
        "transition": "crossfade",
        "animations": [
            "zoom_in", "diagonal_zoom_in", "pan_right",
            "zoom_out", "pan_left", "zoom_in_pan_right",
            "zoom_in_pan_left", "drift_right",
        ],
        "zoom_amount_override": None,
        "color_grade": "cool",
        "subtitle_style": "lower_third",
        "music_volume": 0.08,
        "narration_volume": 1.0,
        "vignette": 0.18,
    },
    "technology": {
        "transition": "fade",
        "animations": [
            "zoom_out", "pan_left", "zoom_in", "pan_right",
            "zoom_out_pan_right", "diagonal_zoom_out", "drift_left",
        ],
        "zoom_amount_override": None,
        "color_grade": "cool",
        "subtitle_style": "bottom_white",
        "music_volume": 0.15,
        "narration_volume": 1.0,
        "vignette": 0.30,
    },
    "finance": {
        "transition": "fade",
        "animations": [
            "slow_zoom_in", "pan_right", "slow_zoom_out", "pan_left",
            "drift_right", "drift_left",
        ],
        "zoom_amount_override": None,
        "color_grade": "warm",
        "subtitle_style": "bottom_white",
        "music_volume": 0.10,
        "narration_volume": 1.0,
        "vignette": 0.35,
    },
    "educational": {
        "transition": "crossfade",
        "animations": [
            "zoom_in", "pan_right", "zoom_out", "pan_left",
            "zoom_in_pan_left", "pan_up",
            "zoom_in_pan_down", "diagonal_zoom_in",
        ],
        "zoom_amount_override": None,
        "color_grade": "neutral",
        "subtitle_style": "bottom_yellow",
        "music_volume": 0.10,
        "narration_volume": 1.0,
        "vignette": 0.20,
    },
    "history": {
        "transition": "fade",
        "animations": [
            "slow_zoom_in", "pan_up", "slow_zoom_out", "pan_down",
            "pan_left", "pan_right",
            "diagonal_zoom_in", "drift_right", "tilt_up", "slide_in_left",
        ],
        "zoom_amount_override": 0.06,
        "color_grade": "sepia",
        "subtitle_style": "bottom_white",
        "music_volume": 0.14,
        "narration_volume": 1.0,
        "vignette": 0.50,
    },
    "cinematic": {
        "transition": "crossfade",
        "animations": [
            "zoom_in_pan_right", "zoom_out", "pan_right", "pan_left",
            "zoom_in_pan_left", "drift_right", "slide_in_left", "tilt_up",
        ],
        "zoom_amount_override": None,
        "color_grade": "film",
        "subtitle_style": "bottom_white",
        "music_volume": 0.12,
        "narration_volume": 1.0,
        "vignette": 0.40,
    },
    "dramatic": {
        "transition": "flash",
        "animations": [
            "zoom_burst", "zoom_in", "diagonal_zoom_in", "slide_in_left",
            "slide_in_right", "push_left", "push_right", "zoom_in_pan_right",
        ],
        "zoom_amount_override": None,
        "color_grade": "moody",
        "subtitle_style": "bottom_white",
        "music_volume": 0.15,
        "narration_volume": 1.0,
        "vignette": 0.55,
    },
}


# ---------------------------------------------------------------------------
# Per-scene style rules — keyword-matched from scenes.json metadata
# ---------------------------------------------------------------------------
SCENE_STYLE_RULES: List[Dict[str, Any]] = [
    {
        "keywords": ["space", "galaxy", "star", "cosmos", "universe", "planet", "nebula",
                     "solar", "astronaut", "orbit", "black hole", "supernova", "satellite"],
        "style": {"anim": "zoom_in", "grade": "cool", "effect": "light_leak", "transition": "zoom_blur"},
    },
    {
        "keywords": ["ancient", "history", "historical", "medieval", "empire", "war", "battle",
                     "ruins", "civilization", "pharaoh", "archaeological", "tomb", "dynasty", "kingdom"],
        "style": {"anim": "pan_right", "grade": "vintage", "effect": "film_grain", "transition": "crossfade"},
    },
    {
        "keywords": ["technology", "tech", "digital", "cyber", "artificial intelligence", "ai",
                     "robot", "circuit", "computer", "quantum", "machine learning", "data", "algorithm"],
        "style": {"anim": "diagonal_zoom_in", "grade": "cool", "effect": "chromatic_aberration", "transition": "glitch"},
    },
    {
        "keywords": ["nature", "forest", "ocean", "sea", "mountain", "landscape", "sky",
                     "sunrise", "sunset", "waterfall", "jungle", "wildlife", "river", "cloud"],
        "style": {"anim": "drift_right", "grade": "warm", "effect": "light_leak", "transition": "crossfade"},
    },
    {
        "keywords": ["dark", "shadow", "mystery", "mysterious", "horror", "fear", "night",
                     "haunted", "evil", "apocalypse", "underground", "sinister", "danger"],
        "style": {"anim": "zoom_in", "grade": "moody", "effect": "film_grain", "transition": "crossfade"},
    },
    {
        "keywords": ["future", "futuristic", "neon", "cyberpunk", "hologram", "virtual",
                     "simulation", "matrix", "glowing", "electric", "laser"],
        "style": {"anim": "diagonal_zoom_in", "grade": "neon", "effect": "chromatic_aberration", "transition": "glitch"},
    },
    {
        "keywords": ["science", "research", "discovery", "laboratory", "lab", "experiment",
                     "biology", "chemistry", "physics", "microscope", "dna", "atom", "molecule"],
        "style": {"anim": "zoom_in_pan_right", "grade": "cool", "effect": None, "transition": "crossfade"},
    },
    {
        "keywords": ["city", "urban", "building", "skyscraper", "traffic", "downtown",
                     "architecture", "skyline", "street", "metropolis", "infrastructure"],
        "style": {"anim": "pan_left", "grade": "cinematic", "effect": "light_leak", "transition": "wipe_left"},
    },
    {
        "keywords": ["explosion", "dramatic", "impact", "powerful", "force", "intense",
                     "crash", "destroy", "fire", "chaos", "violent", "rage", "epic"],
        "style": {"anim": "zoom_burst", "grade": "moody", "effect": "chromatic_aberration", "transition": "flash"},
    },
    {
        "keywords": ["calm", "peaceful", "meditation", "serene", "gentle", "quiet",
                     "relaxing", "tranquil", "harmony", "zen", "spiritual"],
        "style": {"anim": "drift_left", "grade": "warm", "effect": None, "transition": "crossfade"},
    },
    {
        "keywords": ["money", "finance", "economy", "market", "stock", "business",
                     "corporate", "investment", "bank", "wealth", "currency", "trade"],
        "style": {"anim": "zoom_in_pan_left", "grade": "cinematic", "effect": None, "transition": "wipe_right"},
    },
    {
        "keywords": ["desert", "pyramid", "sand", "ancient egypt", "hieroglyph",
                     "sphinx", "mummy", "oasis", "dune", "sahara"],
        "style": {"anim": "tilt_up", "grade": "sepia", "effect": "film_grain", "transition": "crossfade"},
    },
    {
        "keywords": ["black and white", "monochrome", "classic", "vintage film",
                     "old photograph", "retro", "nostalgic", "grayscale"],
        "style": {"anim": "pan_right", "grade": "bw", "effect": "film_grain", "transition": "crossfade"},
    },
    {
        "keywords": ["breathtaking", "stunning", "spectacular", "vivid", "vibrant",
                     "colorful", "gorgeous", "beautiful", "hdr"],
        "style": {"anim": "zoom_out", "grade": "hdr", "effect": "light_leak", "transition": "crossfade"},
    },
    {
        "keywords": ["underwater", "ocean floor", "coral", "deep sea", "submarine",
                     "aquatic", "marine", "fish", "whale", "dolphin"],
        "style": {"anim": "drift_right", "grade": "cool", "effect": "light_leak", "transition": "zoom_blur"},
    },
    {
        "keywords": ["film", "movie", "cinema", "cinematic", "dramatic shot", "documentary"],
        "style": {"anim": "zoom_in_pan_right", "grade": "film", "effect": "film_grain", "transition": "crossfade"},
    },
]


class VideoGenerationService(BaseService):
    """Assembles final video from per-scene clips rendered by FFmpeg."""

    service_name = "video_generation"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        template: str = "documentary",
        fps: int = 30,
        resolution: str = "1920x1080",
        zoom_amount: float = 0.10,
        transition_duration: float = 0.5,
        video_codec: str = "libx264",
        audio_codec: str = "aac",
        video_bitrate: str = "8000k",
        audio_bitrate: str = "192k",
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
        narrator_enabled: bool = False,
        narrator_clips_dir: str = "",
        narrator_position: str = "bottom_right",
        narrator_width: int = 320,
        narrator_margin: int = 20,
        narrator_bottom_margin: int = 120,
        narrator_shape: str = "circle",
        logo_path: str = "",
        logo_opacity: float = 1.0,
        logo_scale: float = 0.10,
        logo_margin: int = 20,
        project_type: str = "deep_dive",
        burn_subtitles: bool = True,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.burn_subtitles = burn_subtitles
        self.project_type = project_type
        # AI News projects default to the "ai_news" template when the caller
        # hasn't explicitly picked a different one (i.e. still on "documentary").
        if project_type == "ai_news" and template == "documentary":
            template = "ai_news"
        self.template_cfg = TEMPLATES.get(template, TEMPLATES["documentary"])
        self.template_name = template
        self.fps = fps
        w, h = resolution.split("x")
        self.width, self.height = int(w), int(h)
        override = self.template_cfg.get("zoom_amount_override")
        self.zoom_amount = zoom_amount if override is None else float(override)
        self.transition_duration = min(float(transition_duration), 0.5)
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.video_bitrate = video_bitrate
        self.audio_bitrate = audio_bitrate
        self.output_dir = self.get_output_dir("output")
        self._nvenc_available: Optional[bool] = None
        self.narrator_enabled = narrator_enabled
        self.narrator_clips_dir = narrator_clips_dir
        self.narrator_position = narrator_position
        self.narrator_width = narrator_width
        self.narrator_margin = narrator_margin
        self.narrator_bottom_margin = narrator_bottom_margin
        self.narrator_shape = narrator_shape
        self.logo_path = logo_path
        self.logo_opacity = logo_opacity
        self.logo_scale = logo_scale
        self.logo_margin = logo_margin

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    async def execute(self) -> Dict[str, Any]:
        return await self.generate()

    async def generate(self) -> Dict[str, Any]:
        await self.report_progress(2, "Scanning project assets…")

        images_dir = self.project_dir / "images"
        clips_dir  = self.project_dir / "clips"
        audio_dir  = self.project_dir / "audio"
        subs_dir   = self.project_dir / "subtitles"
        input_dir  = self.project_dir / "input"

        if self.project_type == "ai_news":
            def _ai_sec_key(d: Path) -> tuple:
                n = d.name
                if n == "intro": return (0, 0)
                if n == "outro": return (2, 0)
                if n.startswith("story_"):
                    try: return (1, int(n.split("_", 1)[1]))
                    except: pass
                return (1, 999)
            sections_img_dir = images_dir / "sections"
            image_files: List[Path] = []
            if sections_img_dir.exists():
                for sd in sorted((d for d in sections_img_dir.iterdir() if d.is_dir()), key=_ai_sec_key):
                    image_files.extend(sorted(sd.glob("scene_*.png")))
        else:
            image_files = sorted(images_dir.glob("scene_*.png"))
        if not image_files:
            raise ServiceError(self.service_name, "No scene images found. Generate images first.")

        narration_file = self._find_narration(audio_dir)
        music_file     = None
        srt_file       = subs_dir / "subtitles.srt"

        loop = asyncio.get_event_loop()
        codec = await loop.run_in_executor(None, self._pick_codec)
        self.logger.info(f"Encoding codec: {codec}")

        per_scene_wavs = sorted(audio_dir.glob("scene_*.wav"))
        use_per_scene_audio = len(per_scene_wavs) > 0

        scene_durations = self._calculate_scene_durations(len(image_files), narration_file)

        # Count available clips (generated or user-uploaded replacements)
        clip_files = sorted(clips_dir.glob("scene_*.mp4")) if clips_dir.exists() else []
        clip_info = f"{len(clip_files)} clip(s)" if clip_files else "images only"
        await self.report_progress(5, f"Building {len(image_files)}-scene video ({clip_info})…")

        _ai_news_no_nar: List[Tuple[float, float]] = []
        if self.project_type == "ai_news":
            raw_video, _ai_news_no_nar = await loop.run_in_executor(
                None, self._build_ai_news_video, image_files, clips_dir, scene_durations, codec,
                audio_dir if use_per_scene_audio else None,
            )
            # Auto-generate 9:16 shorts for all sections that have narration
            await self.report_progress(75, "Generating section shorts…")
            await self._auto_generate_ai_news_shorts()
        else:
            raw_video = await loop.run_in_executor(
                None, self._build_hybrid_video, image_files, clips_dir, scene_durations, codec,
                audio_dir if use_per_scene_audio else None,
            )

        # ── Stage 2: add audio ─────────────────────────────────────────
        await self.report_progress(80, "Mixing background music…")
        # When narration is already embedded per-scene (or per-section for AI News),
        # pass narration_path=None so _add_audio only handles music overlay.
        # AI News embeds narration inside _build_ai_news_video, so always skip here.
        _narr_for_mix = (
            None if (use_per_scene_audio or self.project_type == "ai_news")
            else narration_file
        )
        mixed_path = await loop.run_in_executor(
            None, self._add_audio, raw_video, _narr_for_mix, music_file,
        )

        # ── Stage 2.5: narrator overlay ────────────────────────────────
        narrator_clips = self._find_narrator_clips()
        if narrator_clips:
            # For AI News use title-card/agenda intervals; for others detect from silent scenes.
            silent_intervals = (
                _ai_news_no_nar if self.project_type == "ai_news"
                else self._compute_silent_intervals(audio_dir)
            )
            await self.report_progress(87, f"Compositing narrator overlay ({len(narrator_clips)} clip(s))…")
            narrated_path = await loop.run_in_executor(
                None, self._add_narrator_overlay, mixed_path, narrator_clips, silent_intervals,
            )
            if narrated_path != mixed_path:
                try:
                    mixed_path.unlink(missing_ok=True)
                except Exception:
                    pass
                mixed_path = narrated_path

        # ── Stage 2.8: logo overlay ────────────────────────────────────
        if self.logo_path and Path(self.logo_path).is_file():
            await self.report_progress(92, "Compositing logo overlay…")
            logo_path_result = await loop.run_in_executor(
                None, self._add_logo_overlay, mixed_path,
            )
            if logo_path_result != mixed_path:
                try:
                    mixed_path.unlink(missing_ok=True)
                except Exception:
                    pass
                mixed_path = logo_path_result

        # ── Stage 3: subtitle burning ────────────────────────────────────
        # AI News: subtitles already burned per-section inside _build_ai_news_video
        output_path = self.output_dir / "video_final.mp4"
        subtitles_burned = False
        if srt_file.exists() and self.burn_subtitles and self.project_type != "ai_news":
            await self.report_progress(88, "Burning subtitles…")
            sub_out = self.output_dir / "_with_subtitles.mp4"
            ok = await loop.run_in_executor(
                None, self._burn_subtitles_ffmpeg, mixed_path, srt_file, sub_out, codec
            )
            if ok and sub_out.exists():
                subtitles_burned = True
                try:
                    mixed_path.unlink(missing_ok=True)
                except Exception:
                    pass
                mixed_path = sub_out
        mixed_path.replace(output_path)

        # Cleanup intermediates
        for tmp in [raw_video, mixed_path]:
            if tmp != output_path:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass

        size_mb = round(output_path.stat().st_size / (1024 * 1024), 2) if output_path.exists() else 0
        total   = len(image_files)

        manifest = {
            "output_path": str(output_path),
            "filename": output_path.name,
            "scene_count": total,
            "template": self.template_name,
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps,
            "duration": round(sum(scene_durations), 2),
            "size_mb": size_mb,
            "codec": codec,
            "has_audio": narration_file is not None,
            "has_music": music_file is not None,
            "has_subtitles": subtitles_burned,
            "has_narrator": len(narrator_clips) > 0,
        }

        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        await self.report_progress(100, "Video render complete")
        return manifest

    # ------------------------------------------------------------------
    # AI News short auto-generation
    # ------------------------------------------------------------------
    async def _auto_generate_ai_news_shorts(self) -> None:
        """Generate 9:16 shorts for every AI News section that has narration.wav."""
        from app.services.shorts_service import AiNewsShortsService
        svc = AiNewsShortsService(project_id=self.project_id, project_dir=self.project_dir)
        audio_sections = self.project_dir / "audio" / "sections"
        if not audio_sections.exists():
            return
        labels = sorted(d.name for d in audio_sections.iterdir()
                        if d.is_dir() and (d / "narration.wav").exists())
        for i, label in enumerate(labels, 1):
            try:
                await self.report_progress(
                    75 + (i / max(len(labels), 1)) * 4,
                    f"Generating short {i}/{len(labels)}: {label}…",
                )
                await svc.generate_section_short(label)
            except Exception as exc:
                self.logger.warning("Auto-short failed for '%s': %s", label, exc)

    # ------------------------------------------------------------------
    # Codec selection
    # ------------------------------------------------------------------
    def _pick_codec(self) -> str:
        if self._nvenc_available is not None:
            return "h264_nvenc" if self._nvenc_available else "libx264"
        try:
            r = subprocess.run(
                ["ffmpeg", "-f", "lavfi", "-i", "nullsrc=s=2x2:duration=0.1",
                 "-vframes", "1", "-c:v", "h264_nvenc", "-f", "null", "-"],
                capture_output=True, timeout=10,
            )
            self._nvenc_available = (r.returncode == 0)
        except Exception:
            self._nvenc_available = False
        self.logger.info(f"h264_nvenc available: {self._nvenc_available}")
        return "h264_nvenc" if self._nvenc_available else "libx264"

    def _codec_args(self, codec: str) -> List[str]:
        if codec == "h264_nvenc":
            return ["-c:v", "h264_nvenc", "-preset", "p4",
                    "-b:v", self.video_bitrate, "-bufsize", self.video_bitrate]
        return ["-c:v", "libx264", "-preset", "fast",
                "-b:v", self.video_bitrate, "-bufsize", self.video_bitrate]

    # ------------------------------------------------------------------
    # Per-frame visual effects
    # ------------------------------------------------------------------
    def _apply_color_grade(self, img, grade: str):
        """Apply a color grade to a PIL RGB image. Returns a new PIL image."""
        from PIL import Image as PILImage, ImageEnhance
        import numpy as np

        if not grade or grade == "neutral":
            return img

        arr = np.array(img, dtype=np.float32)

        if grade == "sepia":
            lum = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
            arr[:, :, 0] = np.clip(lum * 1.08, 0, 255)
            arr[:, :, 1] = np.clip(lum * 0.86, 0, 255)
            arr[:, :, 2] = np.clip(lum * 0.68, 0, 255)
            return PILImage.fromarray(arr.astype(np.uint8))

        if grade == "warm":
            arr[:, :, 0] = np.clip(arr[:, :, 0] * 1.08, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] * 0.88, 0, 255)
            img = PILImage.fromarray(arr.astype(np.uint8))
            return ImageEnhance.Contrast(img).enhance(1.06)

        if grade == "cool":
            arr[:, :, 0] = np.clip(arr[:, :, 0] * 0.90, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] * 1.12, 0, 255)
            img = PILImage.fromarray(arr.astype(np.uint8))
            return ImageEnhance.Contrast(img).enhance(1.05)

        if grade == "cinematic":
            # Lift blacks, crush highlights, slight desaturation → teal-orange feel
            norm = np.clip(arr / 255.0, 0, 1)
            norm = np.power(norm, 0.92) * 0.94 + 0.03
            img = PILImage.fromarray(np.clip(norm * 255, 0, 255).astype(np.uint8))
            img = ImageEnhance.Color(img).enhance(0.85)
            return ImageEnhance.Contrast(img).enhance(1.10)

        if grade == "vintage":
            # Faded, lifted shadows, warm yellowish tint, desaturated
            norm = np.clip(arr / 255.0, 0, 1)
            norm = norm * 0.78 + 0.12
            arr  = np.clip(norm * 255, 0, 255)
            arr[:, :, 0] = np.clip(arr[:, :, 0] * 1.07, 0, 255)
            arr[:, :, 1] = np.clip(arr[:, :, 1] * 1.02, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] * 0.80, 0, 255)
            img = PILImage.fromarray(arr.astype(np.uint8))
            return ImageEnhance.Color(img).enhance(0.72)

        if grade == "moody":
            # Dark, high contrast, heavily desaturated
            norm = np.clip(arr / 255.0, 0, 1)
            norm = np.power(norm, 1.15)
            arr  = np.clip(norm * 255, 0, 255)
            img  = PILImage.fromarray(arr.astype(np.uint8))
            img  = ImageEnhance.Contrast(img).enhance(1.30)
            return ImageEnhance.Color(img).enhance(0.45)

        if grade == "film":
            # S-curve tone mapping, warm split tone, film stock feel
            norm = np.clip(arr / 255.0, 0, 1)
            norm = np.where(norm < 0.5,
                            2.0 * norm * norm,
                            1.0 - 2.0 * (1.0 - norm) * (1.0 - norm))
            norm = norm * 0.90 + 0.05
            arr  = np.clip(norm * 255, 0, 255)
            arr[:, :, 0] = np.clip(arr[:, :, 0] * 1.04, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] * 0.92, 0, 255)
            img  = PILImage.fromarray(arr.astype(np.uint8))
            return ImageEnhance.Color(img).enhance(0.88)

        if grade == "bw":
            # True grayscale with boosted contrast
            lum = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
            arr[:, :, 0] = arr[:, :, 1] = arr[:, :, 2] = lum
            img = PILImage.fromarray(arr.astype(np.uint8))
            return ImageEnhance.Contrast(img).enhance(1.25)

        if grade == "neon":
            # Oversaturated vivid colors
            img = PILImage.fromarray(arr.astype(np.uint8))
            img = ImageEnhance.Color(img).enhance(2.0)
            return ImageEnhance.Contrast(img).enhance(1.15)

        if grade == "hdr":
            # Boosted contrast and saturation, punchy midtones
            norm = np.clip(arr / 255.0, 0, 1)
            norm = np.power(norm, 0.88)
            arr  = np.clip(norm * 255, 0, 255)
            img  = PILImage.fromarray(arr.astype(np.uint8))
            img  = ImageEnhance.Contrast(img).enhance(1.20)
            return ImageEnhance.Color(img).enhance(1.30)

        if grade == "bright":
            # Lifted exposure, airy feel
            norm = np.clip(arr / 255.0, 0, 1)
            norm = np.power(norm, 0.80)
            arr  = np.clip(norm * 255, 0, 255)
            img  = PILImage.fromarray(arr.astype(np.uint8))
            return ImageEnhance.Contrast(img).enhance(1.10)

        return img

    def _make_vignette(self, W: int, H: int, strength: float):
        """Return a grayscale PIL mask: 255 at center, darker toward edges."""
        import numpy as np
        from PIL import Image as PILImage

        X, Y = np.meshgrid(np.linspace(-1, 1, W), np.linspace(-1, 1, H))
        dist = (X ** 2 + Y ** 2) ** 0.5
        mask = 1.0 - np.clip(dist * strength, 0, 1) ** 2.0
        return PILImage.fromarray((mask * 255).astype(np.uint8), "L")

    def _apply_film_grain(self, frame, intensity: float = 0.04):
        """Add random noise texture for a film grain look."""
        import numpy as np
        from PIL import Image as PILImage
        arr = np.array(frame, dtype=np.float32)
        noise = np.random.randn(*arr.shape) * intensity * 255
        return PILImage.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))

    def _make_light_leak_overlay(self, W: int, H: int):
        """RGBA overlay: warm light leak at top-right, cool at bottom-left."""
        import numpy as np
        from PIL import Image as PILImage
        x = np.linspace(0, 1, W); y = np.linspace(0, 1, H)
        X, Y = np.meshgrid(x, y)
        a1 = np.clip(1 - ((1 - X) ** 2 + Y ** 2) ** 0.5 * 2.0, 0, 1) ** 2 * 55
        a2 = np.clip(1 - (X ** 2 + (1 - Y) ** 2) ** 0.5 * 2.5, 0, 1) ** 2 * 30
        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[:, :, 0] = np.clip(a1,           0, 255).astype(np.uint8)
        rgba[:, :, 1] = np.clip(a1 * 0.65,    0, 255).astype(np.uint8)
        rgba[:, :, 2] = np.clip(a1 * 0.1 + a2, 0, 255).astype(np.uint8)
        rgba[:, :, 3] = np.clip(a1 + a2,       0, 255).astype(np.uint8)
        return PILImage.fromarray(rgba, "RGBA")

    def _apply_chromatic_aberration(self, frame, shift: int = 3):
        """Shift the R channel right and B channel left for a digital glitch look."""
        import numpy as np
        from PIL import Image as PILImage
        arr = np.array(frame); result = arr.copy()
        result[:, shift:,  0] = arr[:, :-shift, 0]
        result[:, :shift,  0] = arr[:, 0:1,     0]
        result[:, :-shift, 2] = arr[:, shift:,  2]
        result[:, -shift:, 2] = arr[:, -1:,     2]
        return PILImage.fromarray(result)

    def _apply_frame_effect(self, frame, effect: Optional[str], leak_overlay, vignette_mask, black_vignette):
        """Apply per-frame effects: film_grain / light_leak / chromatic_aberration + vignette."""
        from PIL import Image as PILImage
        if effect == "film_grain":
            frame = self._apply_film_grain(frame)
        elif effect == "chromatic_aberration":
            frame = self._apply_chromatic_aberration(frame)
        if leak_overlay is not None:
            rgba = frame.convert("RGBA")
            rgba.paste(leak_overlay, (0, 0), mask=leak_overlay.split()[3])
            frame = rgba.convert("RGB")
        if vignette_mask is not None:
            frame = PILImage.composite(frame, black_vignette, vignette_mask)
        return frame

    def _analyze_scene_style(self, meta: Dict, scene_idx: int, anim_list: List[str]) -> Dict:
        """Match scene metadata against SCENE_STYLE_RULES; fall back to template defaults."""
        text = " ".join([
            meta.get("title", ""),
            meta.get("narration", ""),
            meta.get("visual_description", ""),
        ]).lower()
        for rule in SCENE_STYLE_RULES:
            if any(kw in text for kw in rule["keywords"]):
                style = dict(rule["style"])
                style.setdefault("anim", anim_list[scene_idx % len(anim_list)])
                return style
        return {
            "anim":       anim_list[scene_idx % len(anim_list)],
            "grade":      self.template_cfg.get("color_grade", "neutral"),
            "effect":     None,
            "transition": self.template_cfg.get("transition", "crossfade"),
        }

    def _transition_frame(self, old_f, new_f, alpha: float, transition: str):
        """Generate one blended frame between two scenes using the given transition style."""
        from PIL import Image as PILImage, ImageFilter
        import numpy as np
        W, H = self.width, self.height

        if transition in ("crossfade", "fade"):
            return PILImage.blend(old_f, new_f, alpha)

        if transition == "wipe_left":
            x = int(W * alpha)
            frame = old_f.copy()
            if x > 0:
                frame.paste(new_f.crop((0, 0, x, H)), (0, 0))
            return frame

        if transition == "wipe_right":
            x = int(W * (1.0 - alpha))
            frame = old_f.copy()
            if x < W:
                frame.paste(new_f.crop((x, 0, W, H)), (x, 0))
            return frame

        if transition == "flash":
            white = PILImage.new("RGB", (W, H), (255, 255, 255))
            if alpha < 0.5:
                return PILImage.blend(old_f, white, alpha * 2.0)
            return PILImage.blend(white, new_f, (alpha - 0.5) * 2.0)

        if transition == "zoom_blur":
            t = 1.0 - abs(2.0 * alpha - 1.0)
            blur_r = int(t * 10)
            blended = PILImage.blend(old_f, new_f, alpha)
            return blended.filter(ImageFilter.GaussianBlur(radius=blur_r)) if blur_r > 0 else blended

        if transition == "glitch":
            arr = np.array(PILImage.blend(old_f, new_f, alpha))
            n_strips = max(0, int((1.0 - abs(2.0 * alpha - 1.0)) * 12))
            for _ in range(n_strips):
                ys = np.random.randint(0, H)
                hs = np.random.randint(2, max(3, H // 20))
                sh = int(np.random.choice([-1, 1]) * np.random.randint(5, max(6, W // 8)))
                arr[ys:min(ys + hs, H)] = np.roll(arr[ys:min(ys + hs, H)], sh, axis=1)
            return PILImage.fromarray(arr)

        return PILImage.blend(old_f, new_f, alpha)

    # ------------------------------------------------------------------
    # Stage 1 — slideshow (images → video, animated or static)
    # ------------------------------------------------------------------
    def _create_slideshow(
        self,
        image_files: List[Path],
        scene_durations: List[float],
        codec: str,
    ) -> Path:
        out = self.output_dir / "_raw_video.mp4"
        animations = self.template_cfg.get("animations", ["zoom_in"])
        has_animation = any(a != "none" for a in animations)

        if has_animation:
            return self._slideshow_animated(image_files, scene_durations, out, codec)

        # Static fallback (news template or all-"none" animations)
        if len(image_files) == 1:
            return self._slideshow_single(image_files[0], scene_durations[0], out, codec)
        transition = self.template_cfg.get("transition", "crossfade")
        if transition == "cut":
            return self._slideshow_cut(image_files, scene_durations, out, codec)
        return self._slideshow_xfade(image_files, scene_durations, out, codec)

    def _build_zoompan_vf(self, anim: str, n_frames: int) -> str:
        """Return an FFmpeg -vf filter chain that applies Ken Burns motion to a looped image.

        Canvas strategy (avoids bilinear upscaling which causes blur):
          - Zoom-only: NO pre-scale — zoompan works on the source image directly.
            For sources larger than output (e.g. 1920×1080 → 1280×720), zoompan
            always downscales the crop to W×H, never upscales.
          - Pan/drift: scale to 1.20×W/H so the pan crop is 1:1 from the canvas.
          - Zoom+pan combined: scale to (z_pan+za)×W/H so the maximum-zoom crop
            is also 1:1, eliminating the previous upscale artifact.
        """
        W, H = self.width, self.height
        d = max(n_frames, 2)
        za = max(self.zoom_amount, 0.04)
        fps = self.fps

        # Pan canvas: 1.20× output so zoompan crops exactly W×H at z=z_pan (1:1)
        XW = int(W * 1.20)
        XH = int(H * 1.20)
        z_pan = round(XW / W, 4)

        # Zoom+pan canvas: sized so the peak-zoom crop is also 1:1 (no upscale)
        ZW = int(W * (z_pan + za + 0.01))
        ZH = int(H * (z_pan + za + 0.01))
        z_zp = round(ZW / W, 4)

        # --- Zoom-only: no pre-scale so zoompan works on the full source image ---
        # When source > output (e.g. 1920×1080) the crop is always a downscale. ✓
        if anim in ("zoom_in", "slow_zoom_in"):
            za_eff = za if anim == "zoom_in" else za * 0.55
            return (
                f"zoompan=z='1+{za_eff:.5f}*on/{d}'"
                f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim in ("zoom_out", "slow_zoom_out"):
            za_eff = za if anim == "zoom_out" else za * 0.55
            return (
                f"zoompan=z='max({1 + za_eff:.4f}-{za_eff:.5f}*on/{d},1)'"
                f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim == "zoom_burst":
            za_b = min(za * 2.0, 0.25)
            return (
                f"zoompan=z='1+{za_b:.5f}*on/{d}'"
                f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )

        # --- Pan/drift: 1.20× canvas, z=z_pan gives 1:1 crop ---
        if anim == "pan_right":
            return (
                f"scale={XW}:{XH}:flags=lanczos,"
                f"zoompan=z='{z_pan:.4f}'"
                f":x='(iw-iw/zoom)*on/{d}':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim == "pan_left":
            return (
                f"scale={XW}:{XH}:flags=lanczos,"
                f"zoompan=z='{z_pan:.4f}'"
                f":x='(iw-iw/zoom)*(1-on/{d})':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim in ("pan_up", "tilt_up"):
            return (
                f"scale={XW}:{XH}:flags=lanczos,"
                f"zoompan=z='{z_pan:.4f}'"
                f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*(1-on/{d})'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim == "pan_down":
            return (
                f"scale={XW}:{XH}:flags=lanczos,"
                f"zoompan=z='{z_pan:.4f}'"
                f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*on/{d}'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim in ("drift_right", "slide_in_left"):
            return (
                f"scale={XW}:{XH}:flags=lanczos,"
                f"zoompan=z='{z_pan:.4f}'"
                f":x='(iw-iw/zoom)*0.25*(1+on/{d})':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim in ("drift_left", "slide_in_right", "push_left", "push_right"):
            return (
                f"scale={XW}:{XH}:flags=lanczos,"
                f"zoompan=z='{z_pan:.4f}'"
                f":x='(iw-iw/zoom)*0.75*(1-on/{d}*0.5)':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )

        # --- Zoom+pan: (z_pan+za)× canvas so peak zoom is still 1:1 ---
        if anim in ("zoom_in_pan_right", "diagonal_zoom_in"):
            return (
                f"scale={ZW}:{ZH}:flags=lanczos,"
                f"zoompan=z='{z_zp:.4f}+{za:.5f}*on/{d}'"
                f":x='(iw-iw/zoom)*on/{d}':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim == "zoom_in_pan_left":
            return (
                f"scale={ZW}:{ZH}:flags=lanczos,"
                f"zoompan=z='{z_zp:.4f}+{za:.5f}*on/{d}'"
                f":x='(iw-iw/zoom)*(1-on/{d})':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim == "zoom_in_pan_down":
            return (
                f"scale={ZW}:{ZH}:flags=lanczos,"
                f"zoompan=z='{z_zp:.4f}+{za:.5f}*on/{d}'"
                f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*on/{d}'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        if anim in ("zoom_out_pan_right", "diagonal_zoom_out"):
            return (
                f"scale={ZW}:{ZH}:flags=lanczos,"
                f"zoompan=z='max({z_zp + za:.4f}-{za:.5f}*on/{d},{z_zp:.4f})'"
                f":x='(iw-iw/zoom)*on/{d}':y='(ih-ih/zoom)/2'"
                f":d={d}:s={W}x{H}:fps={fps},setsar=1"
            )
        # fallback: gentle centred zoom-in on source directly
        return (
            f"zoompan=z='1+{za:.5f}*on/{d}'"
            f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
            f":d={d}:s={W}x{H}:fps={fps},setsar=1"
        )

    # ------------------------------------------------------------------
    # AI News: per-story segment pipeline
    # ------------------------------------------------------------------

    def _build_intro_agenda_clip(
        self,
        story_titles: List[str],
        out_path: Path,
        codec: str,
        duration: float = 6.0,
        with_audio: bool = True,
    ) -> Path:
        """Build a 'Today's Top 10 AI Stories' overview card as a short video clip."""
        from PIL import Image as PILImage, ImageDraw, ImageFont

        W, H = self.width, self.height
        png = out_path.with_suffix(".png")

        img = PILImage.new("RGB", (W, H), (6, 14, 32))
        draw = ImageDraw.Draw(img)

        for y in range(0, H, 2):
            t = y / H
            draw.rectangle(
                [0, y, W, y + 2],
                fill=(int(6 + t * 14), int(14 + t * 18), int(32 + t * 28)),
            )

        AMBER = (255, 176, 0)
        WHITE = (255, 255, 255)
        DIM   = (160, 160, 180)

        draw.rectangle([0, 0, W, 6],   fill=AMBER)
        draw.rectangle([0, H - 6, W, H], fill=AMBER)
        draw.rectangle([0, 0, 10, H],  fill=AMBER)

        def load_f(sz: int, bold: bool = False):
            for n in (
                ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"] if bold
                else ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]
            ):
                try:
                    return ImageFont.truetype(n, sz)
                except Exception:
                    pass
            return ImageFont.load_default()

        hdr_font  = load_f(int(H * 0.052), bold=True)
        item_font = load_f(int(H * 0.030))
        ftr_font  = load_f(int(H * 0.026))

        # Channel / date header
        draw.text(
            (W // 2, int(H * 0.08)),
            "TODAY'S TOP 10 AI STORIES",
            font=hdr_font, fill=AMBER, anchor="mm",
        )
        sep_y = int(H * 0.145)
        draw.rectangle([W // 2 - 320, sep_y, W // 2 + 320, sep_y + 4], fill=AMBER)

        # Story bullet list — fit full title within available width
        text_x   = int(W * 0.13)
        max_tw   = W - text_x - int(W * 0.03)   # right margin

        def _fit_title(t: str) -> str:
            try:
                if draw.textlength(t, font=item_font) <= max_tw:
                    return t
                # Trim word-by-word until it fits with ellipsis
                words = t.split()
                acc = ""
                for w in words:
                    candidate = (acc + " " + w).strip()
                    if draw.textlength(candidate + "…", font=item_font) <= max_tw:
                        acc = candidate
                    else:
                        break
                return (acc + "…") if acc else t[:60] + "…"
            except Exception:
                return t

        line_h = int(H * 0.066)
        y = int(H * 0.17)
        for i, title in enumerate(story_titles[:10], 1):
            display = _fit_title(title)
            # Number bullet (amber)
            draw.text((int(W * 0.06), y), f"{i:2d}.", font=item_font, fill=AMBER)
            # Title text (white)
            draw.text((text_x, y), display, font=item_font, fill=WHITE)
            y += line_h

        draw.text(
            (W // 2, H - 38),
            "DEEP DIVE AI  ·  AI NEWS",
            font=ftr_font, fill=DIM, anchor="mm",
        )

        img.save(str(png))

        cmd: List[str] = ["ffmpeg", "-y", "-loop", "1", "-i", str(png)]
        if with_audio:
            cmd += ["-f", "lavfi", "-i",
                    "aevalsrc=0:channel_layout=mono:sample_rate=44100"]
        cmd += [
            "-vf", f"scale={W}:{H}:flags=lanczos,setsar=1",
            "-t", f"{duration:.3f}", "-r", str(self.fps),
            *self._codec_args(codec), "-pix_fmt", "yuv420p",
        ]
        cmd += ["-c:a", "aac", "-b:a", "128k"] if with_audio else ["-an"]
        cmd.append(str(out_path))

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise ServiceError(
                self.service_name,
                f"Intro agenda clip failed: {r.stderr[-200:]}"
            )
        try:
            png.unlink(missing_ok=True)
        except Exception:
            pass
        return out_path

    def _build_title_card_clip(
        self,
        num: int,
        title: str,
        out_path: Path,
        codec: str,
        duration: float = 3.0,
        with_audio: bool = True,
    ) -> Path:
        """Render a story title card via _make_title_card then encode it as a video clip."""
        W, H = self.width, self.height
        png = out_path.with_suffix(".png")

        self._make_title_card(num, title, png)

        cmd: List[str] = ["ffmpeg", "-y", "-loop", "1", "-i", str(png)]
        if with_audio:
            cmd += ["-f", "lavfi", "-i",
                    "aevalsrc=0:channel_layout=mono:sample_rate=44100"]
        cmd += [
            "-vf", f"scale={W}:{H}:flags=lanczos,setsar=1",
            "-t", f"{duration:.3f}", "-r", str(self.fps),
            *self._codec_args(codec), "-pix_fmt", "yuv420p",
        ]
        cmd += ["-c:a", "aac", "-b:a", "128k"] if with_audio else ["-an"]
        cmd.append(str(out_path))

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise ServiceError(
                self.service_name,
                f"Title card encode failed (story {num}): {r.stderr[-200:]}"
            )
        try:
            png.unlink(missing_ok=True)
        except Exception:
            pass
        return out_path

    # ------------------------------------------------------------------
    # SRT helpers for per-section subtitle extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_srt(srt_path: Path) -> List[Dict]:
        """Parse a .srt file into a list of {index, start, end, text} dicts (times in seconds)."""
        entries: List[Dict] = []
        try:
            text = srt_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return entries

        def _ts(s: str) -> float:
            s = s.strip().replace(",", ".")
            parts = s.split(":")
            try:
                h, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
                return h * 3600 + m * 60 + sec
            except Exception:
                return 0.0

        import re as _re
        blocks = _re.split(r"\n\s*\n", text.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            idx_line  = lines[0].strip()
            time_line = lines[1].strip()
            body      = " ".join(l.strip() for l in lines[2:])
            m = _re.match(r"(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)", time_line)
            if not m:
                continue
            entries.append({
                "index": idx_line,
                "start": _ts(m.group(1)),
                "end":   _ts(m.group(2)),
                "text":  body,
            })
        return entries

    @staticmethod
    def _extract_section_srt(
        entries: List[Dict],
        narr_start: float,
        narr_end: float,
        out_path: Path,
    ) -> Optional[Path]:
        """Write a new SRT from *entries* that overlap [narr_start, narr_end),
        with timestamps shifted so the section starts at 0."""
        overlap = [
            e for e in entries
            if e["end"] > narr_start and e["start"] < narr_end
        ]
        if not overlap:
            return None

        def _fmt(t: float) -> str:
            t = max(0.0, t)
            h = int(t // 3600); m = int((t % 3600) // 60)
            s = int(t % 60); ms = int((t % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines: List[str] = []
        for i, e in enumerate(overlap, 1):
            s = max(0.0, e["start"] - narr_start)
            en = max(0.0, e["end"]   - narr_start)
            lines.append(f"{i}\n{_fmt(s)} --> {_fmt(en)}\n{e['text']}\n")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path

    # ------------------------------------------------------------------
    # Main AI News builder — 12 independent section mini-videos
    # ------------------------------------------------------------------

    def _build_ai_news_video(
        self,
        image_files: List[Path],
        clips_dir: Optional[Path],
        scene_durations: List[float],
        codec: str,
        audio_dir: Optional[Path] = None,
    ) -> Path:
        """Build the AI News final video as ordered, independent section mini-videos.

        Each section (intro / 10 stories / outro) becomes a self-contained mini-video
        with its own muxed narration audio and burned subtitles.

        Final order:
          01_intro  ·  02_agenda (Today's Top 10)  ·  03_story_01  ·  …  ·  12_story_10  ·  13_outro

        Music is added by the caller (Stage 2 of generate()).
        Stage 3 subtitle burning is skipped for AI News (done here per-section).
        """
        import shutil as _shutil

        out          = self.output_dir / "_raw_video.mp4"
        segs_dir     = self.output_dir / "_segments";       segs_dir.mkdir(exist_ok=True)
        sections_dir = self.output_dir / "_sections";       sections_dir.mkdir(exist_ok=True)
        cards_dir    = self.output_dir / "_title_cards";    cards_dir.mkdir(exist_ok=True)
        parts_dir    = self.output_dir / "_news_parts";     parts_dir.mkdir(exist_ok=True)

        scenes_meta   = self._load_scenes_json()
        animations    = self.template_cfg.get("animations", ["none"])
        has_anim      = any(a != "none" for a in animations)
        has_sec_audio = (self.project_dir / "audio" / "sections").exists()

        # Load existing SRT for per-section extraction (avoids running Whisper 12×)
        srt_global = self.project_dir / "subtitles" / "subtitles.srt"
        srt_entries = self._parse_srt(srt_global) if srt_global.exists() else []

        # Pre-generate badge PNGs
        badge_pngs: Dict[int, Path] = {}
        for sm in scenes_meta:
            sn = int(sm.get("story_number", 0))
            if sn > 0 and sn not in badge_pngs:
                bp = cards_dir / f"badge_{sn:02d}.png"
                self._make_story_badge(sn, 108, bp)
                badge_pngs[sn] = bp

        # ── 1. Encode per-scene video segments (video-only, badge composited in) ─
        import wave as _wave

        seg_paths:    List[Path]  = []
        narr_offsets: List[float] = []
        narr_t = 0.0

        for idx, (img_file, duration) in enumerate(zip(image_files, scene_durations)):
            try:
                scene_id = int(img_file.stem.split("_")[1])
            except (IndexError, ValueError):
                scene_id = idx + 1

            sm        = scenes_meta[idx] if idx < len(scenes_meta) else {}
            story_num = int(sm.get("story_number", 0))
            seg_out   = segs_dir / f"seg_{idx:03d}.mp4"
            encoded   = False

            clip_path: Optional[Path] = None
            # For AI news, extract section label from the image path and check
            # for LTX clips at clips/sections/{label}/scene_NNN.mp4
            if self.project_type == "ai_news":
                # img_file is images/sections/{label}/scene_NNN.png — parent is the label dir
                _sec_label = img_file.parent.name  # e.g. "story_01"
                ltx_cand = (
                    self.project_dir / "clips" / "sections"
                    / _sec_label / f"scene_{scene_id:03d}.mp4"
                )
                if ltx_cand.exists():
                    clip_path = ltx_cand
            # Fall back to flat clips dir (deep-dive / pre-generated)
            if clip_path is None and clips_dir and clips_dir.exists():
                cand = clips_dir / f"scene_{scene_id:03d}.mp4"
                if cand.exists():
                    clip_path = cand

            if clip_path:
                cdur = self._probe_duration(clip_path)
                trimmed_dir = self.output_dir / "_trimmed_clips"
                trimmed_dir.mkdir(exist_ok=True)
                if cdur > duration + 0.05:
                    clip_path = self._trim_clip(clip_path, duration, trimmed_dir)
                r = subprocess.run([
                    "ffmpeg", "-y",
                    *(["-stream_loop", "-1"] if cdur < duration - 0.05 else []),
                    "-i", str(clip_path), "-t", f"{duration:.4f}",
                    "-vf", f"scale={self.width}:{self.height}:flags=lanczos,"
                           f"fps={self.fps},setsar=1",
                    *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an", str(seg_out),
                ], capture_output=True, text=True, timeout=300)
                encoded = r.returncode == 0

            if not encoded:
                n_frames = max(1, int(round(duration * self.fps)))
                badge    = badge_pngs.get(story_num) if story_num > 0 else None

                if has_anim:
                    style = self._analyze_scene_style(sm, idx, animations)
                    avf   = self._build_zoompan_vf(style["anim"], n_frames)
                    if badge:
                        cmd = [
                            "ffmpeg", "-y",
                            "-loop", "1", "-i", str(img_file),
                            "-loop", "1", "-i", str(badge),
                            "-filter_complex",
                            f"[0:v]{avf}[bg];[bg][1:v]overlay=x=24:y=24[out]",
                            "-map", "[out]",
                            "-t", f"{duration:.4f}", "-r", str(self.fps),
                            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
                            str(seg_out),
                        ]
                    else:
                        cmd = [
                            "ffmpeg", "-y", "-loop", "1", "-i", str(img_file),
                            "-vf", avf, "-t", f"{duration:.4f}", "-r", str(self.fps),
                            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
                            str(seg_out),
                        ]
                else:
                    svf = f"scale={self.width}:{self.height}:flags=lanczos,setsar=1"
                    if badge:
                        cmd = [
                            "ffmpeg", "-y",
                            "-loop", "1", "-i", str(img_file),
                            "-loop", "1", "-i", str(badge),
                            "-filter_complex",
                            f"[0:v]{svf}[bg];[bg][1:v]overlay=x=24:y=24[out]",
                            "-map", "[out]",
                            "-t", f"{duration:.4f}", "-r", str(self.fps),
                            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
                            str(seg_out),
                        ]
                    else:
                        cmd = [
                            "ffmpeg", "-y", "-loop", "1", "-i", str(img_file),
                            "-vf", svf, "-t", f"{duration:.4f}", "-r", str(self.fps),
                            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
                            str(seg_out),
                        ]

                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=max(600, int(duration * 20)))
                if r.returncode != 0:
                    raise ServiceError(
                        self.service_name,
                        f"Scene {scene_id} encode failed: {r.stderr[-200:]}"
                    )

            # Track narration clock (for SRT time-shifting)
            narr_offsets.append(narr_t)
            if audio_dir:
                wav = audio_dir / f"scene_{scene_id:03d}.wav"
                if wav.exists():
                    try:
                        with _wave.open(str(wav), "rb") as wf:
                            narr_t += wf.getnframes() / float(wf.getframerate())
                    except Exception:
                        narr_t += duration
                else:
                    narr_t += duration
            else:
                narr_t += duration

            seg_paths.append(seg_out)
            self.logger.info("Scene %d/%d encoded (story_num=%d)",
                             idx + 1, len(image_files), story_num)

        # ── 2. Group scenes into ordered sections ─────────────────────────
        # Cap to image count: scenes_meta may have more entries than generated images
        n_img = len(image_files)
        story_idxs = [
            i for i, sm in enumerate(scenes_meta[:n_img])
            if int(sm.get("story_number", 0)) > 0
        ]
        first_si = story_idxs[0]  if story_idxs else n_img
        last_si  = story_idxs[-1] if story_idxs else -1

        # Build ordered sections list
        sections: List[Dict] = []
        if first_si > 0:
            sections.append({
                "type": "intro", "story_num": 0, "title": "",
                "indices": list(range(0, first_si)),
            })
        seen_sns: List[int] = []
        story_idx_map: Dict[int, List[int]] = {}
        for i in range(first_si, min(last_si + 1, n_img)):
            sn = int(scenes_meta[i].get("story_number", 0)) if i < len(scenes_meta) else 0
            if sn > 0:
                if sn not in story_idx_map:
                    story_idx_map[sn] = []
                    seen_sns.append(sn)
                story_idx_map[sn].append(i)
        for sn in seen_sns:
            sm0 = scenes_meta[story_idx_map[sn][0]]
            sections.append({
                "type": "story", "story_num": sn,
                "title": sm0.get("story_title", f"Story {sn}"),
                "indices": story_idx_map[sn],
            })
        if 0 <= last_si < n_img - 1:
            sections.append({
                "type": "outro", "story_num": 0, "title": "",
                "indices": list(range(last_si + 1, n_img)),
            })

        # ── 3. Build title cards + agenda clip ───────────────────────────
        card_clips: Dict[int, Path] = {}
        for sec in sections:
            if sec["type"] == "story":
                sn, title = sec["story_num"], sec["title"]
                cp = cards_dir / f"title_{sn:02d}.mp4"
                self._build_title_card_clip(sn, title, cp, codec,
                                            duration=3.0,
                                            with_audio=has_sec_audio or (audio_dir is not None))
                card_clips[sn] = cp
                self.logger.info("Title card %02d: %s", sn, title[:60])

        story_titles = [sec["title"] for sec in sections if sec["type"] == "story"]
        intro_agenda: Optional[Path] = None
        if story_titles:
            ap = cards_dir / "intro_agenda.mp4"
            self._build_intro_agenda_clip(story_titles, ap, codec,
                                          duration=6.0,
                                          with_audio=has_sec_audio or (audio_dir is not None))
            intro_agenda = ap
            self.logger.info("Intro agenda card: %d stories listed", len(story_titles))

        # ── 4. Build each section mini-video ────────────────────────────────
        def _concat_c(clips: List[Path], dest: Path) -> Path:
            if not clips:
                return dest
            if len(clips) == 1:
                _shutil.copy2(str(clips[0]), str(dest))
                return dest
            cf = dest.with_suffix(".txt")
            cf.write_text(
                "\n".join(f"file '{str(c).replace(chr(92), '/')}'" for c in clips),
                encoding="utf-8",
            )
            r = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(cf), "-c", "copy", str(dest)],
                capture_output=True, text=True, timeout=600,
            )
            if r.returncode != 0:
                raise ServiceError(self.service_name,
                                   f"Concat failed: {r.stderr[-200:]}")
            return dest

        ordered_parts: List[Path] = []
        ordered_labels: List[str] = []
        part_num = 1

        for sec in sections:
            sec_type  = sec["type"]
            story_num = sec["story_num"]
            indices   = sec["indices"]
            label     = f"story_{story_num:02d}" if sec_type == "story" else sec_type
            sec_dir   = sections_dir / label
            sec_dir.mkdir(exist_ok=True)

            # a. Concat scene segs → section raw video (video-only)
            raw_sec = sec_dir / "scenes_raw.mp4"
            _concat_c([seg_paths[i] for i in indices], raw_sec)

            # b. Concat section WAVs → section narration → mux into video
            sec_content = raw_sec
            narr_start  = narr_offsets[indices[0]] if indices else 0.0
            narr_end    = narr_start   # updated below

            # Primary: use pre-assembled section narration.wav (AI news layout)
            perm_narr = self.project_dir / "audio" / "sections" / label / "narration.wav"
            if perm_narr.exists() and indices:
                try:
                    with _wave.open(str(perm_narr), "rb") as wf2:
                        sec_narr_dur = wf2.getnframes() / float(wf2.getframerate())
                except Exception:
                    sec_narr_dur = sum(scene_durations[i] for i in indices)
                narr_end  = narr_start + sec_narr_dur
                vid_dur   = self._probe_duration(raw_sec)
                sec_muxed = sec_dir / "scenes_muxed.mp4"
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", str(raw_sec), "-i", str(perm_narr),
                    "-filter_complex",
                    f"[1:a]aresample=44100,"
                    f"atrim=end={vid_dur:.4f},asetpts=PTS-STARTPTS,"
                    f"apad=whole_dur={vid_dur:.4f}[aout]",
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-t", f"{vid_dur:.4f}", str(sec_muxed),
                ], capture_output=True, text=True, timeout=300)
                if sec_muxed.exists():
                    sec_content = sec_muxed
            elif audio_dir and indices:
                wav_list: List[Path] = []
                for i in indices:
                    try:
                        sid = int(image_files[i].stem.split("_")[1])
                    except Exception:
                        sid = i + 1
                    w = audio_dir / f"scene_{sid:03d}.wav"
                    if w.exists():
                        wav_list.append(w)

                if wav_list:
                    sec_narr = sec_dir / "narration.wav"
                    if len(wav_list) == 1:
                        _shutil.copy2(str(wav_list[0]), str(sec_narr))
                    else:
                        wf_list = sec_dir / "wav_list.txt"
                        wf_list.write_text(
                            "\n".join(f"file '{str(w).replace(chr(92), '/')}'"
                                      for w in wav_list),
                            encoding="utf-8",
                        )
                        subprocess.run(
                            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                             "-i", str(wf_list), "-c", "copy", str(sec_narr)],
                            capture_output=True, text=True, timeout=180,
                        )

                    if sec_narr.exists() and sec_narr.stat().st_size > 0:
                        try:
                            with _wave.open(str(sec_narr), "rb") as wf2:
                                sec_narr_dur = wf2.getnframes() / float(wf2.getframerate())
                        except Exception:
                            sec_narr_dur = sum(scene_durations[i] for i in indices)
                        narr_end   = narr_start + sec_narr_dur
                        vid_dur    = self._probe_duration(raw_sec)
                        sec_muxed  = sec_dir / "scenes_muxed.mp4"
                        subprocess.run([
                            "ffmpeg", "-y",
                            "-i", str(raw_sec), "-i", str(sec_narr),
                            "-filter_complex",
                            f"[1:a]aresample=44100,"
                            f"atrim=end={vid_dur:.4f},asetpts=PTS-STARTPTS,"
                            f"apad=whole_dur={vid_dur:.4f}[aout]",
                            "-map", "0:v:0", "-map", "[aout]",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                            "-t", f"{vid_dur:.4f}", str(sec_muxed),
                        ], capture_output=True, text=True, timeout=300)
                        if sec_muxed.exists():
                            sec_content = sec_muxed

            # c. Burn subtitles — prefer per-section SRT (AI news), fallback to global extraction
            if self.burn_subtitles and sec_content != raw_sec:
                perm_srt = self.project_dir / "subtitles" / "sections" / label / "subtitles.srt"
                srt_to_burn = None
                if perm_srt.exists():
                    srt_to_burn = perm_srt
                elif srt_entries and narr_end > narr_start:
                    extracted = self._extract_section_srt(
                        srt_entries, narr_start, narr_end, sec_dir / "section.srt"
                    )
                    if extracted:
                        srt_to_burn = extracted
                if srt_to_burn:
                    sub_out = sec_dir / "section_final.mp4"
                    ok = self._burn_subtitles_ffmpeg(sec_content, srt_to_burn, sub_out, codec)
                    if ok and sub_out.exists():
                        sec_content = sub_out

            # d. Assemble section part (prepend title card for story sections)
            if sec_type == "story" and story_num in card_clips:
                part = parts_dir / f"{part_num:02d}_story_{story_num:02d}.mp4"
                _concat_c([card_clips[story_num], sec_content], part)
            else:
                part = parts_dir / f"{part_num:02d}_{label}.mp4"
                _shutil.copy2(str(sec_content), str(part))

            ordered_parts.append(part)
            ordered_labels.append(label)
            self.logger.info("Part %02d: %s (%d scene(s))", part_num, label, len(indices))
            part_num += 1

            # Insert agenda card immediately after intro
            if sec_type == "intro" and intro_agenda:
                agenda_part = parts_dir / f"{part_num:02d}_agenda.mp4"
                _shutil.copy2(str(intro_agenda), str(agenda_part))
                ordered_parts.append(agenda_part)
                ordered_labels.append("agenda")
                self.logger.info("Part %02d: Today's Top 10 agenda card", part_num)
                part_num += 1

        # ── Save individual section clips + per-section audio & subtitles ──
        clips_out_dir = self.output_dir / "clips_ai_news"
        clips_out_dir.mkdir(exist_ok=True)
        for lbl, part_path in zip(ordered_labels, ordered_parts):
            _shutil.copy2(str(part_path), str(clips_out_dir / f"{lbl}.mp4"))
        self.logger.info("Saved %d AI News clips → clips_ai_news/", len(ordered_labels))
        for sec in sections:
            lbl     = f"story_{sec['story_num']:02d}" if sec["type"] == "story" else sec["type"]
            tmp_sec = sections_dir / lbl
            narr_w  = tmp_sec / "narration.wav"
            if narr_w.exists():
                perm_a = self.project_dir / "audio" / "sections" / lbl
                perm_a.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(narr_w), str(perm_a / "narration.wav"))
            sec_srt = tmp_sec / "section.srt"
            if sec_srt.exists():
                perm_s = self.project_dir / "subtitles" / "sections" / lbl
                perm_s.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(sec_srt), str(perm_s / "subtitles.srt"))

        # ── 5. Final merge ─────────────────────────────────────────────────
        _concat_c(ordered_parts, out)
        self.logger.info("AI News assembled: %d parts → %s", len(ordered_parts), out.name)

        # ── 6. Compute narrator-off intervals (title cards + agenda) ─────────
        # Title cards are the first 3s of every story_ part; agenda is its own part.
        no_nar_intervals: List[Tuple[float, float]] = []
        cursor = 0.0
        TITLE_CARD_DUR = 3.0   # matches _build_title_card_clip duration=3.0
        for lbl, part_path in zip(ordered_labels, ordered_parts):
            try:
                part_dur = self._probe_duration(part_path)
            except Exception:
                part_dur = 0.0
            if lbl == "agenda":
                no_nar_intervals.append((cursor, cursor + part_dur))
            elif lbl.startswith("story_"):
                card_end = cursor + min(TITLE_CARD_DUR, part_dur)
                no_nar_intervals.append((cursor, card_end))
            cursor += part_dur

        return out, no_nar_intervals

    def _build_hybrid_video(
        self,
        image_files: List[Path],
        clips_dir: Optional[Path],
        scene_durations: List[float],
        codec: str,
        audio_dir: Optional[Path] = None,
    ) -> Path:
        """Build raw video processing each scene independently.

        For each scene:
        - If clips_dir/scene_NNN.mp4 exists (generated or user-uploaded replacement):
            trim to scene duration if the clip is longer, then encode to standard resolution.
        - Otherwise: generate a static image segment for the scene duration.

        If audio_dir is provided, each video segment is immediately muxed with its
        per-scene WAV (scene_NNN.wav) so narration is frame-accurately aligned —
        no drift accumulates across scenes.
        """
        out = self.output_dir / "_raw_video.mp4"
        segments_dir = self.output_dir / "_segments"
        trimmed_dir  = self.output_dir / "_trimmed_clips"
        muxed_dir    = self.output_dir / "_muxed_segments"
        segments_dir.mkdir(exist_ok=True)
        trimmed_dir.mkdir(exist_ok=True)
        muxed_dir.mkdir(exist_ok=True)

        segment_files: List[Path] = []
        animations = self.template_cfg.get("animations", ["none"])
        has_animation = any(a != "none" for a in animations)
        scenes_meta = self._load_scenes_json() if has_animation else []
        total_scenes = len(image_files)

        for idx, (img_file, duration) in enumerate(zip(image_files, scene_durations)):
            try:
                scene_id = int(img_file.stem.split("_")[1])
            except (IndexError, ValueError):
                scene_id = idx + 1

            seg_out = segments_dir / f"seg_{idx:03d}.mp4"

            # Report per-scene progress (5%–75% range) so the frontend doesn't appear frozen.
            scene_pct = 5 + (idx / total_scenes) * 70
            self.logger.info(
                "Scene %d/%d (id=%d, %.1fs): starting encode...",
                idx + 1, total_scenes, scene_id, duration,
            )
            if self.progress_callback and not asyncio.iscoroutinefunction(self.progress_callback):
                try:
                    self.progress_callback(
                        scene_pct,
                        f"Rendering scene {idx + 1}/{total_scenes}…",
                        {},
                    )
                except Exception:
                    pass

            # ── encode video-only segment ──────────────────────────────
            clip_path: Optional[Path] = None
            if clips_dir and clips_dir.exists():
                candidate = clips_dir / f"scene_{scene_id:03d}.mp4"
                if candidate.exists():
                    clip_path = candidate

            encoded = False
            if clip_path:
                clip_dur = self._probe_duration(clip_path)
                if clip_dur > duration + 0.05:
                    clip_path = self._trim_clip(clip_path, duration, trimmed_dir)
                    clip_dur = duration

                needs_loop = clip_dur < duration - 0.05
                cmd = [
                    "ffmpeg", "-y",
                    *(["-stream_loop", "-1"] if needs_loop else []),
                    "-i", str(clip_path),
                    "-t", f"{duration:.4f}",
                    "-vf", f"scale={self.width}:{self.height}:flags=lanczos,fps={self.fps},setsar=1",
                    *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
                    str(seg_out),
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if r.returncode == 0:
                    self.logger.info(f"Scene {scene_id}: clip → {seg_out.name} ({duration:.2f}s)")
                    encoded = True
                else:
                    self.logger.warning(
                        f"Scene {scene_id}: clip encode failed ({r.stderr[-120:]}), falling back to image"
                    )

            if not encoded:
                if has_animation:
                    meta = scenes_meta[idx] if idx < len(scenes_meta) else {}
                    style = self._analyze_scene_style(meta, idx, animations)
                    n_frames = max(1, int(round(duration * self.fps)))
                    vf = self._build_zoompan_vf(style["anim"], n_frames)
                    # Allow ~6× real-time for zoompan on CPU; NVENC is faster.
                    seg_timeout = max(120, int(duration * 6))
                else:
                    vf = f"scale={self.width}:{self.height}:flags=lanczos,setsar=1"
                    seg_timeout = max(60, int(duration * 4))
                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", str(img_file),
                    "-vf", vf,
                    "-t", f"{duration:.4f}", "-r", str(self.fps),
                    *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
                    str(seg_out),
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=seg_timeout)
                if r.returncode != 0:
                    raise ServiceError(
                        self.service_name,
                        f"Image segment failed for scene {scene_id}: {r.stderr[-200:]}",
                    )
                self.logger.info(
                    f"Scene {scene_id}: image ({'animated' if has_animation else 'static'}) → {seg_out.name}"
                )

            # ── mux video segment with per-scene WAV ───────────────────
            # This ensures narration is locked to the exact video frames —
            # no drift even if FPS rounding makes each segment slightly short.
            final_seg = seg_out
            if audio_dir:
                wav_path = audio_dir / f"scene_{scene_id:03d}.wav"
                if wav_path.exists():
                    muxed_out = muxed_dir / f"mux_{idx:03d}.mp4"
                    mux_cmd = [
                        "ffmpeg", "-y",
                        "-i", str(seg_out),
                        "-i", str(wav_path),
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "128k",
                        "-shortest",  # end when shorter of video/audio ends
                        str(muxed_out),
                    ]
                    mr = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=120)
                    if mr.returncode == 0:
                        final_seg = muxed_out
                    else:
                        self.logger.warning(
                            f"Scene {scene_id}: per-scene WAV mux failed — audio may drift"
                        )

            self.logger.info(
                "Scene %d/%d done → %s (audio=%s)",
                idx + 1, total_scenes, final_seg.name, final_seg != seg_out,
            )
            segment_files.append(final_seg)

        # Concatenate all segments (uniform codec/resolution — stream copy is safe)
        concat_file = self.output_dir / "_hybrid_concat.txt"
        lines = [f"file '{str(s).replace(chr(92), '/')}'" for s in segment_files]
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        concat_file.unlink(missing_ok=True)
        if r.returncode != 0:
            raise ServiceError(self.service_name, f"Hybrid concat failed: {r.stderr[-300:]}")
        return out

    def _get_scene_target_duration(self, scene_id: int, clip_index: int) -> Optional[float]:
        """Return the target duration for a scene clip.

        Resolution order:
        1. Individual WAV file (most accurate — actual TTS output length)
        2. scenes.json entry matched by scene_id
        3. scenes.json entry matched by clip sort-order index (covers uploaded clips
           where scene_id in the filename may not match the JSON)
        """
        audio_dir = self.project_dir / "audio"
        wav_path = audio_dir / f"scene_{scene_id:03d}.wav"
        if wav_path.exists():
            try:
                with wave.open(str(wav_path), "rb") as wf:
                    return wf.getnframes() / wf.getframerate()
            except Exception:
                pass

        scenes = self._load_scenes_json()

        # Match by scene_id field
        for s in scenes:
            raw_sid = s.get("scene_id") or s.get("id")
            try:
                if raw_sid is not None and int(raw_sid) == scene_id:
                    dur = s.get("duration")
                    if dur:
                        return float(dur)
            except (ValueError, TypeError):
                pass

        # Positional fallback — user-uploaded clip at index N maps to scene N
        if 0 <= clip_index < len(scenes):
            dur = scenes[clip_index].get("duration")
            if dur:
                return float(dur)

        return None

    def _trim_clip(self, clip: Path, max_dur: float, trimmed_dir: Path) -> Path:
        """Return clip trimmed to max_dur seconds (re-encoded for frame accuracy)."""
        trimmed = trimmed_dir / clip.name
        cmd = [
            "ffmpeg", "-y",
            "-i", str(clip),
            "-t", f"{max_dur:.6f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-an",
            str(trimmed),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            self.logger.info(f"Trimmed {clip.name} to {max_dur:.3f}s")
            return trimmed
        self.logger.warning(f"Trim failed for {clip.name}: {r.stderr[-200:]}")
        return clip

    def _concat_clips(self, clips: List[Path], codec: str) -> Path:
        """Concatenate animated clips into a single raw video.

        Every clip that exceeds its scene target duration is pre-trimmed before
        concatenation. User-uploaded replacements are covered via positional
        fallback even when WAV files are absent.
        """
        out = self.output_dir / "_raw_video.mp4"
        concat_file = self.output_dir / "_clips_concat.txt"
        trimmed_dir = self.output_dir / "_trimmed_clips"
        trimmed_dir.mkdir(exist_ok=True)

        ready_clips: List[Path] = []
        for idx, clip in enumerate(clips):
            target = clip
            try:
                scene_id = int(clip.stem.split("_")[1])
            except (IndexError, ValueError):
                scene_id = idx + 1

            target_dur = self._get_scene_target_duration(scene_id, idx)
            if target_dur is not None:
                clip_dur = self._probe_duration(clip)
                if clip_dur > target_dur + 0.05:
                    target = self._trim_clip(clip, target_dur, trimmed_dir)
            else:
                self.logger.warning(
                    f"{clip.name}: no target duration found — using clip as-is ({self._probe_duration(clip):.2f}s)"
                )
            ready_clips.append(target)

        lines = [
            f"file '{str(c).replace(chr(92), '/')}'"
            for c in ready_clips
        ]
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-vf", f"scale={self.width}:{self.height}:flags=lanczos,fps={self.fps},setsar=1",
            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        concat_file.unlink(missing_ok=True)
        if r.returncode != 0:
            raise ServiceError(self.service_name, f"Clip concat failed: {r.stderr[-300:]}")
        return out

    def _slideshow_single(self, img: Path, duration: float, out: Path, codec: str) -> Path:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img),
            "-vf", f"scale={self.width}:{self.height}:flags=lanczos,setsar=1",
            "-t", f"{duration:.4f}", "-r", str(self.fps),
            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise ServiceError(self.service_name, f"Slideshow failed: {r.stderr[-300:]}")
        return out

    def _slideshow_cut(
        self, images: List[Path], durations: List[float], out: Path, codec: str
    ) -> Path:
        """Concat-demuxer slideshow — instant cuts between images."""
        concat_file = self.output_dir / "_concat_list.txt"
        lines: List[str] = []
        for img, dur in zip(images, durations):
            lines.append(f"file '{str(img).replace(chr(92), '/')}'")
            lines.append(f"duration {dur:.4f}")
        # Repeat last image — FFmpeg concat demuxer requires this to flush the
        # last frame's duration before EOF.
        lines.append(f"file '{str(images[-1]).replace(chr(92), '/')}'")
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-vf", f"scale={self.width}:{self.height}:flags=lanczos,fps={self.fps},setsar=1",
            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        concat_file.unlink(missing_ok=True)
        if r.returncode != 0:
            raise ServiceError(self.service_name, f"Slideshow (cut) failed: {r.stderr[-400:]}")
        return out

    def _slideshow_xfade(
        self, images: List[Path], durations: List[float], out: Path, codec: str
    ) -> Path:
        """Crossfade slideshow using FFmpeg xfade filter directly on images."""
        td = self.transition_duration
        W, H, fps = self.width, self.height, self.fps
        n = len(images)

        # One -loop 1 -t duration -i image per scene
        inputs: List[str] = []
        for img, dur in zip(images, durations):
            inputs += ["-loop", "1", "-t", f"{dur:.4f}", "-i", str(img)]

        # Scale each input stream to a consistent size/fps
        parts: List[str] = []
        for i in range(n):
            parts.append(
                f"[{i}:v]scale={W}:{H}:flags=lanczos,fps={fps},setsar=1[s{i}]"
            )

        # Chain xfade filters
        cumsum = 0.0
        for i in range(n - 1):
            cumsum += durations[i]
            offset = max(cumsum - (i + 1) * td, 0.01)
            src0 = f"[s{i}]"   if i == 0     else f"[xf{i}]"
            src1 = f"[s{i + 1}]"
            dst  = "[vout]"    if i == n - 2 else f"[xf{i + 1}]"
            parts.append(
                f"{src0}{src1}xfade=transition=fade:duration={td:.3f}:offset={offset:.3f}{dst}"
            )

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", ";".join(parts),
            "-map", "[vout]",
            *self._codec_args(codec), "-pix_fmt", "yuv420p", "-an",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            self.logger.warning(f"xfade failed, falling back to cut: {r.stderr[-200:]}")
            return self._slideshow_cut(images, durations, out, codec)
        return out

    # ------------------------------------------------------------------
    # Animated slideshow helpers (PIL pipe)
    # ------------------------------------------------------------------
    def _prescale_for_anim(self, img, anim: str):
        """Pre-scale a PIL Image once for the given animation type.

        Returns (scaled, sw, sh, dW, dH) where dW/dH are the extra pixels
        beyond (W, H) that the animation will consume.
        """
        from PIL import Image as PILImage
        W, H, z = self.width, self.height, self.zoom_amount
        z2       = z * 0.5
        ZW,  ZH  = round(W * (1 + z)),   round(H * (1 + z))
        ZW2, ZH2 = round(W * (1 + z2)),  round(H * (1 + z2))
        PW,  PH  = round(W * 1.20),      round(H * 1.20)

        # Composite animations render from a W×H canvas — no extra border needed
        composite_anims = {
            "slide_in_left", "slide_in_right", "slide_in_up", "slide_in_down", "zoom_burst",
        }
        pan_anims = {
            "pan_right", "pan_left", "pan_up", "pan_down",
            "drift_right", "drift_left",
            "tilt_up", "tilt_down", "push_left", "push_right",
        }
        slow_anims = {"slow_zoom_in", "slow_zoom_out"}

        if anim in composite_anims:
            scaled = img.resize((W, H), PILImage.LANCZOS)
            return scaled, W, H, 0, 0

        if anim in pan_anims:
            scaled = img.resize((PW, PH), PILImage.LANCZOS)
        elif anim in slow_anims:
            scaled = img.resize((ZW2, ZH2), PILImage.LANCZOS)
        elif z > 0 and anim != "none":
            scaled = img.resize((ZW, ZH), PILImage.LANCZOS)
        else:
            scaled = img.resize((W, H), PILImage.LANCZOS)

        sw, sh = scaled.size
        return scaled, sw, sh, sw - W, sh - H

    def _anim_frame(self, scaled, anim: str, p: float,
                    W: int, H: int, sw: int, sh: int, dW: int, dH: int):
        """Return one W×H PIL Image at smoothstepped animation progress p ∈ [0, 1]."""
        from PIL import Image as PILImage
        p = p * p * (3.0 - 2.0 * p)  # smoothstep easing

        if anim == "none":
            return scaled  # already (W, H) from _prescale_for_anim
        elif anim in ("zoom_in", "slow_zoom_in"):
            cw = round(sw - dW * p); ch = round(sh - dH * p)
            x  = round(dW / 2 * p);  y  = round(dH / 2 * p)
        elif anim in ("zoom_out", "slow_zoom_out"):
            cw = round(W + dW * p);  ch = round(H + dH * p)
            x  = round(dW / 2 * (1 - p)); y = round(dH / 2 * (1 - p))
        elif anim == "pan_right":
            cw, ch = W, H; x = round(dW * p);       y = dH // 2
        elif anim == "pan_left":
            cw, ch = W, H; x = round(dW * (1 - p)); y = dH // 2
        elif anim == "pan_up":
            cw, ch = W, H; x = dW // 2; y = round(dH * (1 - p))
        elif anim == "pan_down":
            cw, ch = W, H; x = dW // 2; y = round(dH * p)
        elif anim == "zoom_in_pan_right":
            cw = round(sw - dW * p); ch = round(sh - dH * p)
            x  = round(dW * p);      y  = round((sh - ch) / 2)
        elif anim == "zoom_in_pan_left":
            cw = round(sw - dW * p); ch = round(sh - dH * p)
            x  = round(dW * (1 - p)); y = round((sh - ch) / 2)
        elif anim == "zoom_out_pan_right":
            cw = round(W + dW * p); ch = round(H + dH * p)
            x  = round(dW / 2 * (1 - p)); y = round((sh - ch) / 2)
        elif anim == "zoom_out_pan_left":
            cw = round(W + dW * p); ch = round(H + dH * p)
            x  = round(dW / 2 * p); y = round((sh - ch) / 2)
        elif anim == "zoom_in_pan_up":
            # Zoom in while ending on the top portion of the image
            cw = round(sw - dW * p); ch = round(sh - dH * p)
            x  = round((sw - cw) / 2); y = 0
        elif anim == "zoom_in_pan_down":
            # Zoom in while drifting toward the bottom
            cw = round(sw - dW * p); ch = round(sh - dH * p)
            x  = round((sw - cw) / 2); y = round(dH * p)
        elif anim == "diagonal_zoom_in":
            # Zoom in while moving toward bottom-right
            cw = round(sw - dW * p); ch = round(sh - dH * p)
            x  = round(dW * 0.7 * p); y = round(dH * 0.7 * p)
        elif anim == "diagonal_zoom_out":
            # Zoom out while starting from bottom-right
            cw = round(W + dW * p); ch = round(H + dH * p)
            x  = round(dW * 0.3 * (1 - p)); y = round(dH * 0.3 * (1 - p))
        elif anim == "drift_right":
            # Subtle slow drift right — uses pan canvas but only 25% of travel range
            cw, ch = W, H
            x = round(dW * (0.375 + 0.25 * p)); y = dH // 2
        elif anim == "drift_left":
            # Subtle slow drift left — uses pan canvas but only 25% of travel range
            cw, ch = W, H
            x = round(dW * (0.625 - 0.25 * p)); y = dH // 2
        elif anim == "tilt_up":
            # Slow upward camera tilt — pans from bottom toward top of image
            cw, ch = W, H
            x = dW // 2; y = round(dH * (1 - p))
        elif anim == "tilt_down":
            # Slow downward camera tilt — pans from top toward bottom of image
            cw, ch = W, H
            x = dW // 2; y = round(dH * p)
        elif anim == "push_left":
            # Aggressive pan left across 75% of the canvas
            cw, ch = W, H
            x = round(dW * (0.8 - 0.75 * p)); y = dH // 2
        elif anim == "push_right":
            # Aggressive pan right across 75% of the canvas
            cw, ch = W, H
            x = round(dW * (0.2 + 0.75 * p)); y = dH // 2
        elif anim == "zoom_burst":
            # Starts very zoomed in, quickly zooms out to full frame
            start_f  = 0.55
            fraction = start_f + (1.0 - start_f) * p
            cw = round(W * fraction); ch = round(H * fraction)
            x  = (W - cw) // 2;      y  = (H - ch) // 2
            frame = scaled.crop((max(0, x), max(0, y), min(W, x + cw), min(H, y + ch)))
            return frame.resize((W, H), PILImage.LANCZOS)
        elif anim == "slide_in_left":
            # Image slides in from the left edge (off-screen → on-screen)
            offset = int(W * (p - 1.0))
            canvas = PILImage.new("RGB", (W, H), 0)
            src_x  = max(0, -offset); dst_x = max(0, offset)
            vis_w  = min(W - src_x, W - dst_x)
            if vis_w > 0:
                canvas.paste(scaled.crop((src_x, 0, src_x + vis_w, H)), (dst_x, 0))
            return canvas
        elif anim == "slide_in_right":
            # Image slides in from the right edge
            offset = int(W * (1.0 - p))
            canvas = PILImage.new("RGB", (W, H), 0)
            vis_w  = W - offset
            if vis_w > 0:
                canvas.paste(scaled.crop((0, 0, vis_w, H)), (offset, 0))
            return canvas
        elif anim == "slide_in_up":
            # Image slides in from the top edge
            offset = int(H * (p - 1.0))
            canvas = PILImage.new("RGB", (W, H), 0)
            src_y  = max(0, -offset); dst_y = max(0, offset)
            vis_h  = min(H - src_y, H - dst_y)
            if vis_h > 0:
                canvas.paste(scaled.crop((0, src_y, W, src_y + vis_h)), (0, dst_y))
            return canvas
        elif anim == "slide_in_down":
            # Image slides in from the bottom edge
            offset = int(H * (1.0 - p))
            canvas = PILImage.new("RGB", (W, H), 0)
            vis_h  = H - offset
            if vis_h > 0:
                canvas.paste(scaled.crop((0, 0, W, vis_h)), (0, offset))
            return canvas
        else:
            cw = round(sw - dW * p); ch = round(sh - dH * p)
            x  = round(dW / 2 * p); y  = round(dH / 2 * p)

        x  = max(0, min(x,  sw - max(cw, 1)))
        y  = max(0, min(y,  sh - max(ch, 1)))
        cw = max(1, min(cw, sw - x))
        ch = max(1, min(ch, sh - y))

        frame = scaled.crop((x, y, x + cw, y + ch))
        return frame.resize((W, H), PILImage.LANCZOS) if frame.size != (W, H) else frame

    def _slideshow_animated(
        self, images: List[Path], durations: List[float], out: Path, codec: str
    ) -> Path:
        """Ken Burns animated slideshow with per-scene CapCut-style effects.

        Each scene is analyzed against SCENE_STYLE_RULES to select the best
        animation, color grade, frame effect, and transition for that scene's
        content. Falls back to the template defaults when no keywords match.
        """
        from PIL import Image as PILImage

        W, H       = self.width, self.height
        fps        = self.fps
        td         = self.transition_duration
        n_scenes   = len(images)
        animations = self.template_cfg.get("animations", ["zoom_in"])

        vignette_strength = float(self.template_cfg.get("vignette", 0.0))
        vignette_mask     = self._make_vignette(W, H, vignette_strength) if vignette_strength > 0 else None
        black_vignette    = PILImage.new("RGB", (W, H), 0) if vignette_mask else None

        scenes_meta = self._load_scenes_json()
        self.logger.info(
            f"Animated slideshow: {n_scenes} scenes | zoom={self.zoom_amount:.2f} "
            f"| vignette={vignette_strength:.2f} | per-scene styles active"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(fps),
            "-i", "pipe:0",
            *self._codec_args(codec),
            "-pix_fmt", "yuv420p", "-an",
            str(out),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            last_frame: Optional[Any] = None

            for i, (img_path, duration) in enumerate(zip(images, durations)):
                meta  = scenes_meta[i] if i < len(scenes_meta) else {}
                style = self._analyze_scene_style(meta, i, animations)

                anim             = style["anim"]
                grade            = style["grade"]
                effect           = style.get("effect")
                scene_transition = style.get("transition",
                                             self.template_cfg.get("transition", "crossfade"))

                trans_frames = int(round(td * fps)) if scene_transition != "cut" else 0
                is_last      = (i == n_scenes - 1)
                n_total      = max(1, int(round(duration * fps)))
                n_content    = n_total if is_last else max(1, n_total - trans_frames)

                self.logger.debug(
                    f"  Scene {i+1}/{n_scenes}: anim={anim} grade={grade} "
                    f"effect={effect} trans={scene_transition} frames={n_content}"
                )

                img = PILImage.open(img_path).convert("RGB")
                img = self._apply_color_grade(img, grade)
                scaled, sw, sh, dW, dH = self._prescale_for_anim(img, anim)

                leak_ov = self._make_light_leak_overlay(W, H) if effect == "light_leak" else None

                # ── Transition blend from previous scene ───────────────
                if last_frame is not None and trans_frames > 0:
                    first_f = self._anim_frame(scaled, anim, 0.0, W, H, sw, sh, dW, dH)
                    first_f = self._apply_frame_effect(first_f, effect, leak_ov,
                                                       vignette_mask, black_vignette)
                    for k in range(trans_frames):
                        alpha   = (k + 1) / (trans_frames + 1)
                        blended = self._transition_frame(last_frame, first_f, alpha, scene_transition)
                        proc.stdin.write(blended.tobytes())

                # ── Content frames for this scene ──────────────────────
                for n in range(n_content):
                    p     = n / max(n_content - 1, 1)
                    frame = self._anim_frame(scaled, anim, p, W, H, sw, sh, dW, dH)
                    frame = self._apply_frame_effect(frame, effect, leak_ov,
                                                     vignette_mask, black_vignette)
                    if n == n_content - 1:
                        last_frame = frame
                    proc.stdin.write(frame.tobytes())

            proc.stdin.close()
            _, stderr_data = proc.communicate(timeout=600)

        except Exception as exc:
            proc.kill()
            raise ServiceError(self.service_name, f"Animated slideshow pipe failed: {exc}")

        if proc.returncode != 0:
            raise ServiceError(
                self.service_name,
                f"Animated slideshow failed: "
                f"{stderr_data.decode('utf-8', errors='replace')[-500:]}"
            )
        return out

    # ------------------------------------------------------------------
    # Stage 3 — audio mixing
    # ------------------------------------------------------------------
    def _add_audio(
        self,
        video_path: Path,
        narration_path: Optional[Path],
        music_path: Optional[Path],
    ) -> Path:
        if not narration_path and not music_path:
            return video_path

        out = self.output_dir / "_with_audio.mp4"
        narr_vol  = self.template_cfg.get("narration_volume", 1.0)
        music_vol = self.template_cfg.get("music_volume", 0.12)

        if narration_path and not music_path:
            narr_dur = self._probe_duration(narration_path)
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(narration_path),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", self.audio_codec, "-b:a", self.audio_bitrate,
                "-t", f"{narr_dur:.3f}",  # trim output to exact narration length
                str(out),
            ]

        elif narration_path and music_path:
            narr_dur = self._probe_duration(narration_path)  # narration defines length
            fc = (
                f"[1:a]volume={narr_vol}[narr];"
                f"[2:a]volume={music_vol},"
                f"aloop=loop=-1:size=2147483647,"
                f"atrim=duration={narr_dur:.3f}[music];"
                "[narr][music]amix=inputs=2:duration=first:dropout_transition=3[aout]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(narration_path),
                "-i", str(music_path),
                "-filter_complex", fc,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", self.audio_codec, "-b:a", self.audio_bitrate,
                "-t", f"{narr_dur:.3f}",  # trim output to exact narration length
                str(out),
            ]

        else:  # music only — but video may already have per-scene narration embedded
            vid_dur = self._probe_duration(video_path)
            # Detect whether the video has an audio stream (per-scene narration)
            probe_r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video_path)],
                capture_output=True, text=True,
            )
            has_embedded_audio = "audio" in probe_r.stdout

            if has_embedded_audio:
                # Mix background music under the already-embedded narration
                fc = (
                    f"[0:a]volume={narr_vol}[narr];"
                    f"[1:a]volume={music_vol},"
                    f"aloop=loop=-1:size=2147483647,"
                    f"atrim=duration={vid_dur:.3f}[music];"
                    "[narr][music]amix=inputs=2:duration=first:dropout_transition=3[aout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(music_path),
                    "-filter_complex", fc,
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", self.audio_codec, "-b:a", self.audio_bitrate,
                    str(out),
                ]
            else:
                # Silent video — add looped music track
                fc = (
                    f"[1:a]volume={music_vol},"
                    f"aloop=loop=-1:size=2147483647,"
                    f"atrim=duration={vid_dur:.3f}[aout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(music_path),
                    "-filter_complex", fc,
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", self.audio_codec, "-b:a", self.audio_bitrate,
                    "-shortest",
                    str(out),
                ]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            self.logger.error(f"Audio mix failed: {r.stderr[-300:]}")
            return video_path  # Degrade gracefully — video without audio
        return out

    def _probe_duration(self, path: Path) -> float:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 str(path)],
                capture_output=True, text=True, timeout=30,
            )
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Stage 4 — subtitle burning (unchanged logic)
    # ------------------------------------------------------------------
    def _burn_subtitles_ffmpeg(
        self, input_path: Path, srt_path: Path, output_path: Path, codec: str = "libx264"
    ) -> bool:
        import tempfile as _tempfile
        import shutil as _shutil_sub
        style_map = {
            "bottom_white":  "Fontsize=22,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Alignment=2",
            "bottom_yellow": "Fontsize=22,PrimaryColour=&H00ffff,OutlineColour=&H000000,Outline=2,Alignment=2",
            "lower_third":   "Fontsize=20,PrimaryColour=&Hffffff,BackColour=&H80000000,Alignment=2,BorderStyle=4",
        }
        style_name = self.template_cfg.get("subtitle_style", "bottom_white")
        style_str  = style_map.get(style_name, style_map["bottom_white"])
        # FFmpeg subtitles filter fails on paths with spaces; copy to a temp dir first
        _tmp_srt_dir = None
        srt_use = srt_path
        if " " in str(srt_path):
            _tmp_srt_dir = Path(_tempfile.mkdtemp())
            srt_use = _tmp_srt_dir / "sub.srt"
            _shutil_sub.copy2(str(srt_path), str(srt_use))
        srt_esc = str(srt_use).replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"subtitles='{srt_esc}':force_style='{style_str}'",
            *self._codec_args(codec),
            "-c:a", "copy",
            str(output_path),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                self.logger.info(f"Subtitles burned → {output_path}")
                return True
            self.logger.error(f"Subtitle burn failed:\n{r.stderr[-1000:]}")
            return False
        except subprocess.TimeoutExpired:
            self.logger.error("Subtitle burn timed out")
            return False
        except FileNotFoundError:
            self.logger.error("ffmpeg not found")
            return False
        finally:
            if _tmp_srt_dir:
                _shutil_sub.rmtree(str(_tmp_srt_dir), ignore_errors=True)

    # ------------------------------------------------------------------
    # Narrator overlay (Stage 2.5)
    # ------------------------------------------------------------------
    def _find_narrator_clips(self) -> List[Path]:
        """Return narrator clips, preferring *_nobg.webm (alpha) over raw .mp4."""
        def _prefer_nobg(clips: List[Path]) -> List[Path]:
            result = []
            for c in clips:
                nobg = c.parent / f"{c.stem}_nobg.webm"
                result.append(nobg if nobg.exists() else c)
            return result

        project_nar = self.project_dir / "narrator"
        if project_nar.exists():
            clips = sorted(project_nar.glob("*.mp4"))
            if clips:
                return _prefer_nobg(clips)
        if self.narrator_enabled and self.narrator_clips_dir:
            d = Path(self.narrator_clips_dir)
            if d.exists():
                clips = sorted(d.glob("*.mp4"))
                if clips:
                    return _prefer_nobg(clips)
        return []

    def _compute_silent_intervals(self, audio_dir: Path) -> List[tuple]:
        """Return [(start_sec, end_sec), ...] for every scene whose narration is empty.

        Uses scenes.json to identify empty-narration scenes and per-scene WAV
        durations to compute their time offsets in the assembled video.
        """
        scenes_list = self._load_scenes_json()
        silent_intervals: List[tuple] = []
        cursor = 0.0

        for s in scenes_list:
            raw_sid = s.get("scene_id") or s.get("id")
            try:
                sid = int(str(raw_sid).replace("scene_", ""))
            except (TypeError, ValueError):
                sid = -1

            wav = audio_dir / f"scene_{sid:03d}.wav"
            if wav.exists():
                try:
                    dur = wave.open(str(wav), "rb")
                    duration = dur.getnframes() / float(dur.getframerate())
                    dur.close()
                except Exception:
                    duration = float(s.get("duration", 5))
            else:
                duration = float(s.get("duration", 5))

            narration = s.get("narration", "").strip()
            if not narration:
                silent_intervals.append((cursor, cursor + duration))

            cursor += duration

        return silent_intervals

    def _add_narrator_overlay(self, video_path: Path, clips: List[Path], silent_intervals: Optional[List[tuple]] = None) -> Path:
        """Composite narrator clips as a looped PiP overlay on the video.

        Only the video stream from narrator clips is used; audio stays from
        the main video (TTS narration + background music already mixed in).
        """
        out = self.output_dir / "_with_narrator.mp4"
        vid_dur = self._probe_duration(video_path)
        if vid_dur <= 0:
            return video_path

        total_nar_dur = sum(self._probe_duration(c) for c in clips)
        if total_nar_dur <= 0:
            return video_path

        # Detect whether the clips have an alpha channel (background removed WebM)
        has_alpha = any(c.suffix.lower() == ".webm" for c in clips)

        # Resolve display size early — needed for pre-processing and filtergraph.
        w = self.narrator_width
        is_circle = self.narrator_shape == "circle"

        # Pre-normalize each narrator clip to a consistent resolution before
        # passing them to the concat demuxer. The concat demuxer requires all
        # input streams to have identical parameters (including width/height).
        # When clips have different resolutions, the demuxer stops after the
        # first file, truncating the narrator loop to a few seconds and then
        # cutting the entire output video via the overlay's shortest=1 flag.
        if is_circle:
            pre_vf = f"crop=min(iw\\,ih):min(iw\\,ih),scale={w}:{w}:flags=lanczos"
        else:
            pre_vf = f"scale={w}:-2:flags=lanczos"
        proc_dir = self.output_dir / "_narrator_proc"
        proc_dir.mkdir(exist_ok=True)
        processed_clips: List[Path] = []
        for idx, clip in enumerate(clips):
            proc_out = proc_dir / f"proc_{idx:03d}.mp4"
            pr = subprocess.run(
                ["ffmpeg", "-y", "-i", str(clip),
                 "-vf", pre_vf,
                 "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an",
                 str(proc_out)],
                capture_output=True, text=True, timeout=120,
            )
            processed_clips.append(proc_out if pr.returncode == 0 else clip)

        # Repeat processed clips enough times to cover the full video duration
        repeats = max(1, int(vid_dur / total_nar_dur) + 2)
        concat_path = self.output_dir / "_narrator_concat.txt"
        lines: List[str] = []
        for _ in range(repeats):
            for clip in processed_clips:
                lines.append(f"file '{str(clip).replace(chr(92), '/')}'")
        concat_path.write_text("\n".join(lines), encoding="utf-8")

        # Build looped narrator video — clips are now all the same resolution
        nar_loop = self.output_dir / ("_narrator_looped.webm" if has_alpha else "_narrator_looped.mp4")
        if has_alpha:
            loop_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_path),
                "-t", f"{vid_dur + 2:.3f}",
                "-vf", f"fps={self.fps}",
                "-c:v", "libvpx-vp9",
                "-auto-alt-ref", "0",
                "-pix_fmt", "yuva420p",
                "-b:v", "0", "-crf", "23",
                "-an",
                str(nar_loop),
            ]
        else:
            loop_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_path),
                "-t", f"{vid_dur + 2:.3f}",
                "-vf", f"fps={self.fps}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-an",
                str(nar_loop),
            ]
        r = subprocess.run(loop_cmd, capture_output=True, text=True, timeout=600)
        concat_path.unlink(missing_ok=True)
        import shutil as _shutil
        _shutil.rmtree(proc_dir, ignore_errors=True)
        if r.returncode != 0:
            self.logger.warning(f"Narrator loop creation failed: {r.stderr[-300:]}")
            return video_path

        # Overlay position
        m = self.narrator_margin
        b = self.narrator_bottom_margin
        pos_map = {
            "bottom_right": (f"main_w-overlay_w-{m}", f"main_h-overlay_h-{b}"),
            "bottom_left":  (str(m),                   f"main_h-overlay_h-{b}"),
            "top_right":    (f"main_w-overlay_w-{m}",  str(m)),
            "top_left":     (str(m),                    str(m)),
        }
        ox, oy = pos_map.get(self.narrator_position, pos_map["bottom_right"])

        if is_circle:
            # Loop is already cropped to square and scaled to w×w.
            # Just apply the circular alpha mask before compositing.
            alpha_src = "alpha(X\\,Y)" if has_alpha else "255"
            geq = (
                f"geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':"
                f"a='if(lte(hypot(X-W/2\\,Y-H/2)\\,min(W\\,H)/2)\\,{alpha_src}\\,0)'"
            )
            nar_scale = (
                f"[1:v]format=rgba,"
                f"{geq},"
                f"format=yuva420p[nar]"
            )
        else:
            # Rectangle — loop is already scaled to w×-2
            nar_scale = (
                f"[1:v]format=yuva420p[nar]"
                if has_alpha
                else f"[1:v]scale={w}:-2[nar]"
            )

        # Build enable expression: hide narrator during silent (no-narration) scenes.
        if silent_intervals:
            # FFmpeg enable uses 'between(t,s,e)' — combine with '+' (OR) then negate.
            between_parts = "+".join(
                f"between(t,{s:.3f},{e:.3f})" for s, e in silent_intervals
            )
            enable_expr = f":enable='not({between_parts})'"
        else:
            enable_expr = ""

        fc = f"{nar_scale};[0:v][nar]overlay={ox}:{oy}:shortest=1{enable_expr}"

        codec = self._pick_codec()
        overlay_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(nar_loop),
            "-filter_complex", fc,
            "-map", "0:a?",
            *self._codec_args(codec),
            "-pix_fmt", "yuv420p",
            "-t", f"{vid_dur:.3f}",
            str(out),
        ]
        r = subprocess.run(overlay_cmd, capture_output=True, text=True, timeout=600)
        nar_loop.unlink(missing_ok=True)

        if r.returncode != 0:
            self.logger.warning(f"Narrator overlay failed: {r.stderr[-400:]}")
            return video_path

        self.logger.info(f"Narrator overlay ({self.narrator_position}, {self.narrator_width}px) → {out}")
        return out

    # ------------------------------------------------------------------
    # Story number overlay (Stage 2.9) — AI News only
    # ------------------------------------------------------------------
    def _make_story_badge(self, num: int, size: int, out_path: Path) -> None:
        """Render a transparent PNG circle badge with the story number."""
        from PIL import Image as PILImage, ImageDraw, ImageFont

        img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Drop-shadow circle (offset 3px)
        s = 5
        draw.ellipse([s, s, size - 1, size - 1], fill=(0, 0, 0, 130))

        # Amber filled circle
        m = 4
        draw.ellipse([m, m, size - s - 1, size - s - 1], fill=(255, 176, 0, 235))

        # Dark border
        draw.ellipse([m, m, size - s - 1, size - s - 1],
                     outline=(20, 20, 20, 180), width=3)

        # Number text — try bold system fonts, fall back to PIL default
        text = str(num)
        font_size = int(size * 0.44)
        font = None
        for face in (
            "arialbd.ttf", "Arial Bold.ttf", "Arial_Bold.ttf",
            "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
        ):
            try:
                font = ImageFont.truetype(face, font_size)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()

        # Centre text within the circle area
        circle_cx = (m + size - s - 1) / 2
        circle_cy = (m + size - s - 1) / 2
        bbox = draw.textbbox((0, 0), text, font=font)
        tx = circle_cx - (bbox[2] - bbox[0]) / 2 - bbox[0]
        ty = circle_cy - (bbox[3] - bbox[1]) / 2 - bbox[1]

        # Text shadow
        draw.text((tx + 2, ty + 2), text, fill=(0, 0, 0, 160), font=font)
        # White text
        draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)

        img.save(str(out_path), "PNG")

    def _make_title_card(self, num: int, title: str, out_path: Path) -> None:
        """Render a full W×H story title card (opaque PNG) with number and title."""
        import textwrap
        from PIL import Image as PILImage, ImageDraw, ImageFont

        W, H = self.width, self.height
        img = PILImage.new("RGB", (W, H), (6, 14, 32))
        draw = ImageDraw.Draw(img)

        # Top-to-bottom gradient background
        for y in range(0, H, 2):
            t = y / H
            draw.rectangle(
                [0, y, W, y + 2],
                fill=(int(6 + t * 14), int(14 + t * 18), int(32 + t * 28)),
            )

        # Amber accent bars and left stripe
        amber = (255, 176, 0)
        draw.rectangle([0, 0, W, 6], fill=amber)
        draw.rectangle([0, H - 6, W, H], fill=amber)
        draw.rectangle([0, 0, 10, H], fill=amber)

        # ---- font loader ----
        def load_f(sz: int, bold: bool = False) -> Any:
            names = (
                ["arialbd.ttf", "Arial Bold.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf"]
                if bold else
                ["arial.ttf", "Arial.ttf", "calibri.ttf", "DejaVuSans.ttf"]
            )
            for n in names:
                try:
                    return ImageFont.truetype(n, sz)
                except OSError:
                    pass
            return ImageFont.load_default()

        f_label = load_f(int(H * 0.042))
        f_num   = load_f(int(H * 0.20), bold=True)
        f_title = load_f(int(H * 0.058), bold=True)
        f_sub   = load_f(int(H * 0.026))

        def measure(text: str, font: Any):
            b = draw.textbbox((0, 0), text, font=font)
            return b[2] - b[0], b[3] - b[1]

        lw, lh = measure("STORY", f_label)
        nw, nh = measure(str(num), f_num)
        wrapped = textwrap.wrap(title, width=34)
        line_h  = int(H * 0.058) + 14
        title_h = len(wrapped) * line_h

        gap, sep = 18, 5
        total_h = lh + gap + nh + gap + sep + gap + title_h
        y = (H - total_h) // 2
        cx = W // 2

        # "STORY" label
        draw.text((cx - lw // 2, y), "STORY", fill=amber, font=f_label)
        y += lh + gap

        # Large number
        draw.text((cx - nw // 2, y), str(num), fill=(255, 205, 30), font=f_num)
        y += nh + gap

        # Separator line
        draw.rectangle([W // 4, y, 3 * W // 4, y + sep], fill=amber)
        y += sep + gap

        # Title lines
        for line in wrapped:
            tw2, _ = measure(line, f_title)
            draw.text((cx - tw2 // 2, y), line, fill=(235, 235, 242), font=f_title)
            y += line_h

        # Bottom label
        sub = "DEEP DIVE AI  ·  AI NEWS"
        sw, _ = measure(sub, f_sub)
        draw.text((cx - sw // 2, H - 52), sub, fill=(110, 125, 160), font=f_sub)

        img.save(str(out_path), "PNG")

    def _add_story_number_overlay(
        self, video_path: Path, scene_durations: List[float]
    ) -> Path:
        """Overlay per-story elements on an AI News video:

        - Amber circle badge (top-left, 108 px) visible for the **full duration**
          of each story section (appears after the title card disappears).
        - Full-frame dark title card with "STORY N" + story title shown for the
          first 3 seconds of each story section.

        Both use FFmpeg filter_complex chained overlays gated by between(t,...).
        """
        scenes = self._load_scenes_json()
        if not scenes:
            self.logger.warning("story_number overlay skipped — no scenes.json")
            return video_path

        # Build full time ranges for each story section
        story_ranges: Dict[int, Dict] = {}
        cumulative = 0.0
        for i, dur in enumerate(scene_durations):
            sm = scenes[i] if i < len(scenes) else {}
            sn = int(sm.get("story_number", 0))
            if sn > 0:
                if sn not in story_ranges:
                    story_ranges[sn] = {
                        "start": cumulative,
                        "end": cumulative + dur,
                        "title": sm.get("story_title", f"Story {sn}"),
                    }
                else:
                    story_ranges[sn]["end"] = cumulative + dur
            cumulative += dur

        if not story_ranges:
            self.logger.info("No story_number > 0 in scenes.json — overlay skipped")
            return video_path

        try:
            from PIL import Image as PILImage  # noqa: F401
        except ImportError:
            self.logger.warning("Pillow not installed — story overlay skipped")
            return video_path

        assets_dir = self.output_dir / "_story_assets"
        assets_dir.mkdir(exist_ok=True)

        badge_pngs: Dict[int, Path] = {}
        card_pngs: Dict[int, Path] = {}
        for num, info in sorted(story_ranges.items()):
            bp = assets_dir / f"badge_{num:02d}.png"
            self._make_story_badge(num, 108, bp)
            badge_pngs[num] = bp

            cp = assets_dir / f"card_{num:02d}.png"
            self._make_title_card(num, info["title"], cp)
            card_pngs[num] = cp

        title_secs = 3.0  # title card display duration
        sorted_nums = sorted(story_ranges.keys())
        stories = [
            (story_ranges[n]["start"], story_ranges[n]["end"], n, story_ranges[n]["title"])
            for n in sorted_nums
        ]

        # FFmpeg inputs: [0]=video, badges, then title cards
        ffmpeg_inputs: List[str] = ["-i", str(video_path)]
        badge_idx: Dict[int, int] = {}
        for i, num in enumerate(sorted_nums):
            ffmpeg_inputs += ["-i", str(badge_pngs[num])]
            badge_idx[num] = i + 1

        card_idx: Dict[int, int] = {}
        for i, num in enumerate(sorted_nums):
            ffmpeg_inputs += ["-i", str(card_pngs[num])]
            card_idx[num] = len(sorted_nums) + i + 1

        # filter_complex: badge overlays first (appear after title card), then
        # title card overlays on top (so they cover the badge during the first 3s)
        parts: List[str] = []
        prev = "[0:v]"
        margin = 24

        for i, (start, end, num, _) in enumerate(stories):
            badge_start = start + title_secs
            if badge_start >= end:
                badge_start = start
            out_label = f"[vb{i}]"
            parts.append(
                f"{prev}[{badge_idx[num]}:v]overlay=x={margin}:y={margin}"
                f":enable='between(t,{badge_start:.3f},{end:.3f})'{out_label}"
            )
            prev = out_label

        for i, (start, end, num, _) in enumerate(stories):
            card_end = min(start + title_secs, end)
            is_last = i == len(stories) - 1
            out_label = "[vout]" if is_last else f"[vc{i}]"
            parts.append(
                f"{prev}[{card_idx[num]}:v]overlay=x=0:y=0"
                f":enable='between(t,{start:.3f},{card_end:.3f})'{out_label}"
            )
            prev = out_label

        filter_complex = ";".join(parts)

        out = self.output_dir / "_with_story_numbers.mp4"
        codec = self._pick_codec()
        cmd = [
            "ffmpeg", "-y",
            *ffmpeg_inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",
            *self._codec_args(codec),
            "-c:a", "copy",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            self.logger.warning("Story overlay failed:\n%s", r.stderr[-500:])
            return video_path

        self.logger.info(
            "Story overlay: %d title cards + badges → %s",
            len(stories), out.name,
        )
        return out

    # ------------------------------------------------------------------
    # Logo overlay (Stage 2.8)
    # ------------------------------------------------------------------
    def _add_logo_overlay(self, video_path: Path) -> Path:
        """Composite a logo image at the top-right corner of the video."""
        logo = Path(self.logo_path)
        if not logo.is_file():
            return video_path

        out = self.output_dir / "_with_logo.mp4"
        target_w = max(1, int(self.logo_scale * self.width))
        m = self.logo_margin
        opacity = max(0.0, min(1.0, self.logo_opacity))

        # Scale logo to target width; preserve alpha; apply opacity via colorchannelmixer
        logo_filter = (
            f"[1:v]scale={target_w}:-2:flags=lanczos,"
            f"format=rgba,"
            f"colorchannelmixer=aa={opacity:.4f}"
            f"[logo];"
            f"[0:v][logo]overlay=main_w-overlay_w-{m}:{m}:format=auto"
        )

        codec = self._pick_codec()
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(logo),
            "-filter_complex", logo_filter,
            "-map", "0:a?",
            *self._codec_args(codec),
            "-pix_fmt", "yuv420p",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            self.logger.warning(f"Logo overlay failed: {r.stderr[-400:]}")
            return video_path

        self.logger.info(f"Logo overlay ({target_w}px, opacity={opacity:.2f}) → {out}")
        return out

    # ------------------------------------------------------------------
    # Asset helpers
    # ------------------------------------------------------------------
    def _find_narration(self, audio_dir: Path) -> Optional[Path]:
        for name in ["narration_merged.wav", "narration_merged.mp3"]:
            p = audio_dir / name
            if p.exists():
                return p
        # Fallback: any non-scene audio file (scene_NNN.wav files are per-scene, not merged)
        for ext in ["*.wav", "*.mp3"]:
            found = [f for f in sorted(audio_dir.glob(ext))
                     if not f.stem.startswith("scene_")]
            if found:
                return found[0]
        return None

    def _find_music(self, input_dir: Path) -> Optional[Path]:
        for ext in [".mp3", ".wav", ".ogg", ".m4a"]:
            for name in [f"bg_music{ext}", f"music{ext}", f"background{ext}"]:
                p = input_dir / name
                if p.exists():
                    return p
        for ext in [".mp3", ".wav", ".ogg", ".m4a"]:
            found = list(input_dir.glob(f"*{ext}"))
            if found:
                return found[0]
        return None

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

    def _calculate_scene_durations(
        self, num_scenes: int, audio_file: Optional[Path]
    ) -> List[float]:
        audio_dir = self.project_dir / "audio"
        images_dir = self.project_dir / "images"

        # Build scene_id → actual WAV duration map (no count requirement)
        wav_durs: Dict[int, float] = {}
        for wav in sorted(audio_dir.glob("scene_*.wav")):
            try:
                sid = int(wav.stem.split("_")[1])
                with wave.open(str(wav), "rb") as wf:
                    wav_durs[sid] = wf.getnframes() / float(wf.getframerate())
            except Exception:
                pass

        # scenes.json declared durations as fallback per scene_id
        scenes_json = self._load_scenes_json()
        json_durs: Dict[int, float] = {}
        for i, s in enumerate(scenes_json):
            raw_sid = s.get("scene_id") or s.get("id")
            try:
                sid = int(raw_sid) if raw_sid is not None else i + 1
            except (ValueError, TypeError):
                sid = i + 1
            d = float(s.get("duration", 0.0))
            if d > 0:
                json_durs[sid] = d

        image_files = sorted(images_dir.glob("scene_*.png"))
        # AI news: images live in sections subdirs; use scenes.json positional durations
        if not image_files and num_scenes > 0:
            durations = []
            for i in range(num_scenes):
                d = float(scenes_json[i].get("duration", 5.0)) if i < len(scenes_json) else 5.0
                durations.append(d if d > 0 else 5.0)
            return durations
        durations: List[float] = []

        for i, img in enumerate(image_files[:num_scenes]):
            try:
                sid = int(img.stem.split("_")[1])
            except (IndexError, ValueError):
                sid = i + 1

            dur = wav_durs.get(sid)                         # actual TTS output
            if not dur:
                dur = json_durs.get(sid)                    # declared estimate
            if not dur and i < len(scenes_json):
                dur = float(scenes_json[i].get("duration", 0.0)) or None
            durations.append(dur if dur and dur > 0 else 5.0)

        # If no WAVs found at all, fall back to splitting merged audio evenly
        if not wav_durs and audio_file and audio_file.exists():
            total_dur = self._probe_duration(audio_file)
            if total_dur > 0:
                dur = total_dur / num_scenes
                self.logger.info(f"Scene durations from merged audio split: {dur:.2f}s × {num_scenes}")
                return [dur] * num_scenes

        self.logger.info(
            f"Scene durations: {len(durations)} scenes, "
            f"total {sum(durations):.1f}s "
            f"({len(wav_durs)} from WAV, {len(durations) - len(wav_durs)} from scenes.json)"
        )
        return durations
