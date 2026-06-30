"""
AiNewsSectionService — generates per-section scenes.json and image_prompts.txt
for all 12 sections of an AI News script.

Priority order (no unnecessary Gemini calls):
  1. Split existing input/scenes.json         → per-section scenes.json
  2. Split existing input/image_prompts.txt   → per-section image_prompts.txt
  3. If either file is missing, call Gemini ONCE for all sections (batch).

Output layout:
  input/sections/{label}/scenes.json
  input/sections/{label}/image_prompts.txt
"""
from __future__ import annotations

import json as _json
import re
from typing import Any, Dict, List, Optional, Set

from app.services.content_service import ContentGenerationService
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Gemini prompts (used only when global files don't exist) ──────────────────

_ALL_SECTIONS_SCENES_PROMPT = """\
You are an expert video production planner for AI news content.

Create a COMPLETE scene breakdown for ALL sections of this AI news video.

FULL SCRIPT:
{script}

SECTIONS TO COVER (use these exact label values in your output):
{section_labels}

REQUIREMENTS:
- Create scenes for EVERY section listed above
- Introduction (intro): 2-4 scenes
- Story sections (story_01 through story_10): 4-8 scenes each
- Outro: 2-4 scenes
- Each scene lasts 5-10 seconds
- scene_id RESETS TO 1 for each new section_label
- image_file uses the section-local scene_id: scene_001.png, scene_002.png, ...

OUTPUT: A single JSON array with ALL scenes for ALL sections.
Every scene object MUST include "section_label".

[
  {
    "section_label": "intro",
    "scene_id": 1,
    "section": "Introduction",
    "duration": 8,
    "image_file": "scene_001.png",
    "title": "Scene title",
    "visual_description": "What to show on screen (always in English)",
    "narration": "Exact narrator words from the script"
  }
]

Return the JSON array ONLY — no markdown fences, no explanations."""

_ALL_SECTIONS_IMAGE_PROMPTS_FLUX = """\
You are an award-winning cinematic concept artist specializing in FLUX Dev diffusion model prompts.

Generate one FLUX Dev image prompt for EVERY scene across ALL sections.

INPUT SCENES (JSON — includes section_label on every scene):
{scenes_json}

IMAGE STYLE:
Photorealistic, Documentary, Cinematic, Ultra detailed, Professional photography,
Volumetric lighting, Realistic textures, Modern technology aesthetic, 16:9 composition, 4K quality

CRITICAL FLUX DEV PROMPT RULES:
1. START with the EXACT subject/scene being depicted — never start with style adjectives
2. Describe what is literally VISIBLE (objects, people, settings, actions)
3. Use photographic language: camera angle, lighting direction, depth of field
4. Style descriptors go ONLY at the end
5. Never open with: stunning, beautiful, epic, minimalist, dramatic
6. Each prompt: 40-80 words

OUTPUT FORMAT — group scenes under SECTION: {label} headers:

SECTION: intro
SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [FLUX prompt]

SCENE_002
IMAGE_FILE: scene_002.png
PROMPT: [FLUX prompt]

SECTION: story_01
SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [FLUX prompt]

Cover ALL sections and ALL scenes in order. No explanations, no skipping."""

_ALL_SECTIONS_IMAGE_PROMPTS_GEMINI = """\
You are a creative director specializing in AI image generation with Google Gemini.

Generate one image prompt for EVERY scene across ALL sections.

INPUT SCENES (JSON — includes section_label on every scene):
{scenes_json}

GUIDELINES:
- Rich, descriptive prompts: mood, atmosphere, narrative, lighting, color palette
- Natural expressive language — Gemini understands context and nuance
- 30-60 words per prompt
- Style: photorealistic documentary, cinematic, 16:9, YouTube quality
- Each scene must feel visually distinct

OUTPUT FORMAT — group scenes under SECTION: {label} headers:

SECTION: intro
SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [Gemini prompt]

SCENE_002
IMAGE_FILE: scene_002.png
PROMPT: [Gemini prompt]

SECTION: story_01
SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [Gemini prompt]

Cover ALL sections and ALL scenes in order. No explanations."""

_SECTION_IMAGE_PROMPTS_FLUX = """\
You are an award-winning cinematic concept artist specializing in FLUX Dev diffusion model prompts.

Generate exactly {scene_count} FLUX Dev image prompts — one for each scene below. No more, no less.

SECTION: {label}
INPUT SCENES (JSON):
{scenes_json}

IMAGE STYLE:
Photorealistic, Documentary, Cinematic, Ultra detailed, Professional photography,
Volumetric lighting, Realistic textures, Modern technology aesthetic, 16:9 composition, 4K quality

CRITICAL FLUX DEV PROMPT RULES:
1. START with the EXACT subject/scene being depicted — never start with style adjectives
2. Describe what is literally VISIBLE (objects, people, settings, actions)
3. Use photographic language: camera angle, lighting direction, depth of field
4. Style descriptors go ONLY at the end
5. Never open with: stunning, beautiful, epic, minimalist, dramatic
6. Each prompt: 40-80 words

OUTPUT FORMAT (exactly {scene_count} entries, no extras):

SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [FLUX prompt]

SCENE_002
IMAGE_FILE: scene_002.png
PROMPT: [FLUX prompt]

Output only these {scene_count} entries. No section header, no explanations."""

_SECTION_IMAGE_PROMPTS_GEMINI = """\
You are a creative director specializing in AI image generation with Google Gemini.

Generate exactly {scene_count} image prompts — one for each scene below. No more, no less.

SECTION: {label}
INPUT SCENES (JSON):
{scenes_json}

GUIDELINES:
- Rich, descriptive prompts: mood, atmosphere, narrative, lighting, color palette
- Natural expressive language — Gemini understands context and nuance
- 30-60 words per prompt
- Style: photorealistic documentary, cinematic, 16:9, YouTube quality
- Each scene must feel visually distinct

OUTPUT FORMAT (exactly {scene_count} entries, no extras):

SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [Gemini prompt]

SCENE_002
IMAGE_FILE: scene_002.png
PROMPT: [Gemini prompt]

Output only these {scene_count} entries. No section header, no explanations."""


class AiNewsSectionService(ContentGenerationService):
    """Generates per-section scenes.json and image_prompts.txt for AI News projects."""

    # ── Script parsing ─────────────────────────────────────────────────────────

    @staticmethod
    def parse_script_sections(script: str) -> List[Dict[str, Any]]:
        """Parse script.md into ordered section dicts.

        Returns list of {"num", "title", "label", "type", "script"}.
        """
        pattern = re.compile(r"^SECTION\s+(\d+)[:\s—–-]+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(script))
        if not matches:
            return []

        sections: List[Dict[str, Any]] = []
        script_len = len(script)
        for i, m in enumerate(matches):
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else script_len
            sec_num = int(m.group(1))
            title   = m.group(2).strip()
            text    = script[m.start():end_pos].strip()

            if sec_num == 1:
                label, sec_type = "intro", "intro"
            elif sec_num == 12:
                label, sec_type = "outro", "outro"
            else:
                story_num = sec_num - 1
                label, sec_type = f"story_{story_num:02d}", "story"

            sections.append({
                "num":    sec_num,
                "title":  title,
                "label":  label,
                "type":   sec_type,
                "script": text,
            })

        return sections

    # ── Main entry point ───────────────────────────────────────────────────────

    async def generate_all_sections(
        self,
        script: str,
        image_backend: str = "flux",
    ) -> List[Dict[str, Any]]:
        """Generate scenes.json + image_prompts.txt for all sections.

        If input/scenes.json already exists it is split into per-section files
        (zero Gemini calls for scenes).  Same for input/image_prompts.txt.
        Gemini is called ONLY for whichever file is missing — and then only
        once for all sections combined (two calls maximum total).
        """
        sections = self.parse_script_sections(script)
        if not sections:
            self.logger.warning("No SECTION headers found in script.md — nothing generated")
            return []

        valid_labels: Set[str] = {s["label"] for s in sections}
        scenes_by_label: Dict[str, List[Dict[str, Any]]] = {s["label"]: [] for s in sections}

        # ── Step 1: scenes.json ───────────────────────────────────────────────
        global_scenes_path = self.input_dir / "scenes.json"

        if global_scenes_path.exists():
            await self._safe_report(5, "Splitting global scenes.json into sections…", "scenes")
            try:
                raw_scenes: List[Dict[str, Any]] = _json.loads(
                    global_scenes_path.read_text(encoding="utf-8")
                )
                scenes_by_label = self._split_scenes_by_section(script, sections, raw_scenes)
                self.logger.info(
                    "Split %d global scenes across %d sections",
                    len(raw_scenes), len(sections),
                )
            except Exception as exc:
                self.logger.error("Failed to split global scenes.json: %s — will call Gemini", exc)
                scenes_by_label = {s["label"]: [] for s in sections}

        # If still empty (file missing or split failed) → call Gemini once
        if not any(scenes_by_label.values()):
            await self._safe_report(5, f"Generating scenes for all {len(sections)} sections…", "scenes")
            scenes_by_label = await self._gemini_scenes(script, sections)

        # Write per-section scenes.json (strip internal _orig_id helper field)
        for sec in sections:
            lbl = sec["label"]
            sec_scenes = scenes_by_label.get(lbl, [])
            if sec_scenes:
                sec_dir = self.input_dir / "sections" / lbl
                sec_dir.mkdir(parents=True, exist_ok=True)
                clean = [{k: v for k, v in s.items() if k != "_orig_id"} for s in sec_scenes]
                (sec_dir / "scenes.json").write_text(
                    _json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                self.logger.info("  %s/scenes.json — %d scenes", lbl, len(sec_scenes))
            else:
                self.logger.warning("  %s — no scenes", lbl)

        await self._safe_report(50, "Scenes written for all sections", "ai_news_section")

        # ── Step 2: image_prompts.txt ─────────────────────────────────────────
        global_prompts_path = self.input_dir / "image_prompts.txt"
        prompts_by_label: Dict[str, str] = {}  # label → formatted text

        if global_prompts_path.exists() and any(scenes_by_label.values()):
            await self._safe_report(55, "Splitting global image_prompts.txt into sections…", "image_prompts")
            try:
                global_prompts_text = global_prompts_path.read_text(encoding="utf-8")
                prompts_by_label = self._split_prompts_by_section(global_prompts_text, scenes_by_label)
                self.logger.info("Split global image_prompts.txt into %d sections", len(prompts_by_label))
            except Exception as exc:
                self.logger.error("Failed to split global image_prompts.txt: %s — will call Gemini", exc)

        # If still empty → call Gemini flash once for all sections
        if not prompts_by_label:
            await self._safe_report(55, f"Generating image prompts for all {len(sections)} sections…", "image_prompts")
            prompts_by_label = await self._gemini_prompts(scenes_by_label, valid_labels, image_backend)

        # Write per-section image_prompts.txt
        for sec in sections:
            lbl = sec["label"]
            text = prompts_by_label.get(lbl, "")
            if text:
                sec_dir = self.input_dir / "sections" / lbl
                sec_dir.mkdir(parents=True, exist_ok=True)
                (sec_dir / "image_prompts.txt").write_text(text, encoding="utf-8")
                self.logger.info("  %s/image_prompts.txt saved", lbl)
            else:
                self.logger.warning("  %s — no image prompts", lbl)

        await self._safe_report(100, "All sections complete", "ai_news_section")

        return [
            {
                "label":             sec["label"],
                "type":              sec["type"],
                "title":             sec["title"],
                "has_scenes":        bool(scenes_by_label.get(sec["label"])),
                "has_image_prompts": bool(prompts_by_label.get(sec["label"])),
            }
            for sec in sections
        ]

    # ── Split helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _split_scenes_by_section(
        script: str,
        sections: List[Dict[str, Any]],
        global_scenes: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Distribute global scenes into per-section buckets.

        Matching priority:
          0. scene["section_label"]   — already tagged (Gemini-generated sections)
          1. scene["story_number"]    — set by AiNewsService._assign_story_numbers
          2. Exact scene["section"] title match (case-insensitive)
          3. Partial title match (one contains the other)
          4. Narrator word-overlap against the section script text

        scene_id and image_file are re-numbered locally (1-based) per section.
        A hidden _orig_id field is kept for prompt splitting.
        """
        # Build lookup tables
        label_set: Set[str] = {sec["label"] for sec in sections}

        # story_number → label (for AI news: story_number=1..10 → story_01..story_10)
        story_num_to_label: Dict[int, str] = {}
        intro_label = "intro"
        outro_label = "outro"
        for sec in sections:
            if sec.get("type") == "story":
                sn = sec["num"] - 1  # SECTION 2 → story_num 1, SECTION 11 → story_num 10
                story_num_to_label[sn] = sec["label"]
            elif sec.get("type") == "intro":
                intro_label = sec["label"]
            elif sec.get("type") == "outro":
                outro_label = sec["label"]

        # For story_number=0 disambiguation: scenes after the last story scene → outro
        story_scene_indices = [
            i for i, sc in enumerate(global_scenes) if (sc.get("story_number") or 0) > 0
        ]
        last_story_idx = max(story_scene_indices) if story_scene_indices else -1

        # Normalised title → label
        title_map: Dict[str, str] = {
            sec["title"].lower().strip(): sec["label"] for sec in sections
        }

        # Narrator word-sets for overlap fallback
        narrator_words: Dict[str, Set[str]] = {}
        for sec in sections:
            blocks = re.findall(
                r'\[NARRATOR\]\s*([\s\S]*?)(?=\[VISUAL\]|\[NARRATOR\]|^SECTION\s+\d+|\Z)',
                sec["script"], re.MULTILINE,
            )
            text = " ".join(blocks) if blocks else sec["script"]
            narrator_words[sec["label"]] = set(re.findall(r'\w+', text.lower()))

        result: Dict[str, List[Dict[str, Any]]] = {sec["label"]: [] for sec in sections}
        default_label = sections[0]["label"]

        for idx, scene in enumerate(global_scenes):
            label: Optional[str] = None

            # 0. Explicit section_label (e.g. from Gemini-generated per-section scenes)
            explicit = scene.get("section_label", "")
            if explicit and explicit in label_set:
                label = explicit

            # 1. story_number field (set by AiNewsService._assign_story_numbers)
            if not label:
                story_num = scene.get("story_number")
                if story_num is not None:
                    if story_num > 0:
                        label = story_num_to_label.get(story_num)
                    else:
                        # 0 = intro OR outro — use position to disambiguate
                        label = outro_label if idx > last_story_idx else intro_label
                    if label and label not in label_set:
                        label = None

            # 2. Exact title match
            if not label:
                scene_sec = str(scene.get("section", "")).lower().strip()
                label = title_map.get(scene_sec)

            # 3. Partial title match
            if not label:
                scene_sec = str(scene.get("section", "")).lower().strip()
                for title, lbl in title_map.items():
                    if scene_sec and (scene_sec in title or title in scene_sec):
                        label = lbl
                        break

            # 4. Narrator word-overlap
            if not label:
                scene_words = set(re.findall(r'\w+', str(scene.get("narration", "")).lower()))
                best_lbl, best_score = default_label, 0
                for lbl, words in narrator_words.items():
                    score = len(scene_words & words)
                    if score > best_score:
                        best_score, best_lbl = score, lbl
                label = best_lbl

            scene_copy = dict(scene)
            scene_copy["_orig_id"] = scene.get("scene_id")
            result.setdefault(label, []).append(scene_copy)

        # Re-number locally per section
        for lbl, scenes in result.items():
            for local_id, s in enumerate(scenes, 1):
                s["scene_id"]   = local_id
                s["image_file"] = f"scene_{local_id:03d}.png"
                s["section_label"] = lbl

        return result

    @staticmethod
    def _split_prompts_by_section(
        global_prompts_text: str,
        scenes_by_label: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, str]:
        """Build per-section image_prompts.txt content from the global file.

        Uses the _orig_id stored by _split_scenes_by_section to map each
        per-section scene back to its original SCENE_NNN prompt.
        Returns {label: formatted_prompts_text}.
        """
        # Parse global prompts: {orig_scene_id: prompt_string}
        global_prompts: Dict[int, str] = {}
        current_id: Optional[int] = None
        for line in global_prompts_text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("SCENE_"):
                try:
                    current_id = int(stripped.split("_", 1)[1])
                except (IndexError, ValueError):
                    current_id = None
            elif stripped.upper().startswith("PROMPT:") and current_id is not None:
                p = stripped[7:].strip()
                if p:
                    global_prompts[current_id] = p
                current_id = None

        # Fallback: if no SCENE_NNN markers, treat each non-empty line as a prompt
        if not global_prompts:
            plain = [ln.strip() for ln in global_prompts_text.splitlines() if ln.strip()]
            global_prompts = {i + 1: p for i, p in enumerate(plain)}

        result: Dict[str, str] = {}
        for label, scenes in scenes_by_label.items():
            lines: List[str] = []
            for s in scenes:
                local_id = s["scene_id"]
                orig_id  = s.get("_orig_id", local_id)
                prompt   = global_prompts.get(orig_id, "")
                if prompt:
                    lines += [
                        f"SCENE_{local_id:03d}",
                        f"IMAGE_FILE: scene_{local_id:03d}.png",
                        f"PROMPT: {prompt}",
                        "",
                    ]
            if lines:
                result[label] = "\n".join(lines).strip()

        return result

    # ── Gemini batch fallbacks ────────────────────────────────────────────────

    async def _gemini_scenes(
        self,
        script: str,
        sections: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """One pro-model call → all scenes for all sections, split by section_label."""
        section_labels_text = "\n".join(
            f'  {s["label"]} → "{s["title"]}" (SECTION {s["num"]})'
            for s in sections
        )
        prompt = (
            _ALL_SECTIONS_SCENES_PROMPT
            .replace("{script}", script)
            .replace("{section_labels}", section_labels_text)
        )
        raw = await self._call(prompt, model_name=self.pro_model, thinking_budget=0)
        all_scenes: List[Dict[str, Any]] = _json.loads(self._extract_json(raw))
        if not isinstance(all_scenes, list):
            raise ValueError("Expected a JSON array of scenes")

        self.logger.info("Gemini returned %d scenes for all sections", len(all_scenes))

        valid = {s["label"] for s in sections}
        result: Dict[str, List[Dict[str, Any]]] = {s["label"]: [] for s in sections}
        for scene in all_scenes:
            lbl = str(scene.get("section_label", "")).strip()
            if lbl in valid:
                result[lbl].append(dict(scene))

        # Ensure scene_ids are locally numbered
        for lbl, scenes in result.items():
            for i, s in enumerate(scenes, 1):
                s["scene_id"]   = i
                s["image_file"] = f"scene_{i:03d}.png"

        return result

    async def _gemini_prompts(
        self,
        scenes_by_label: Dict[str, List[Dict[str, Any]]],
        valid_labels: Set[str],
        image_backend: str,
    ) -> Dict[str, str]:
        """Generate image prompts per section (one Gemini call per section).

        Calling per-section instead of as a single 57-scene batch guarantees
        that the model sees exactly N scenes and must output exactly N prompts —
        eliminating count mismatches caused by batch-mode hallucination.
        """
        use_gemini_backend = image_backend.lower() == "gemini"
        tmpl = _SECTION_IMAGE_PROMPTS_GEMINI if use_gemini_backend else _SECTION_IMAGE_PROMPTS_FLUX

        result: Dict[str, str] = {}
        for label, scenes in scenes_by_label.items():
            if not scenes or label not in valid_labels:
                continue

            scene_count = len(scenes)
            clean_scenes = [{k: v for k, v in s.items() if k != "_orig_id"} for s in scenes]
            prompt = (
                tmpl
                .replace("{label}", label)
                .replace("{scene_count}", str(scene_count))
                .replace("{scenes_json}", _json.dumps(clean_scenes, ensure_ascii=False))
            )
            try:
                raw = await self._call(prompt, model_name=self.flash_model)
            except Exception as exc:
                self.logger.error("_gemini_prompts: %s — Gemini call failed: %s", label, exc)
                continue

            # Parse the per-section output (no SECTION: headers — just SCENE_NNN entries)
            lines: List[str] = []
            current_scene: Optional[str] = None
            current_file:  Optional[str] = None
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("SCENE_"):
                    current_scene = stripped
                    current_file  = None
                elif stripped.upper().startswith("IMAGE_FILE:"):
                    current_file = stripped
                elif stripped.upper().startswith("PROMPT:"):
                    p = stripped[7:].strip()
                    if p:
                        lines += [current_scene or "", current_file or "", f"PROMPT: {p}", ""]
                        current_scene = current_file = None

            # Enforce exact scene count — truncate any extras
            scene_header_indices = [
                i for i, ln in enumerate(lines) if ln.strip().upper().startswith("SCENE_")
            ]
            if len(scene_header_indices) > scene_count:
                self.logger.warning(
                    "_gemini_prompts: %s — got %d prompts for %d scenes, truncating",
                    label, len(scene_header_indices), scene_count,
                )
                cutoff = scene_header_indices[scene_count]
                lines = lines[:cutoff]

            if lines:
                result[label] = "\n".join(lines).strip()
                self.logger.info("  %s: %d/%d prompts generated", label, len(scene_header_indices[:scene_count]), scene_count)
            else:
                self.logger.warning("  %s: no prompts parsed from Gemini response", label)

        return result

    @staticmethod
    def _extract_all_section_prompts(
        text: str,
        valid_labels: Set[str],
    ) -> Dict[str, str]:
        """Parse SECTION: {label} / SCENE_NNN / PROMPT: output into per-label text blobs."""
        buckets: Dict[str, List[str]] = {}
        current_label: Optional[str] = None
        current_scene: Optional[str] = None
        current_file:  Optional[str] = None

        for line in text.splitlines():
            stripped = line.strip()

            if stripped.upper().startswith("SECTION:"):
                candidate = stripped[8:].strip().lower()
                if candidate in valid_labels:
                    current_label = candidate
                    buckets.setdefault(current_label, [])
                continue

            if current_label is None:
                continue

            if stripped.upper().startswith("SCENE_"):
                current_scene = stripped
                current_file  = None
            elif stripped.upper().startswith("IMAGE_FILE:"):
                current_file = stripped
            elif stripped.upper().startswith("PROMPT:"):
                p = stripped[7:].strip()
                if p:
                    scene_line = current_scene or ""
                    file_line  = current_file  or ""
                    buckets[current_label] += [scene_line, file_line, f"PROMPT: {p}", ""]
                current_scene = current_file = None

        return {lbl: "\n".join(lines).strip() for lbl, lines in buckets.items() if lines}

    # ── Utility ────────────────────────────────────────────────────────────────

    async def _safe_report(self, progress: float, message: str, step: str) -> None:
        """Call _report without ever letting a WS failure break the generation loop."""
        try:
            await self._report(progress, message, step)
        except Exception:
            pass
