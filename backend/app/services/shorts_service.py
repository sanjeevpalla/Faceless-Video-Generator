"""
ShortsService — generate N × 30-second YouTube Shorts rebuilt from scene clips and audio.

Highlight selection (TF-IDF content scoring):
  1. Parse scenes.json — narration text, titles, durations.
  2. Score each scene with TF-IDF: high unique-term density → high score.
  3. Build all consecutive-scene windows that sum to ≈30 seconds.
  4. Score each window = sum of contained scene scores.
  5. Greedily select the top N non-overlapping windows; sort chronologically.
  6. Assemble each short from:
       - clips/scene_NNN.mp4  (Wan2GP animated, preferred)
       - images/scene_NNN.png (static fallback → Ken Burns slideshow)
       - audio/scene_NNN.wav  (per-scene narration)
       - input/*.mp3           (background music at 8% volume)
  7. Crop to 9:16 vertical (1080×1920), trim to SHORT_DURATION.
  8. No subtitles — source clips are clean.
"""
import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import wave
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)

SHORTS_DIR = "shorts"
SHORT_W, SHORT_H = 1080, 1920
SHORT_DURATION = 30.0

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "that", "this", "it", "is", "are", "was",
    "were", "be", "been", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "about", "when",
    "where", "what", "how", "who", "which", "not", "no", "more", "also",
    "just", "they", "their", "we", "our", "its", "into", "than", "even",
    "very", "most", "only", "some", "each", "while", "these", "those",
    "such", "both", "since", "after", "before", "here", "there", "then",
    "now", "once", "still", "between", "through", "over", "under", "again",
    "further", "during", "because", "however", "instead", "within", "many",
    "every", "another", "without", "already", "other", "being", "all",
    "him", "her", "his", "she", "he", "you", "your", "my", "me", "us",
    "them", "too", "so", "up", "out", "if", "can", "like", "get", "got",
    "let", "see", "say", "said", "make", "made", "take", "use", "used",
    "using", "new", "one", "two", "three", "first", "last", "long", "back",
    "old", "little", "give", "day", "man", "keep", "know", "year", "real",
    "any", "per", "yet", "put", "end", "add", "set", "show", "come", "came",
    "look", "need", "feel", "try", "turn", "ask", "mean", "move", "live",
    "hold", "lead", "read", "run", "stay", "own", "call", "start", "right",
    "seem", "next", "late", "point", "well", "become", "way", "part", "work",
    "world", "place", "thing", "time", "people", "number", "hand", "high",
    "open", "seem", "together", "next", "white", "children", "begin", "got",
    "walk", "example", "ease", "paper", "group", "always", "music", "those",
    "both", "mark", "book", "letter", "until", "mile", "river", "car",
    "feet", "care", "second", "enough", "plain", "girl", "usual", "young",
    "ready", "above", "ever", "red", "list", "though", "feel", "talk",
    "bird", "soon", "body", "dog", "family", "direct", "pose", "leave",
    "song", "measure", "door", "product", "black", "short", "numeral",
    "class", "wind", "question", "happen", "complete", "ship", "area",
    "half", "rock", "order", "fire", "south", "problem", "piece", "told",
    "knew", "pass", "since", "top", "whole", "king", "space",
}


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _write_status(
    shorts_dir: Path,
    state: str,
    progress: float,
    message: str,
    extras: Optional[Dict] = None,
) -> None:
    data: Dict[str, Any] = {
        "state": state,
        "progress": round(progress, 1),
        "message": message,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if extras:
        data.update(extras)
    try:
        (shorts_dir / "status.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def read_status(shorts_dir: Path) -> Dict[str, Any]:
    p = shorts_dir / "status.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"state": "idle", "progress": 0, "message": ""}


# ---------------------------------------------------------------------------
# TF-IDF scoring
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    return [
        w.lower()
        for w in re.findall(r"\b[a-zA-Z]{3,}\b", text)
        if w.lower() not in STOPWORDS
    ]


def _score_scenes_tfidf(scenes: List[Dict]) -> List[float]:
    """Return a TF-IDF score for each scene; higher = more information-dense / unique content."""
    token_lists = [
        _tokenize(s.get("narration", "") + " " + s.get("title", ""))
        for s in scenes
    ]
    n = len(scenes)
    if n == 0:
        return []
    df: Counter = Counter()
    for tokens in token_lists:
        df.update(set(tokens))
    scores: List[float] = []
    for tokens in token_lists:
        tf = Counter(tokens)
        score = sum(
            tf[w] * math.log(n / df[w])
            for w in tf
            if df[w] < n  # skip ubiquitous terms
        )
        scores.append(score)
    return scores


# ---------------------------------------------------------------------------
# Window building and selection
# ---------------------------------------------------------------------------

def _build_windows(
    scenes: List[Dict],
    scores: List[float],
    target: float = SHORT_DURATION,
) -> List[Tuple[List[int], float, float]]:
    """
    Build consecutive-scene windows in the range [75%, 130%] of target.
    Returns (scene_indices, total_duration, effective_score).

    Effective score = raw_score × min(1.0, target/total) so windows that run
    over the target duration are penalised — tighter windows win when content
    density is otherwise equal.
    """
    n = len(scenes)
    windows: List[Tuple[List[int], float, float]] = []
    for start in range(n):
        # Don't start a window on a zeroed-out (intro/outro) scene
        if scores[start] == 0.0:
            continue
        total = 0.0
        wscore = 0.0
        indices: List[int] = []
        for end in range(start, n):
            d = float(scenes[end].get("duration", 5))
            total += d
            wscore += scores[end]
            indices.append(end)
            if total >= target * 0.75:
                effective = wscore * min(1.0, target / total)
                windows.append((list(indices), total, effective))
            if total >= target * 1.5:
                break
    return windows


def _select_top_windows(
    windows: List[Tuple[List[int], float, float]],
    count: int,
) -> List[Tuple[List[int], float]]:
    """Greedy: pick highest-scoring non-overlapping windows, then re-sort by scene order."""
    sorted_w = sorted(windows, key=lambda w: w[2], reverse=True)
    selected: List[Tuple[List[int], float]] = []
    used: set = set()
    for indices, dur, _ in sorted_w:
        if len(selected) >= count:
            break
        if not any(i in used for i in indices):
            selected.append((indices, dur))
            used.update(indices)
    selected.sort(key=lambda x: x[0][0])
    return selected


def _fallback_windows(
    scenes: List[Dict],
    count: int,
    target: float,
) -> List[Tuple[List[int], float, str]]:
    """Equally-spaced windows across the content when TF-IDF yields too few candidates."""
    n = len(scenes)
    result: List[Tuple[List[int], float, str]] = []
    step = max(1, n // (count + 1))
    for i in range(count):
        center = min(step * (i + 1), n - 1)
        indices: List[int] = []
        total = 0.0
        j = center
        while j < n and total < target * 0.75:
            indices.append(j)
            total += float(scenes[j].get("duration", 5))
            j += 1
        if not indices:
            indices = [center]
            total = float(scenes[center].get("duration", 5))
        title = scenes[indices[0]].get("title") or f"Highlight {i + 1}"
        result.append((indices, total, title))
    return result


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 5.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ShortsService:
    def __init__(self, project_id: str, project_dir: Path, count: int = 5) -> None:
        self.project_id = project_id
        self.project_dir = project_dir
        self.count = max(1, min(count, 10))
        self.audio_dir = project_dir / "audio"
        self.clips_dir = project_dir / "clips"
        self.images_dir = project_dir / "images"
        self.input_dir = project_dir / "input"
        self.logger = logger

    # ── Entry point ──────────────────────────────────────────────────────────

    async def generate(self) -> Dict[str, Any]:
        shorts_dir = self.project_dir / "output" / SHORTS_DIR
        shorts_dir.mkdir(parents=True, exist_ok=True)
        scenes_file = self.input_dir / "scenes.json"

        _write_status(shorts_dir, "generating", 2, "Analysing content for highlight selection…")

        loop = asyncio.get_event_loop()
        try:
            windows: List[Tuple[List[int], float, str]] = await loop.run_in_executor(
                None, self._select_windows, scenes_file
            )
        except Exception as exc:
            _write_status(shorts_dir, "error", 0, str(exc))
            raise

        self.logger.info(
            f"Selected {len(windows)} highlight windows for project {self.project_id}: "
            + ", ".join(f'"{t}"' for _, _, t in windows)
        )

        scenes = self._load_scenes(scenes_file)
        music_file = self._find_music()
        results: List[Dict[str, Any]] = []

        for i, (scene_indices, dur, title) in enumerate(windows):
            out_path = shorts_dir / f"short_{i + 1}.mp4"
            pct = 5 + (i / self.count) * 90
            _write_status(
                shorts_dir, "generating", pct,
                f"Building short {i + 1}/{self.count}: {title}…",
            )
            try:
                await loop.run_in_executor(
                    None, self._build_short,
                    scenes, scene_indices, music_file, out_path,
                )
                size_mb = (
                    round(out_path.stat().st_size / (1024 * 1024), 2)
                    if out_path.exists() else 0
                )
                # Estimate content position as cumulative scene duration before this window
                scene_start = sum(
                    float(scenes[j].get("duration", 5))
                    for j in range(scene_indices[0])
                ) if scenes else 0.0
                results.append({
                    "index": i + 1,
                    "filename": out_path.name,
                    "title": title,
                    "start_time": round(scene_start, 1),
                    "duration": SHORT_DURATION,
                    "size_mb": size_mb,
                    "status": "ready",
                })
            except Exception as exc:
                self.logger.error(f"Short {i + 1} ({title}) failed: {exc}", exc_info=True)
                results.append({
                    "index": i + 1,
                    "filename": out_path.name,
                    "title": title,
                    "start_time": 0.0,
                    "duration": SHORT_DURATION,
                    "size_mb": 0,
                    "status": "error",
                    "error": str(exc),
                })

        manifest = {
            "count": self.count,
            "short_duration": SHORT_DURATION,
            "resolution": f"{SHORT_W}x{SHORT_H}",
            "shorts": results,
        }
        (shorts_dir / "shorts_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        ok = sum(1 for r in results if r["status"] == "ready")
        _write_status(
            shorts_dir, "ready", 100,
            f"{ok}/{self.count} highlight shorts ready",
            {"shorts": results},
        )
        return manifest

    # ── Scene selection ──────────────────────────────────────────────────────

    def _select_windows(self, scenes_file: Path) -> List[Tuple[List[int], float, str]]:
        scenes = self._load_scenes(scenes_file)
        if not scenes:
            raise RuntimeError("No scenes found in scenes.json — cannot select highlights")

        scores = _score_scenes_tfidf(scenes)

        # Zero-out intro (first section) and outro (last two sections)
        sections = [s.get("section", "") for s in scenes]
        all_secs = list(dict.fromkeys(sections))
        skip_secs: set = set()
        if len(all_secs) >= 1:
            skip_secs.add(all_secs[0])
        if len(all_secs) >= 2:
            skip_secs.add(all_secs[-1])
        if len(all_secs) >= 3:
            skip_secs.add(all_secs[-2])

        adjusted = [
            0.0 if scenes[i].get("section", "") in skip_secs else s
            for i, s in enumerate(scores)
        ]

        windows = _build_windows(scenes, adjusted, SHORT_DURATION)
        if not windows:
            return _fallback_windows(scenes, self.count, SHORT_DURATION)

        top = _select_top_windows(windows, self.count)

        # Fill remaining slots with fallback if we didn't get enough
        if len(top) < self.count:
            used_idx = {i for indices, _ in top for i in indices}
            for fb_indices, fb_dur, fb_title in _fallback_windows(scenes, self.count * 2, SHORT_DURATION):
                if len(top) >= self.count:
                    break
                # Never start a fallback window in a skip section
                if scenes[fb_indices[0]].get("section", "") in skip_secs:
                    continue
                if not any(i in used_idx for i in fb_indices):
                    top.append((fb_indices, fb_dur))
                    used_idx.update(fb_indices)
            top.sort(key=lambda x: x[0][0])

        result: List[Tuple[List[int], float, str]] = []
        for scene_indices, dur in top:
            best = max(scene_indices, key=lambda j: adjusted[j])
            title = (
                scenes[best].get("title")
                or scenes[best].get("section")
                or f"Highlight {len(result) + 1}"
            )
            result.append((scene_indices, dur, title))
        return result

    # ── Build one short ──────────────────────────────────────────────────────

    def _build_short(
        self,
        scenes: List[Dict],
        scene_indices: List[int],
        music_file: Optional[Path],
        out_path: Path,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="short_") as tmpdir:
            tmp = Path(tmpdir)
            video = self._build_window_video(scenes, scene_indices, tmp)
            audio = self._build_window_audio(scenes, scene_indices, tmp)
            if music_file:
                audio = self._mix_audio(audio, music_file, tmp)
            self._compose_short(video, audio, out_path)

    def _build_window_video(
        self,
        scenes: List[Dict],
        scene_indices: List[int],
        tmp: Path,
    ) -> Path:
        """Concatenate animated clips (or image stills) for this window."""
        segments: List[Path] = []

        for idx, j in enumerate(scene_indices):
            scene = scenes[j]
            scene_id = int(scene.get("scene_id", j + 1))
            dur = float(scene.get("duration", 5.0))

            # Prefer Wan2GP animated clip
            clip = self.clips_dir / f"scene_{scene_id:03d}.mp4"
            if clip.exists():
                segments.append(clip)
                continue

            # Fall back to static image
            img: Optional[Path] = None
            if self.images_dir.exists():
                candidate = self.images_dir / f"scene_{scene_id:03d}.png"
                if candidate.exists():
                    img = candidate
                else:
                    matches = list(self.images_dir.glob(f"scene_{scene_id}*.png"))
                    if matches:
                        img = matches[0]

            wav = self.audio_dir / f"scene_{scene_id:03d}.wav"
            actual_dur = _wav_duration(wav) if wav.exists() else dur

            if img:
                clip_tmp = tmp / f"img_{idx:03d}.mp4"
                self._image_to_clip(img, actual_dur, clip_tmp)
                segments.append(clip_tmp)

        if not segments:
            ids = [scenes[j].get("scene_id", j + 1) for j in scene_indices]
            raise RuntimeError(f"No clips or images found for scenes {ids}")

        if len(segments) == 1:
            return segments[0]

        # Concatenate: re-encode to 1920×1080 @ 30fps so all segments match
        concat_list = tmp / "concat_video.txt"
        concat_list.write_text(
            "\n".join(f"file '{p}'" for p in segments), encoding="utf-8"
        )
        out = tmp / "window_video.mp4"
        r = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-vf",
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-an", str(out),
            ],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Video concat failed: {r.stderr[-400:]}")
        return out

    def _image_to_clip(self, img: Path, duration: float, out: Path) -> None:
        r = subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(img),
                "-t", f"{duration:.3f}",
                "-vf",
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-an", str(out),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Image-to-clip failed: {r.stderr[-200:]}")

    def _build_window_audio(
        self,
        scenes: List[Dict],
        scene_indices: List[int],
        tmp: Path,
    ) -> Path:
        """Concatenate per-scene WAV files; fall back to silence if none found."""
        wavs: List[Path] = []
        for j in scene_indices:
            scene_id = int(scenes[j].get("scene_id", j + 1))
            wav = self.audio_dir / f"scene_{scene_id:03d}.wav"
            if wav.exists():
                wavs.append(wav)

        if not wavs:
            out = tmp / "silence.wav"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"aevalsrc=0:d={SHORT_DURATION}",
                    "-ar", "44100", str(out),
                ],
                capture_output=True, timeout=30,
            )
            return out

        if len(wavs) == 1:
            return wavs[0]

        concat_list = tmp / "concat_audio.txt"
        concat_list.write_text(
            "\n".join(f"file '{p}'" for p in wavs), encoding="utf-8"
        )
        out = tmp / "window_audio.wav"
        r = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:a", "pcm_s16le", str(out),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Audio concat failed: {r.stderr[-200:]}")
        return out

    def _mix_audio(self, narration: Path, music: Path, tmp: Path) -> Path:
        """Mix narration (full volume) + looped background music at 8% volume."""
        out = tmp / "mixed_audio.aac"
        r = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(narration),
                "-stream_loop", "-1", "-i", str(music),
                "-filter_complex",
                "[0:a]volume=1.0[nar];"
                "[1:a]volume=0.08[mus];"
                "[nar][mus]amix=inputs=2:duration=first[out]",
                "-map", "[out]",
                "-t", f"{SHORT_DURATION:.3f}",
                "-c:a", "aac", "-b:a", "128k",
                str(out),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            self.logger.warning(f"Music mix failed, using narration only: {r.stderr[-200:]}")
            out2 = tmp / "nar_only.aac"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(narration),
                    "-t", f"{SHORT_DURATION:.3f}",
                    "-c:a", "aac", "-b:a", "128k", str(out2),
                ],
                capture_output=True, timeout=60,
            )
            return out2
        return out

    def _compose_short(self, video: Path, audio: Path, out: Path) -> None:
        """Crop centre 9:16 strip, scale to 1080×1920, trim to SHORT_DURATION, mux audio."""
        vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920"
        r = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(video),
                "-i", str(audio),
                "-t", f"{SHORT_DURATION:.3f}",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(out),
            ],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Compose failed: {r.stderr[-500:]}")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _load_scenes(self, scenes_file: Path) -> List[Dict]:
        if not scenes_file or not scenes_file.exists():
            return []
        try:
            _d = json.loads(scenes_file.read_text(encoding="utf-8"))
            return _d if isinstance(_d, list) else _d.get("scenes", [])
        except Exception:
            return []

    def _find_music(self) -> Optional[Path]:
        for pat in ("*.mp3", "*.wav", "*.ogg", "*.m4a"):
            files = sorted(self.input_dir.glob(pat))
            if files:
                return files[0]
        return None

    @staticmethod
    def list_shorts(project_dir: Path) -> List[Dict[str, Any]]:
        shorts_dir = project_dir / "output" / SHORTS_DIR
        if not shorts_dir.exists():
            return []
        manifest_path = shorts_dir / "shorts_manifest.json"
        if manifest_path.exists():
            try:
                return json.loads(
                    manifest_path.read_text(encoding="utf-8")
                ).get("shorts", [])
            except Exception:
                pass
        return [
            {
                "index": int(f.stem.split("_")[1]) if "_" in f.stem else (i + 1),
                "filename": f.name,
                "title": f"Short {i + 1}",
                "start_time": 0.0,
                "duration": SHORT_DURATION,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "status": "ready",
            }
            for i, f in enumerate(sorted(shorts_dir.glob("short_*.mp4")))
        ]


