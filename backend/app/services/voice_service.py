import asyncio
import hashlib
import json
import shutil
import tempfile
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.services.base import BaseService
from app.core.exceptions import ServiceError


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


class VoiceGenerationService(BaseService):
    """Generates narration audio using Piper TTS."""

    service_name = "voice_generation"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        piper_executable: str = "piper",
        model_path: str = "",
        speed: float = 1.0,
        progress_callback: Optional[Callable] = None,
        settings: Optional[Any] = None,
    ) -> None:
        super().__init__(project_id, project_dir, progress_callback, settings)
        self.piper_executable = piper_executable
        self.model_path = model_path
        self.speed = speed
        self.audio_dir = self.get_output_dir("audio")
        self.cache_dir = self.get_output_dir("cache/audio")

    async def execute(self) -> Dict[str, Any]:
        return await self.generate_all()

    async def generate_all(self) -> Dict[str, Any]:
        scenes_file = self.project_dir / "input" / "scenes.json"
        if not scenes_file.exists():
            raise ServiceError(self.service_name, "scenes.json not found in project input directory")

        with open(scenes_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_scenes = data if isinstance(data, list) else data.get("scenes", [])
        if not raw_scenes:
            raise ServiceError(self.service_name, "No scenes found in scenes.json")

        scenes = [
            {
                "id":       s.get("scene_id", i + 1),
                "text":     s.get("narration", "").strip(),
                "duration": float(s.get("duration", 5)),
            }
            for i, s in enumerate(raw_scenes)
        ]
        total            = len(scenes)
        generated_files: List[Dict[str, Any]] = []
        failed:          List[Dict[str, Any]] = []

        await self.report_progress(0, f"Starting voice generation for {total} scenes")

        # ── Resume: split scenes into already-done and pending ───────────────
        pending: List[Dict[str, Any]] = []
        for scene in scenes:
            await self.check_cancelled()
            existing = self.audio_dir / f"scene_{int(scene['id']):03d}.wav"
            if existing.exists() and existing.stat().st_size > 0:
                generated_files.append({
                    "scene_id": scene["id"],
                    "path":     str(existing),
                    "filename": existing.name,
                    "duration": round(_wav_duration(existing), 2),
                    "resumed":  True,
                })
            else:
                pending.append(scene)

        if generated_files and not pending:
            # All already done — just merge and return
            pass
        elif generated_files:
            await self.report_progress(
                len(generated_files) / total * 100,
                f"Resumed — {len(generated_files)} already done, {len(pending)} pending",
                {"completed": len(generated_files), "total": total},
            )

        if pending:
            # ── Silence scenes (no narration text) ──────────────────────────
            for s in [sc for sc in pending if not sc["text"]]:
                await self.check_cancelled()
                try:
                    generated_files.append(self._write_silence(s["id"], s["duration"]))
                except Exception as exc:
                    self.logger.error("Silence gen failed scene %s: %s", s["id"], exc)
                    failed.append({"scene_id": s["id"], "error": str(exc)})

            # ── Text scenes: check cache, then batch the rest ────────────────
            text_pending = [sc for sc in pending if sc["text"]]
            to_batch:         List[Dict[str, Any]] = []
            to_batch_hashes:  List[str]            = []

            for s in text_pending:
                await self.check_cancelled()
                h = self._hash_text(s["text"])
                cached = self.check_cache(h, s["id"])
                if cached:
                    generated_files.append(cached)
                else:
                    to_batch.append(s)
                    to_batch_hashes.append(h)

            if to_batch:
                await self.report_progress(
                    len(generated_files) / total * 100,
                    f"Running Piper for {len(to_batch)} scene(s) in one batch…",
                    {"completed": len(generated_files), "total": total},
                )
                try:
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        wav_paths = await self._run_piper_batch(
                            [s["text"] for s in to_batch], Path(tmp_dir)
                        )
                        for i, (s, h) in enumerate(zip(to_batch, to_batch_hashes)):
                            if i >= len(wav_paths):
                                failed.append({"scene_id": s["id"], "error": "Piper produced no output"})
                                continue
                            dest = self.audio_dir / f"scene_{int(s['id']):03d}.wav"
                            shutil.copy2(wav_paths[i], dest)
                            duration = _wav_duration(dest)
                            result = {
                                "scene_id":  s["id"],
                                "path":      str(dest),
                                "filename":  dest.name,
                                "duration":  round(duration, 2),
                                "text_hash": h,
                            }
                            generated_files.append(result)
                            cache_file = self.cache_dir / f"{h}.json"
                            with open(cache_file, "w") as cf:
                                json.dump(result, cf)
                            await self.report_progress(
                                len(generated_files) / total * 100,
                                f"Generated {i + 1}/{len(to_batch)} scenes",
                                {"scene_id": s["id"], "completed": len(generated_files), "total": total},
                            )
                except Exception as exc:
                    self.logger.error("Piper batch failed: %s", exc)
                    for s in to_batch:
                        failed.append({"scene_id": s["id"], "error": str(exc)})

        generated_files.sort(key=lambda x: x.get("scene_id", 0))

        merged_path   = await self.merge_audio_files(generated_files) if generated_files else None
        total_duration = sum(f.get("duration", 0.0) for f in generated_files)

        manifest = {
            "total":          total,
            "generated":      len(generated_files),
            "failed":         failed,
            "total_duration": round(total_duration, 2),
            "audio_files":    generated_files,
            "merged_audio":   str(merged_path) if merged_path else None,
        }
        with open(self.audio_dir / "manifest.json", "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        await self.report_progress(100, f"Voice generation complete — {len(generated_files)}/{total} scenes")
        return manifest

    def check_cache(self, narration_hash: str, scene_id: Any) -> Optional[Dict[str, Any]]:
        cache_file = self.cache_dir / f"{narration_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                if Path(data.get("path", "")).exists():
                    return data
            except Exception:
                pass
        return None

    def _hash_text(self, text: str) -> str:
        combined = f"{text}|{self.model_path}|{self.speed}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _write_silence(self, scene_id: Any, duration: float) -> Dict[str, Any]:
        """Write a silent WAV file matching *duration* seconds for scenes with no narration."""
        import struct
        output_path = self.audio_dir / f"scene_{int(scene_id):03d}.wav"
        sample_rate  = 22050
        num_channels = 1
        sample_width = 2  # 16-bit
        n_frames     = int(sample_rate * max(0.1, duration))
        data_size    = n_frames * num_channels * sample_width

        with open(output_path, "wb") as f:
            # RIFF header
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + data_size))
            f.write(b"WAVE")
            # fmt chunk
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))           # chunk size
            f.write(struct.pack("<H", 1))            # PCM
            f.write(struct.pack("<H", num_channels))
            f.write(struct.pack("<I", sample_rate))
            f.write(struct.pack("<I", sample_rate * num_channels * sample_width))  # byte rate
            f.write(struct.pack("<H", num_channels * sample_width))                # block align
            f.write(struct.pack("<H", sample_width * 8))                           # bits per sample
            # data chunk
            f.write(b"data")
            f.write(struct.pack("<I", data_size))
            f.write(b"\x00" * data_size)

        return {
            "scene_id": scene_id,
            "path":     str(output_path),
            "filename": output_path.name,
            "duration": round(duration, 2),
            "silence":  True,
        }

    async def generate_scene_audio(self, scene_id: Any, text: str) -> Dict[str, Any]:
        text_hash = self._hash_text(text)
        cached = self.check_cache(text_hash, scene_id)
        if cached:
            self.logger.info(f"Cache hit for scene {scene_id} audio")
            return cached

        output_path = self.audio_dir / f"scene_{int(scene_id):03d}.wav"
        await self._run_piper(text, output_path)

        duration = _wav_duration(output_path)
        result = {
            "scene_id": scene_id,
            "path": str(output_path),
            "filename": output_path.name,
            "duration": round(duration, 2),
            "text_hash": text_hash,
        }

        # Write cache
        cache_file = self.cache_dir / f"{text_hash}.json"
        with open(cache_file, "w") as f:
            json.dump(result, f)

        return result

    async def _run_piper(self, text: str, output_path: Path) -> None:
        cmd = [self.piper_executable]
        if self.model_path:
            cmd.extend(["--model", self.model_path])
        cmd.extend(["--output_file", str(output_path)])
        if self.speed != 1.0:
            cmd.extend(["--length_scale", str(1.0 / self.speed)])

        self.logger.info(f"Running Piper: {' '.join(cmd)}")

        loop = asyncio.get_event_loop()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=text.encode("utf-8")),
                timeout=120.0,
            )
            if proc.returncode != 0:
                raise ServiceError(
                    self.service_name,
                    f"Piper exited with code {proc.returncode}",
                    detail=stderr.decode("utf-8", errors="replace"),
                )
        except asyncio.TimeoutError:
            raise ServiceError(self.service_name, f"Piper timed out for scene audio")

        self.logger.info(f"Piper generated: {output_path}")

    async def _run_piper_batch(self, texts: List[str], output_dir: Path) -> List[Path]:
        """Run Piper once for all texts using --output_dir.

        Piper writes one WAV per stdin line.  We sort outputs by mtime so the
        returned list is in the same order as *texts*.
        """
        cmd = [self.piper_executable]
        if self.model_path:
            cmd.extend(["--model", self.model_path])
        cmd.extend(["--output_dir", str(output_dir)])
        if self.speed != 1.0:
            cmd.extend(["--length_scale", str(1.0 / self.speed)])

        joined = "\n".join(texts)
        self.logger.info("Piper batch: %d lines -> %s", len(texts), output_dir)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=joined.encode("utf-8")),
            timeout=600.0,
        )
        if proc.returncode != 0:
            raise ServiceError(
                self.service_name,
                "Piper batch TTS failed",
                detail=stderr.decode("utf-8", errors="replace"),
            )
        # Sort by creation-time nanoseconds — matches input order
        return sorted(output_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime_ns)

    async def generate_section_voice(
        self,
        section_label: str,
        section_scenes_path: Optional[Path] = None,
        section_script_text: str = "",
    ) -> Dict[str, Any]:
        """Generate narration audio for one AI News section.

        Source priority:
          1. section_scenes_path (input/sections/{label}/scenes.json) — per-scene WAVs
          2. section_script_text (raw [NARRATOR] text from script.md) — single WAV

        Output:
          audio/sections/{label}/scene_NNN.wav  (one per scene/chunk)
          audio/sections/{label}/narration.wav  (concatenated)
        """
        sec_audio = self.audio_dir / "sections" / section_label
        sec_audio.mkdir(parents=True, exist_ok=True)

        # Build (id, text) pairs
        narr_chunks: List[Dict[str, Any]] = []
        if section_scenes_path and section_scenes_path.exists():
            with open(section_scenes_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data if isinstance(data, list) else data.get("scenes", [])
            narr_chunks = [
                {"id": s.get("scene_id", i + 1), "text": s.get("narration", "").strip()}
                for i, s in enumerate(raw)
                if s.get("narration", "").strip()
            ]
        elif section_script_text:
            narr_chunks = [{"id": 1, "text": section_script_text.strip()}]

        if not narr_chunks:
            raise ServiceError(
                self.service_name,
                f"No narration text found for section '{section_label}'"
            )

        generated: List[Dict[str, Any]] = []
        total = len(narr_chunks)

        # Resume logic: reuse existing WAVs only for interrupted (partial) runs.
        # If ALL expected WAVs exist, scenes may have been edited since the last
        # run → clear them so stale audio is never reused in narration.wav.
        existing_wavs = [
            sec_audio / f"scene_{int(c['id']):03d}.wav" for c in narr_chunks
        ]
        all_exist = all(w.exists() and w.stat().st_size > 0 for w in existing_wavs)
        if all_exist:
            for w in existing_wavs:
                w.unlink(missing_ok=True)
            narr_wav = sec_audio / "narration.wav"
            narr_wav.unlink(missing_ok=True)

        pending_chunks: List[Dict[str, Any]] = []
        for chunk in narr_chunks:
            out_wav = sec_audio / f"scene_{int(chunk['id']):03d}.wav"
            if out_wav.exists() and out_wav.stat().st_size > 0:
                generated.append({
                    "scene_id": chunk["id"],
                    "path":     str(out_wav),
                    "filename": out_wav.name,
                    "duration": _wav_duration(out_wav),
                })
            else:
                pending_chunks.append(chunk)

        if pending_chunks:
            await self.report_progress(
                len(generated) / total * 100,
                f"Running Piper for {len(pending_chunks)} chunk(s) in one batch…",
                {"completed": len(generated), "total": total},
            )
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    wav_paths = await self._run_piper_batch(
                        [c["text"] for c in pending_chunks], Path(tmp_dir)
                    )
                    for i, chunk in enumerate(pending_chunks):
                        if i >= len(wav_paths):
                            self.logger.error(
                                "Piper produced no output for %s chunk %d",
                                section_label, chunk["id"],
                            )
                            continue
                        dest = sec_audio / f"scene_{int(chunk['id']):03d}.wav"
                        shutil.copy2(wav_paths[i], dest)
                        generated.append({
                            "scene_id": chunk["id"],
                            "path":     str(dest),
                            "filename": dest.name,
                            "duration": _wav_duration(dest),
                        })
                        await self.report_progress(
                            len(generated) / total * 100,
                            f"Section voice {len(generated)}/{total}",
                            {"scene_id": chunk["id"], "completed": len(generated), "total": total},
                        )
            except Exception as exc:
                self.logger.error("Piper batch failed for %s: %s", section_label, exc)
                raise ServiceError(
                    self.service_name,
                    f"Piper batch TTS failed for section '{section_label}': {exc}",
                )

        # Concatenate all scene WAVs → narration.wav
        narr_path: Optional[Path] = None
        if generated:
            sorted_gen = sorted(generated, key=lambda x: x.get("scene_id", 0))
            file_list = sec_audio / "file_list.txt"
            file_list.write_text(
                "\n".join(f"file '{g['path']}'" for g in sorted_gen),
                encoding="utf-8",
            )
            merged = sec_audio / "narration.wav"
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(file_list), "-c", "copy", str(merged),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            if proc.returncode == 0:
                narr_path = merged
            else:
                self.logger.error("Section audio merge failed: %s", stderr.decode())

        total_dur = sum(g.get("duration", 0.0) for g in generated)
        await self.report_progress(
            100,
            f"Section '{section_label}' voice done — {len(generated)}/{total} chunks",
        )
        return {
            "label":          section_label,
            "chunks":         total,
            "generated":      len(generated),
            "total_duration": round(total_dur, 2),
            "narration_wav":  str(narr_path) if narr_path else None,
        }

    async def merge_audio_files(self, audio_files: List[Dict[str, Any]]) -> Optional[Path]:
        if not audio_files:
            return None

        sorted_files = sorted(audio_files, key=lambda x: x.get("scene_id", 0))
        file_list_path = self.audio_dir / "file_list.txt"
        merged_path = self.audio_dir / "narration_merged.wav"

        with open(file_list_path, "w") as f:
            for af in sorted_files:
                f.write(f"file '{af['path']}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(file_list_path),
            "-c", "copy",
            str(merged_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            if proc.returncode != 0:
                self.logger.error(f"FFmpeg merge failed: {stderr.decode()}")
                return None
        except Exception as exc:
            self.logger.error(f"Audio merge failed: {exc}")
            return None

        self.logger.info(f"Merged audio: {merged_path}")
        return merged_path
