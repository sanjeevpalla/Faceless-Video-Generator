"""
DurationSyncService — equalizes per-scene narration length across every
project.languages entry so every language's rendered video ends up the same
total length.

Why this works: VideoGenerationService sizes each scene's on-screen duration
directly from that scene's WAV file length (see
video_service._calculate_scene_durations), and SubtitleGenerationService
transcribes whichever "*merged*"/"*narration*" WAV it finds in the audio dir
(see subtitle_service._find_audio_file). So making every language's per-scene
WAV the same duration — and re-merging afterwards — is sufficient to make
every language's video and subtitle timing line up, with no changes needed
in the video/subtitle rendering code itself.

Method: for each scene_id, take the longest duration observed across all
languages and pad every shorter language's WAV with trailing silence to
match it (ffmpeg `apad`). Speech is never sped up, slowed down, or trimmed —
only silence is appended after the last word — so pronunciation and pitch
are untouched.

Runs as the "duration_sync" pipeline step, after "voice" (every language's
audio must already exist) and before "subtitles" (so Whisper transcribes the
final, padded audio and its timestamps stay valid for the rendered video).
"""
import asyncio
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.base import BaseService


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


class DurationSyncService(BaseService):
    """Pads shorter-language scene WAVs with trailing silence so every
    project.languages entry shares identical per-scene (and total) duration."""

    service_name = "duration_sync"

    # Ignore differences below this — sub-frame rounding noise, not worth an
    # ffmpeg re-encode.
    MIN_PAD_SECONDS = 0.03

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        languages: List[str],
        project_language: str,
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.languages = languages
        self.project_language = project_language

    async def execute(self) -> Dict[str, Any]:
        return await self.sync()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _audio_dir(self, lang: str) -> Path:
        base = self.project_dir / "audio"
        return base if lang == self.project_language else base / lang

    def _section_labels(self) -> List[str]:
        """AI News projects store audio per section (audio[/{lang}]/sections/{label}/);
        Deep Dive projects store it flat (audio[/{lang}]/scene_*.wav). Union labels
        across every language in case they were generated in different orders."""
        labels: set = set()
        found_sections = False
        for lang in self.languages:
            d = self._audio_dir(lang) / "sections"
            if d.exists():
                found_sections = True
                labels.update(x.name for x in d.iterdir() if x.is_dir())
        return sorted(labels) if found_sections else [""]

    def _scene_dir(self, lang: str, label: str) -> Path:
        d = self._audio_dir(lang)
        return (d / "sections" / label) if label else d

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    async def sync(self) -> Dict[str, Any]:
        if len(self.languages) < 2:
            await self.report_progress(100, "Single language — nothing to sync")
            return {"scenes_padded": 0, "sections": 0}

        await self.report_progress(2, "Scanning per-language scene durations…")
        labels = self._section_labels()

        total_padded = 0
        for i, label in enumerate(labels):
            await self.check_cancelled()
            total_padded += await self._sync_group(label)
            await self.report_progress(
                5 + (i + 1) / max(len(labels), 1) * 55,
                f"Synced durations for {label or 'narration'}",
            )

        await self.report_progress(65, "Re-merging padded narration files…")
        for lang in self.languages:
            for label in labels:
                await self.check_cancelled()
                await self._remerge(lang, label)

        await self.report_progress(
            100, f"Duration sync complete — {total_padded} scene WAV(s) padded"
        )
        return {"scenes_padded": total_padded, "sections": len(labels)}

    async def _sync_group(self, label: str) -> int:
        """Pad every language's scene_NNN.wav in this section/group to the max
        duration observed for that scene_id across languages. Returns the
        number of WAVs padded."""
        by_scene: Dict[int, Dict[str, Tuple[Path, float]]] = {}
        for lang in self.languages:
            d = self._scene_dir(lang, label)
            if not d.exists():
                continue
            for wav in sorted(d.glob("scene_*.wav")):
                try:
                    sid = int(wav.stem.split("_")[1])
                except (IndexError, ValueError):
                    continue
                by_scene.setdefault(sid, {})[lang] = (wav, _wav_duration(wav))

        padded = 0
        for sid, per_lang in by_scene.items():
            await self.check_cancelled()
            target = max(dur for _, dur in per_lang.values())
            for lang, (wav, dur) in per_lang.items():
                pad = target - dur
                if pad > self.MIN_PAD_SECONDS:
                    ok = await self._pad_silence(wav, pad)
                    if ok:
                        padded += 1
        return padded

    async def _pad_silence(self, wav: Path, pad_seconds: float) -> bool:
        tmp = wav.with_suffix(".padded.wav")
        cmd = [
            "ffmpeg", "-y", "-i", str(wav),
            "-af", f"apad=pad_dur={pad_seconds:.3f}",
            str(tmp),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            if proc.returncode != 0 or not tmp.exists():
                self.logger.warning(
                    f"Silence pad failed for {wav.name}: "
                    f"{stderr.decode(errors='replace')[-300:]}"
                )
                tmp.unlink(missing_ok=True)
                return False
        except Exception as exc:
            self.logger.warning(f"Silence pad failed for {wav.name}: {exc}")
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(wav)
        return True

    async def _remerge(self, lang: str, label: str) -> None:
        d = self._scene_dir(lang, label)
        if not d.exists():
            return
        wavs = sorted(
            (p for p in d.glob("scene_*.wav")),
            key=lambda p: int(p.stem.split("_")[1]) if p.stem.split("_")[1].isdigit() else 0,
        )
        if not wavs:
            return

        merged_name = "narration.wav" if label else "narration_merged.wav"
        merged = d / merged_name
        file_list = d / "file_list.txt"
        file_list.write_text(
            "\n".join(f"file '{w}'" for w in wavs), encoding="utf-8",
        )
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(file_list), "-c", "copy", str(merged),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            if proc.returncode != 0:
                self.logger.warning(
                    f"Re-merge failed for {lang}/{label or '.'}: "
                    f"{stderr.decode(errors='replace')[-300:]}"
                )
        except Exception as exc:
            self.logger.warning(f"Re-merge failed for {lang}/{label or '.'}: {exc}")