# ---------------------------------------------------------------------------
# AI News per-section 9:16 shorts
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _find_system_font() -> Optional[str]:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _escape_font_path(font: str) -> str:
    """Escape a font file path for use inside an FFmpeg drawtext fontfile= option.

    On Windows, the drive-letter colon (C:/) must be escaped as C\\:/ so the
    FFmpeg option parser does not treat it as an option separator.
    """
    s = font.replace("\\", "/")
    s = re.sub(r"^([A-Za-z]):/", r"\1\\:/", s)
    return s


def _escape_drawtext(text: str) -> str:
    return text.replace("'", "").replace(":", " -")[:55]


def _escape_srt_path(path: Path) -> str:
    s = str(path).replace("\\", "/")
    # Escape Windows drive letter colon (C:/ → C\:/)
    s = re.sub(r"^([A-Za-z]):/", r"\1\\:/", s)
    return s.replace("'", "\\'")


def _write_top_ass(srt_path: Path, out_path: Path, canvas_w: int, canvas_h: int,
                   clip_h_est: int = 608) -> None:
    """Convert SRT to ASS with subtitles positioned in the top blurred zone.

    Alignment=8 (top-center) is baked into the ASS Style so libass never falls
    back to the SRT default (bottom-center), which force_style Alignment= can
    silently ignore on some Windows FFmpeg builds.
    """
    top_zone = (canvas_h - clip_h_est) // 2   # ≈ 656 for 1920-tall canvas
    margin_v = top_zone // 2 - 15             # centre of top zone, minus half a line

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {canvas_w}\n"
        f"PlayResY: {canvas_h}\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Alignment=8 = top-centre; MarginV = distance from the top edge
        f"Style: Default,Arial,30,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"0,0,0,0,100,100,0,0,1,2,1,8,10,10,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    def _ts(t: str) -> str:
        """HH:MM:SS,mmm → H:MM:SS.cs (ASS centiseconds)."""
        h, m, rest = t.strip().split(":")
        s, ms = rest.split(",")
        return f"{int(h)}:{m}:{s}.{int(ms) // 10:02d}"

    srt_text = srt_path.read_text(encoding="utf-8", errors="ignore")
    rows: list[str] = []
    for block in re.split(r"\n\n+", srt_text.strip()):
        lines = [ln.rstrip() for ln in block.strip().splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        try:
            parts = lines[1].split(" --> ")
            start, end = _ts(parts[0]), _ts(parts[1])
            text = r"\N".join(lines[2:])
            text = re.sub(r"<[^>]+>", "", text)
            rows.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        except Exception:
            continue

    out_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


class AiNewsShortsService:
    """Generates 9:16 (1080×1920) vertical short videos for AI News sections.

    For each section it uses:
      images/sections/{label}/scene_NNN.png   (cycling images; required)
      audio/sections/{label}/narration.wav    (required)
      subtitles/sections/{label}/subtitles.srt (optional — burned in at bottom)

    Output: output/ai_news_shorts/{label}.mp4
    """

    CANVAS_W = 1080
    CANVAS_H = 1920
    FPS      = 30

    def __init__(self, project_id: str, project_dir: Path,
                 narrator_clips_dir: str = "") -> None:
        self.project_id        = project_id
        self.project_dir       = project_dir
        self.narrator_clips_dir = narrator_clips_dir

    async def generate_section_short(
        self,
        section_label: str,
        title: str = "",
        narrator_text: Optional[str] = None,
        logo_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        images_dir = self.project_dir / "images"    / "sections" / section_label
        audio_path = self.project_dir / "audio"     / "sections" / section_label / "narration.wav"
        srt_path   = self.project_dir / "subtitles" / "sections" / section_label / "subtitles.srt"

        if not audio_path.exists():
            raise RuntimeError(
                f"narration.wav not found for section '{section_label}'. "
                "Generate voice first."
            )

        images: List[Path] = (
            sorted(images_dir.glob("scene_*.png")) if images_dir.exists() else []
        )

        duration = await self._probe_duration(audio_path)

        out_dir = self.project_dir / "output" / "ai_news_shorts"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{section_label}.mp4"

        await self._render(
            section_label=section_label,
            images=images,
            audio_path=audio_path,
            srt_path=srt_path,
            total_duration=duration,
            out_path=out_path,
            title=title,
            narrator_text=narrator_text,
            logo_path=logo_path if (logo_path and logo_path.exists()) else None,
        )

        return {"label": section_label, "duration": duration, "output": str(out_path)}

    async def _probe_duration(self, path: Path) -> float:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet",
            "-print_format", "json", "-show_format",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return float(json.loads(stdout)["format"]["duration"])

    async def _probe_source_size(self, path: Path) -> tuple:
        """Return (width, height) of a video or image file via ffprobe."""
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-select_streams", "v:0",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            s = json.loads(stdout)["streams"][0]
            return int(s["width"]), int(s["height"])
        except Exception:
            return self.CANVAS_W, int(self.CANVAS_W * 9 // 16)

    def _find_narrator_clips(self) -> List[Path]:
        """Return narrator clips, preferring *_nobg.webm (alpha).

        Checks project narrator/ folder first, then falls back to the global
        narrator_clips_dir from video settings (same lookup as VideoGenerationService).
        """
        def _prefer_nobg(clips: List[Path]) -> List[Path]:
            result: List[Path] = []
            for c in clips:
                nobg = c.parent / f"{c.stem}_nobg.webm"
                result.append(nobg if nobg.exists() else c)
            return result

        project_nar = self.project_dir / "narrator"
        if project_nar.exists():
            clips = sorted(project_nar.glob("*.mp4"))
            if clips:
                return _prefer_nobg(clips)

        if self.narrator_clips_dir:
            d = Path(self.narrator_clips_dir)
            if d.exists():
                clips = sorted(d.glob("*.mp4"))
                if clips:
                    return _prefer_nobg(clips)

        return []

    async def _render(
        self,
        section_label: str,
        images: List[Path],
        audio_path: Path,
        srt_path: Path,
        total_duration: float,
        out_path: Path,
        title: str,
        narrator_text: Optional[str] = None,
        logo_path: Optional[Path] = None,
    ) -> None:
        W, H = self.CANVAS_W, self.CANVAS_H

        # Prefer LTX clips (no subtitles, no narrator — clean shot)
        ltx_dir   = self.project_dir / "clips" / "sections" / section_label
        ltx_clips = sorted(ltx_dir.glob("scene_*.mp4")) if ltx_dir.exists() else []
        using_ltx = bool(ltx_clips)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)

            # ── Video input ────────────────────────────────────────────────
            if using_ltx:
                # Pre-concat LTX clips (video-only, stream-copy)
                concat_lines = "".join(f"file '{c.as_posix()}'\n" for c in ltx_clips)
                concat_txt   = tmp_p / "concat.txt"
                concat_txt.write_text(concat_lines)

                raw_concat = tmp_p / "ltx_concat.mp4"
                r = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                    "-map", "0:v:0", "-c:v", "copy",
                    str(raw_concat),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                _, stderr_c = await r.communicate()
                if r.returncode != 0:
                    raise RuntimeError(
                        f"LTX clip concat failed for '{section_label}':\n"
                        + stderr_c.decode(errors="replace")[-500:]
                    )
                vid_input = ["-i", str(raw_concat)]

            elif images:
                per = total_duration / len(images)
                lines: List[str] = []
                for img in images:
                    lines.append(f"file '{img.as_posix()}'")
                    lines.append(f"duration {per:.3f}")
                lines.append(f"file '{images[-1].as_posix()}'")
                concat_txt = tmp_p / "concat.txt"
                concat_txt.write_text("\n".join(lines))
                vid_input = ["-f", "concat", "-safe", "0", "-i", str(concat_txt)]
            else:
                vid_input = [
                    "-f", "lavfi",
                    "-i", f"color=c=black:s={W}x{H}:r={self.FPS}",
                ]

            # ── Probe actual source dimensions → correct bottom-zone geometry ──
            # We need the real clip height after FFmpeg scales source to canvas width
            # (scale=W:-2) so we know exactly where the clip ends in the 9:16 canvas.
            # Static 16:9 estimates break for 3:2 or 4:3 sources.
            _src = (ltx_clips[0] if using_ltx and ltx_clips
                    else images[0] if images else None)
            if _src:
                _sw, _sh = await self._probe_source_size(_src)
                # Mirror FFmpeg scale=W:-2: height proportional, rounded to even
                _clip_h = int(_sh * W / _sw)
                if _clip_h % 2:
                    _clip_h += 1
                _clip_h = min(_clip_h, H)
            else:
                _clip_h = int(W * 9 // 16)   # fallback: assume 16:9

            # ── 9:16 blur-background filter ────────────────────────────────
            # Input (LTX clips or images) is expanded to 9:16 with blur BG.
            if using_ltx or images:
                vf = (
                    f"split=2[bg][fg];"
                    f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},gblur=sigma=25[blurred];"
                    f"[fg]scale={W}:-2[sharp];"
                    f"[blurred][sharp]overlay=0:(H-h)/2"
                )
            else:
                vf = f"scale={W}:{H}"

            # Title drawtext (image-based only)
            if not using_ltx:
                safe_title = _escape_drawtext(title) if title else ""
                if safe_title:
                    font = _find_system_font()
                    font_arg = f":fontfile='{_escape_font_path(font)}'" if font else ""
                    vf += (
                        f",drawtext=text='{safe_title}'{font_arg}"
                        f":fontsize=42:fontcolor=white"
                        f":x=(w-text_w)/2:y=72"
                        f":box=1:boxcolor=black@0.65:boxborderw=12"
                    )

            # Subtitles in TOP blurred zone — all shots (LTX and image-based).
            # We generate a proper ASS file so libass respects Alignment=8 (top-
            # center) even on Windows FFmpeg builds that ignore force_style Alignment.
            if srt_path.exists():
                tmp_ass = tmp_p / "sub.ass"
                _write_top_ass(srt_path, tmp_ass, W, H, clip_h_est=_clip_h)
                ass_esc = _escape_srt_path(tmp_ass)
                vf += f",subtitles='{ass_esc}'"

            # Bottom-zone geometry derived from probed source size
            clip_bottom = (H + _clip_h) // 2
            btm_zone_h  = H - clip_bottom

            # Find narrator VIDEO clips — prefer *_nobg.webm (alpha, transparent BG)
            nar_clips     = self._find_narrator_clips()
            has_nar_video = bool(nar_clips)

            # Text-banner fallback: only shown when NO narrator video clips exist
            if not has_nar_video and narrator_text:
                safe_narrator = _escape_drawtext(narrator_text)
                font = _find_system_font()
                font_arg = f":fontfile='{_escape_font_path(font)}'" if font else ""
                banner_h = 140
                banner_y = clip_bottom + (btm_zone_h - banner_h) // 2  # ≈ 1522
                text_y   = banner_y + (banner_h - 46) // 2             # ≈ 1569
                vf += (
                    f",drawbox=x=0:y={banner_y}:w=iw:h={banner_h}"
                    f":color=black@0.65:t=fill"
                    f",drawtext=text='{safe_narrator}'{font_arg}"
                    f":fontsize=42:fontcolor=white"
                    f":x=(w-text_w)/2:y={text_y}"
                )

            # ── FFmpeg command ─────────────────────────────────────────────
            _enc = ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart"]

            if has_nar_video:
                # Narrator VIDEO — circular crop, looped into the bottom blurred zone.
                # Pipeline: crop to square → scale to circle_d × circle_d →
                #   format=yuva420p (adds alpha for raw MP4) →
                #   geq circle mask (min with existing alpha so nobg clips stay cut-out) →
                #   overlay centred horizontally at y=clip_bottom.
                nar_clip = nar_clips[0]
                circle_d = btm_zone_h   # diameter fills the bottom zone height
                # geq: inside circle → preserve original alpha; outside → transparent.
                _geq = (
                    "geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                    "a='min(alpha(X,Y)"
                    ",255*lte(pow(X-W/2,2)+pow(Y-H/2,2)"
                    ",pow(min(W,H)/2,2)))'"
                )
                fc = (
                    f"[0:v]{vf}[_main];"
                    f"[2:v]crop=min(iw\\,ih):min(iw\\,ih),scale={circle_d}:{circle_d},"
                    f"format=yuva420p,{_geq}[_nar];"
                    f"[_main][_nar]overlay=(main_w-overlay_w)/2:{clip_bottom}"
                    f":format=yuv420:shortest=0[vout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    *vid_input,
                    "-i", str(audio_path),
                    "-stream_loop", "-1", "-i", str(nar_clip),
                    "-filter_complex", fc,
                    "-map", "[vout]", "-map", "1:a:0",
                    "-t", f"{total_duration:.3f}",
                    *_enc, str(out_path),
                ]
            elif logo_path and not using_ltx:
                filter_complex = (
                    f"[0:v]{vf}[_filtered];"
                    f"[2:v]scale=150:-1[_logo];"
                    f"[_filtered][_logo]overlay=W-w-20:20[vout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    *vid_input,
                    "-i", str(audio_path),
                    "-i", str(logo_path),
                    "-filter_complex", filter_complex,
                    "-map", "[vout]", "-map", "1:a:0",
                    "-t", f"{total_duration:.3f}",
                    *_enc, str(out_path),
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    *vid_input,
                    "-i", str(audio_path),
                    "-vf", vf,
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-t", f"{total_duration:.3f}",
                    *_enc, str(out_path),
                ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg failed for short '{section_label}':\n"
                    + stderr.decode(errors="replace")[-1000:]
                )


# ---------------------------------------------------------------------------
# AI News per-section 16:9 clip regenerator
# ---------------------------------------------------------------------------

class AiNewsClipService:
    """Regenerates a 16:9 (1920×1080) section clip from images + narration.

    Used for per-section clip re-generation without running the full video render.
    Output: output/clips_ai_news/{label}.mp4
    """

    CANVAS_W = 1920
    CANVAS_H = 1080
    FPS = 30

    def __init__(self, project_id: str, project_dir: Path) -> None:
        self.project_id = project_id
        self.project_dir = project_dir

    async def regenerate_section_clip(
        self,
        section_label: str,
        title: str = "",
    ) -> Dict[str, Any]:
        # Agenda clip has no narration — rebuild the story-list card directly.
        if section_label == "agenda":
            return await self._regenerate_agenda_clip()

        images_dir = self.project_dir / "images"    / "sections" / section_label
        audio_path = self.project_dir / "audio"     / "sections" / section_label / "narration.wav"
        srt_path   = self.project_dir / "subtitles" / "sections" / section_label / "subtitles.srt"

        if not audio_path.exists():
            raise RuntimeError(
                f"narration.wav not found for section '{section_label}'. "
                "Generate voice first."
            )

        images: List[Path] = (
            sorted(images_dir.glob("scene_*.png")) if images_dir.exists() else []
        )

        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
            str(audio_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        duration = float(json.loads(stdout)["format"]["duration"])

        out_dir = self.project_dir / "output" / "clips_ai_news"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{section_label}.mp4"

        await self._render(section_label, images, audio_path, srt_path, duration, out_path, title)
        return {"label": section_label, "duration": duration, "output": str(out_path)}

    async def _regenerate_agenda_clip(self) -> Dict[str, Any]:
        """Rebuild the 'TODAY'S TOP 10 AI STORIES' agenda card clip."""
        from app.services.ai_news_section_service import AiNewsSectionService
        from app.services.video_service import VideoGenerationService as VideoService

        script_path = self.project_dir / "input" / "script.md"
        story_titles: List[str] = []
        if script_path.exists():
            try:
                sections = AiNewsSectionService.parse_script_sections(
                    script_path.read_text(encoding="utf-8")
                )
                story_titles = [s["title"] for s in sections if s.get("type") == "story"]
            except Exception:
                pass

        out_dir = self.project_dir / "output" / "clips_ai_news"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "agenda.mp4"

        svc = VideoService(
            project_id=self.project_id,
            project_dir=self.project_dir,
            project_type="ai_news",
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            svc._build_intro_agenda_clip,
            story_titles,
            out_path,
            "libx264",
            6.0,
            True,  # with_audio — silent track so the clip is a valid video file
        )

        return {"label": "agenda", "duration": 6.0, "output": str(out_path)}

    async def _render(
        self,
        section_label: str,
        images: List[Path],
        audio_path: Path,
        srt_path: Path,
        total_duration: float,
        out_path: Path,
        title: str,
    ) -> None:
        W, H = self.CANVAS_W, self.CANVAS_H

        # Prefer LTX clips when available
        ltx_dir   = self.project_dir / "clips" / "sections" / section_label
        ltx_clips = sorted(ltx_dir.glob("scene_*.mp4")) if ltx_dir.exists() else []

        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)

            if ltx_clips:
                # ── LTX clips: pre-concat (video-only, stream-copy) ───────────
                concat_lines = "".join(f"file '{c.as_posix()}'\n" for c in ltx_clips)
                concat_txt   = tmp_p / "concat.txt"
                concat_txt.write_text(concat_lines)

                raw_concat = tmp_p / "ltx_concat.mp4"
                r = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                    "-map", "0:v:0", "-c:v", "copy",
                    str(raw_concat),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                _, stderr_c = await r.communicate()
                if r.returncode != 0:
                    raise RuntimeError(
                        f"LTX clip concat failed for '{section_label}':\n"
                        + stderr_c.decode(errors="replace")[-500:]
                    )
                vid_input = ["-i", str(raw_concat)]

            elif images:
                per = total_duration / len(images)
                lines: List[str] = []
                for img in images:
                    lines.append(f"file '{img.as_posix()}'")
                    lines.append(f"duration {per:.3f}")
                lines.append(f"file '{images[-1].as_posix()}'")
                concat_txt = tmp_p / "concat.txt"
                concat_txt.write_text("\n".join(lines))
                vid_input = ["-f", "concat", "-safe", "0", "-i", str(concat_txt)]

            else:
                vid_input = [
                    "-f", "lavfi",
                    "-i", f"color=c=black:s={W}x{H}:r={self.FPS}",
                ]

            # Scale to fill 16:9 canvas
            vf = (
                f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
            )

            # Optional section title
            if title:
                safe_title = _escape_drawtext(title)
                font = _find_system_font()
                font_arg = f":fontfile='{_escape_font_path(font)}'" if font else ""
                vf += (
                    f",drawtext=text='{safe_title}'{font_arg}"
                    f":fontsize=36:fontcolor=white"
                    f":x=(w-text_w)/2:y=36"
                    f":box=1:boxcolor=black@0.6:boxborderw=10"
                )

            # Subtitle burn-in
            if srt_path.exists():
                tmp_srt = tmp_p / "sub.srt"
                shutil.copy2(str(srt_path), str(tmp_srt))
                srt_esc = _escape_srt_path(tmp_srt)
                vf += (
                    f",subtitles='{srt_esc}'"
                    f":force_style='FontSize=24,PrimaryColour=&H00ffffff,"
                    f"OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=40'"
                )

            cmd = [
                "ffmpeg", "-y",
                *vid_input,
                "-i", str(audio_path),
                "-vf", vf,
                "-map", "0:v:0", "-map", "1:a:0",
                "-t", f"{total_duration:.3f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(out_path),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg failed regenerating clip '{out_path.stem}':\n"
                    + stderr.decode(errors="replace")[-1000:]
                )
