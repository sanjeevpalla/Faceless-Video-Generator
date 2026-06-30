"""
ContentGenerationService — auto-generates all 5 project input files via Gemini API.

Pipeline:
  Step 1: Trend Discovery        (pro_model   — gemini-2.5-flash + Google Search)
  Step 2: Research + Fact Check  (pro_model   — gemini-2.5-flash + Google Search)
  Step 3: Script Generation      (script_model — gemma-4-31b-it, heavy reasoning)
  Step 4: Scenes JSON            (script_model — gemma-4-31b-it, large JSON array)
  Step 5: Image Prompts          (flash_model  — gemini-3.1-flash-lite, plain text)
  Step 6: Thumbnail Prompt       (flash_model  — gemini-3.1-flash-lite, plain text)
  Step 7: SEO Metadata           (script_model — gemma-4-31b-it, JSON object)

JSON-output steps (4, 7) use the larger script_model because gemini-3.1-flash-lite
cannot reliably generate deeply nested / large JSON without MALFORMED_FUNCTION_CALL errors.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Prompts (verbatim from user's workflow docx files) ─────────────────────────

_TREND_PROMPT = """You are an expert AI industry analyst, technology journalist, venture capital researcher, and YouTube growth strategist.

TODAY'S DATE: {today}

TASK: Identify the most important AI-related developments from the last 24 hours (since {yesterday}).
Use Google Search to find real, current news published on or after {yesterday}. Do NOT use training data — only use live search results.

Focus on: Artificial Intelligence, OpenAI, Google Gemini, Anthropic Claude, Microsoft AI, NVIDIA, AI Startups, Robotics, AGI, AI Agents, AI Video Generation, AI Coding, AI Research, AI Safety, AI Hardware, AI Investments, AI Acquisitions, AI Product Launches

REQUIREMENTS:
Find 20 trending AI topics from the last 24 hours.
Calculate Overall Opportunity Score using: 40% YouTube Opportunity + 25% Virality + 20% Search Demand + 15% Longevity

OUTPUT — use this exact Markdown format:

## 📊 AI Trending Topics — {today}

| Rank | Topic | Summary | Source | Search | Virality | YT Opp | Longevity | Score |
|------|-------|---------|--------|--------|----------|--------|-----------|-------|
| 1 | **Topic Title** | One-line summary | [Publisher Name][1] | 9 | 9 | 10 | 9 | 9.40 |
| 2 | **Topic Title** | One-line summary | [Publisher Name][2] | 8 | 8 | 9 | 8 | 8.30 |

Rules for Source column:
- Use reference style: [Publisher Name][N] where N is a sequential number starting from 1
- Each row gets its own unique number
- Publisher name is the outlet that published the article (e.g. TechCrunch, The Verge, Reuters)
- Do NOT write raw URLs anywhere in your response

(continue for all 20 topics)

---

## 🏆 Top 5 Recommended Topics for {channel}

For each of the top 5, use this exact format (add a blank line after each entry):

### 1. Topic Title

- **Why it will perform well:** 1-2 sentences
- **Suggested video title:** catchy YouTube title
- **Thumbnail text:** 3-5 words max
- **Audience interest:** High / Very High / Viral
- **RPM potential:** $X–$Y
- **Competition:** Low / Medium / High
- **Source:** [Publisher Name][N] (use the same reference number from the table above)

(repeat for entries 2–5, each starting with ### N. Topic Title)

---

## ⭐ Best Topic of the Day

State the topic and explain in 2-3 sentences why it is the strongest choice for a faceless AI documentary channel today.

IMPORTANT: Do NOT write raw URLs anywhere — source links are injected automatically from your search results. Prioritize: Breaking news, Product launches, Industry shifts, Controversial developments, Billion-dollar investments, Government actions, AI breakthroughs. Avoid: Generic AI tutorials, Low-impact updates, Recycled stories."""

_RESEARCH_PROMPT = """You are an investigative technology journalist, AI researcher, fact-checking specialist, and documentary researcher.

TOPIC: {topic}

TASK: Create a complete research dossier for a YouTube documentary.

RESEARCH REQUIREMENTS:
Use the most authoritative sources available. Priority order: Official company announcements, Research papers, Government publications, Academic sources, Industry reports, Reputable news organizations.

RESEARCH OUTPUT:

SECTION 1 - EXECUTIVE SUMMARY
Summarize the topic in simple language.

SECTION 2 - KEY FACTS
List all major facts.
Format: Fact: | Source: | Confidence:

SECTION 3 - TIMELINE
Chronological timeline of events.
Format: Date: | Event: | Importance:

SECTION 4 - IMPORTANT PEOPLE
List major individuals involved.
Format: Name: | Role: | Why Important:

SECTION 5 - ORGANIZATIONS
List major organizations involved.
Format: Organization: | Role: | Importance:

SECTION 6 - CLAIM VERIFICATION
Identify all significant claims.
For each claim: Claim: | Evidence: | Supporting Sources: | Contradicting Sources: | Confidence Score (1-10):

SECTION 7 - RISKS
Identify: Technical risks, Security risks, Business risks, Ethical risks, Regulatory risks.

SECTION 8 - MISCONCEPTIONS
Identify common misunderstandings.
Format: Myth: | Reality:

SECTION 9 - YOUTUBE STORY ANGLES
Generate 10 possible documentary angles. Rank all 10.

SECTION 10 - FINAL FACT CHECK SUMMARY
Create: Verified Facts | Likely True | Unconfirmed | Speculation | Rumors

IMPORTANT: Do not create a script. Do not create image prompts. Do not create scenes. Only produce a research dossier and fact-check report."""

_SCRIPT_PROMPT = """You are an award-winning documentary writer, YouTube storytelling expert, and professional scriptwriter for high-retention faceless channels.

CHANNEL: {channel}

TASK: Create a professional YouTube documentary script using ONLY the verified research dossier provided below.

RESEARCH DOSSIER:
{research}

OBJECTIVES:
Transform the research into an engaging, easy-to-understand documentary.
Do not perform additional research. Do not invent facts. Do not add unsupported claims.
If information in the dossier is marked as uncertain, present it as uncertain.

SCRIPT REQUIREMENTS:
Target Length: 2500 - 4000 words
Target Runtime: 8-12 minutes
Audience: Technology enthusiasts, AI professionals, Developers, Students, General viewers
Style: Documentary, Professional, Engaging, High-retention, Story-driven, Curiosity-driven, Easy to understand

PACING: Use Strong opening hook, Open loops, Curiosity gaps, Smooth transitions, Narrative tension, Memorable conclusions.
Avoid: Clickbait, Excessive hype, Repetition, Technical jargon without explanation.

SCRIPT STRUCTURE: Hook -> Background -> Core Explanation -> Major Developments -> Risks and Challenges -> Future Impact -> Key Takeaways -> Call To Action

FORMATTING:
TITLE

SECTION 1: HOOK
[VISUAL] Visual description for editor
[NARRATOR] Narration text

Continue for all sections.

VISUAL GUIDELINES:
For every major narration block include [VISUAL] with concise visual guidance under 30 words.
Suitable for: Documentary editing, AI-generated images, Motion graphics, Infographics, Stock footage.

FACTUAL ACCURACY RULES:
Use only information from the research dossier. Clearly distinguish facts from predictions. Clearly identify uncertainties.

OUTPUT RULES:
Generate ONLY the complete production-ready script.
Do not generate: JSON, Image prompts, SEO metadata, Scene breakdowns, Thumbnail ideas."""

_SCENES_PROMPT = """You are an expert film editor, documentary producer, storyboard artist, and video production planner.

Convert the provided YouTube script into a detailed scene-by-scene production plan.

SCRIPT:
{script}

REQUIREMENTS:
- Create 100-120 scenes
- Each scene should last between 5-10 seconds
- Split narration naturally
- Every scene must have: scene_id, section, duration, image_file, title, visual_description, narration

OUTPUT FORMAT:
Return VALID JSON ONLY. No explanations, no markdown code blocks, just a raw JSON array.

Example:
[
  {{
    "scene_id": 1,
    "section": "Hook",
    "duration": 8,
    "image_file": "scene_001.png",
    "title": "Classified Access",
    "visual_description": "High-tech laboratory with digital security overlays",
    "narration": "Right now behind locked digital doors..."
  }}
]

RULES:
- Scene IDs must be sequential starting from 1
- Image files must follow: scene_001.png, scene_002.png, scene_003.png (zero-padded to 3 digits)
- Narration text must exactly match the script
- Duration must be realistic (5-10 seconds per scene)
- Ensure total runtime matches the script length
- Return JSON array only. Do not include explanations."""

_IMAGE_PROMPTS_FLUX = """You are an award-winning cinematic concept artist, documentary filmmaker, and AI image prompt engineer specializing in FLUX Dev diffusion model.

Your task is to generate one image prompt for every scene in the provided JSON.

INPUT SCENES:
{scenes_json}

IMAGE STYLE:
Photorealistic, Documentary, Cinematic, Ultra detailed, Professional photography, Volumetric lighting, Realistic textures, High contrast, Modern technology aesthetic, YouTube documentary quality, 16:9 composition, 4K quality

CRITICAL FLUX DEV PROMPT RULES:
1. START with the EXACT subject/scene being depicted — never start with style adjectives
2. Describe what is literally VISIBLE in the frame (objects, people, settings, actions)
3. Use photographic language: camera angle, lens, lighting direction, time of day, depth of field
4. Style descriptors (cinematic, photorealistic, 4K) go ONLY at the end
5. Never open with: stunning, beautiful, epic, minimalist, dramatic, stark — these confuse FLUX
6. Each prompt must be 40-80 words
7. Be concrete and specific — FLUX responds to visual vocabulary, not abstract concepts

OUTPUT FORMAT (one per scene, no extra text):
SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [FLUX-optimized prompt here]

SCENE_002
IMAGE_FILE: scene_002.png
PROMPT: [FLUX-optimized prompt here]

Generate prompts for ALL scenes. Do not skip any scene. Do not add explanations."""

_IMAGE_PROMPTS_GEMINI = """You are a creative director and visual storyteller specializing in AI image generation with Google Gemini.

Your task is to generate one image prompt for every scene in the provided JSON.

INPUT SCENES:
{scenes_json}

GEMINI IMAGE GENERATION GUIDELINES:
- Write rich, descriptive prompts that convey mood, atmosphere, and narrative
- Describe the scene, subject, setting, lighting, color palette, and emotional tone
- Use natural, expressive language — Gemini understands context and nuance
- Aim for 30-60 words per prompt
- Keep the style: photorealistic documentary, cinematic, 16:9, YouTube quality
- Each scene must feel visually distinct and support the narration

OUTPUT FORMAT (one per scene, no extra text):
SCENE_001
IMAGE_FILE: scene_001.png
PROMPT: [Gemini-optimized prompt here]

SCENE_002
IMAGE_FILE: scene_002.png
PROMPT: [Gemini-optimized prompt here]

Generate prompts for ALL scenes. Do not skip any scene. Do not add explanations."""

# Keep old name as alias so any direct callers still work
_IMAGE_PROMPTS_PROMPT = _IMAGE_PROMPTS_FLUX

_THUMBNAIL_PROMPT = """You are a world-class YouTube thumbnail strategist specializing in AI, technology, and documentary channels.

CHANNEL: {channel}

TASK: Analyze the provided YouTube script and generate a high-CTR thumbnail concept.

SCRIPT:
{script}

REQUIREMENTS:
- Identify the strongest emotional hook
- Identify the most clickable angle
- Create a thumbnail concept that generates curiosity
- Optimize for desktop and mobile viewers
- Avoid clutter
- Use 3-5 words maximum for thumbnail text

OUTPUT FORMAT:
THUMBNAIL_TITLE: Short descriptive name
THUMBNAIL_TEXT: 3-5 words maximum
THUMBNAIL_CONCEPT: Detailed description of the thumbnail composition.
THUMBNAIL_PROMPT: Photorealistic YouTube thumbnail, cinematic lighting, high contrast, technology documentary style, emotionally compelling, ultra detailed, 16:9, professional YouTube thumbnail, [detailed scene description]
COLOR_THEME: Suggested colors
FOCAL_ELEMENTS: Main subjects
EMOTION: Curiosity / Shock / Urgency / Mystery / Excitement

Generate only the thumbnail information."""

_SEO_PROMPT = """You are a professional YouTube SEO strategist specializing in technology and AI channels.

CHANNEL: {channel}

TASK: Generate YouTube SEO metadata from the provided script.

SCRIPT:
{script}

REQUIREMENTS:
Generate:
- Primary SEO Title
- Alternate Titles (10)
- YouTube Description
- Tags
- Hashtags
- Chapters
- Target Keywords
- Search Intent
- CTR Score Estimate

OUTPUT FORMAT (return valid JSON only, no markdown code blocks):
{{
  "title": "",
  "alternate_titles": [],
  "description": "",
  "tags": [],
  "hashtags": [],
  "chapters": [],
  "keywords": [],
  "search_intent": "",
  "ctr_estimate": ""
}}

IMPORTANT: Description should include keywords naturally, be professional, include CTA, be YouTube ready.
Return valid JSON only."""


# ── Service ────────────────────────────────────────────────────────────────────

class ContentGenerationService:

    _LANGUAGE_NAMES: Dict[str, str] = {
        "en": "English",   "te": "Telugu",   "hi": "Hindi",    "ta": "Tamil",
        "kn": "Kannada",   "ml": "Malayalam","bn": "Bengali",  "mr": "Marathi",
        "gu": "Gujarati",  "fr": "French",   "de": "German",   "es": "Spanish",
        "ja": "Japanese",  "ko": "Korean",   "zh": "Chinese (Simplified)",
        "ar": "Arabic",    "pt": "Portuguese","it": "Italian",  "ru": "Russian",
        "ur": "Urdu",
    }

    # When a model returns 503 after all retries, automatically fall back to this model.
    # Fallback chain — triggered when a model returns 503 after all retries.
    _MODEL_FALLBACKS: Dict[str, str] = {
        "gemini-2.5-flash":      "gemini-3.1-flash-lite",
        "gemini-2.5-pro":        "gemini-2.5-flash",
        "gemma-4-31b-it":        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite": "gemma-4-31b-it",
    }

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        api_key: str,
        pro_model: str = "gemini-2.5-flash",
        script_model: str = "gemma-4-31b-it",
        flash_model: str = "gemini-3.1-flash-lite",
        search_grounding: bool = True,
        image_backend: str = "flux",
        language: str = "en",
        channel_name: str = "Deep Dive AI",
        progress_callback: Optional[Callable] = None,
    ) -> None:
        self.project_id = project_id
        self.project_dir = project_dir
        self.api_key = api_key
        self.pro_model = pro_model
        self.script_model = script_model
        self.flash_model = flash_model
        self.search_grounding = search_grounding
        self.image_backend = image_backend
        self.language = language
        self.channel_name = channel_name
        self.progress_callback = progress_callback
        self.input_dir = project_dir / "input"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger(__name__)

    def _lang_name(self) -> str:
        return self._LANGUAGE_NAMES.get(self.language, self.language.upper())

    def _is_english(self) -> bool:
        return self.language == "en"

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _report(self, progress: float, message: str, step: str = "") -> None:
        if self.progress_callback:
            await self.progress_callback(progress, message, {"step": step})

    async def _call(
        self,
        prompt: str,
        model_name: str,
        with_search: bool = False,
        thinking_budget: Optional[int] = None,
        _attempt: int = 0,
    ) -> str:
        from google import genai as google_genai
        from google.genai import types as gtypes

        client = google_genai.Client(api_key=self.api_key)

        config_kwargs: Dict[str, Any] = {}
        if with_search and self.search_grounding:
            config_kwargs["tools"] = [gtypes.Tool(google_search=gtypes.GoogleSearch())]
        else:
            # Prevent model from spontaneously calling functions (causes MALFORMED_FUNCTION_CALL)
            config_kwargs["tool_config"] = gtypes.ToolConfig(
                function_calling_config=gtypes.FunctionCallingConfig(mode="NONE")
            )

        if thinking_budget is not None:
            config_kwargs["thinking_config"] = gtypes.ThinkingConfig(thinking_budget=thinking_budget)

        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=gtypes.GenerateContentConfig(**config_kwargs),
            )
            result = (response.text or "").strip()

            # Inject real grounding URLs as Markdown reference definitions [1]: url
            if with_search and result:
                try:
                    candidate = response.candidates[0]
                    grounding = getattr(candidate, "grounding_metadata", None)
                    chunks = getattr(grounding, "grounding_chunks", None) or []
                    seen: set = set()
                    ref_defs: list = []   # [N]: url "title"
                    list_lines: list = [] # - [title](url) for the sources section
                    idx = 1
                    for chunk in chunks:
                        web = getattr(chunk, "web", None)
                        if not web:
                            continue
                        uri = getattr(web, "uri", None) or getattr(web, "url", None)
                        if not uri or uri in seen:
                            continue
                        seen.add(uri)
                        title = (getattr(web, "title", None) or uri).replace('"', "'")
                        ref_defs.append(f'[{idx}]: {uri} "{title}"')
                        list_lines.append(f"- [{title}]({uri})")
                        idx += 1
                    if ref_defs:
                        # Reference definitions go at the end — remark-gfm resolves [Publisher][N] → link
                        result += "\n\n" + "\n".join(ref_defs)
                        result += "\n\n---\n\n## 🔗 Verified Sources\n\n" + "\n".join(list_lines)
                    else:
                        self.logger.warning("Search grounding returned no chunks for %s", model_name)
                except Exception as exc:
                    self.logger.warning("Could not extract grounding sources: %s", exc)

            if not result:
                finish = "UNKNOWN"
                try:
                    finish = response.candidates[0].finish_reason.name
                except Exception:
                    pass
                if finish == "MALFORMED_FUNCTION_CALL" and _attempt < 2:
                    self.logger.warning(
                        "MALFORMED_FUNCTION_CALL on %s — retrying (attempt %d/2)", model_name, _attempt + 1,
                    )
                    await asyncio.sleep(2)
                    return await self._call(prompt, model_name=model_name, with_search=with_search, thinking_budget=thinking_budget, _attempt=_attempt + 1)
                if finish == "MALFORMED_FUNCTION_CALL":
                    raise RuntimeError(
                        f"{model_name} keeps generating malformed function calls. "
                        "Switch to a stable model such as gemini-2.5-flash in Settings → Gemini AI."
                    )
                raise RuntimeError(
                    f"Gemini returned empty text for {model_name} (finish_reason: {finish}). "
                    "Try again — if it persists, switch to a different model in Settings → Gemini AI."
                )
            return result
        except RuntimeError:
            raise
        except Exception as e:
            err = str(e)
            is_quota       = "429" in err or "RESOURCE_EXHAUSTED" in err.upper() or "ResourceExhausted" in type(e).__name__
            is_unavailable = "503" in err or "UNAVAILABLE" in err.upper() or "ServiceUnavailable" in type(e).__name__
            is_internal    = "500" in err or "INTERNAL" in err.upper() or "InternalServerError" in type(e).__name__
            if is_quota:
                if "PerDay" in err or "per_day" in err.lower():
                    quota_m = re.search(r"quota_value:\s*(\d+)", err)
                    limit = quota_m.group(1) if quota_m else "unknown"
                    raise RuntimeError(
                        f"Daily free-tier quota exhausted for {model_name} "
                        f"(limit: {limit} req/day). "
                        "Try again tomorrow, or switch to a higher-quota model in Settings → Gemini AI."
                    ) from e
                if _attempt < 3:
                    delay_m = re.search(r"seconds:\s*(\d+)", err)
                    wait = int(delay_m.group(1)) + 2 if delay_m else 30 * (2 ** _attempt)
                    self.logger.warning("Rate limited on %s — retrying in %ds (attempt %d/3)", model_name, wait, _attempt + 1)
                    await asyncio.sleep(wait)
                    return await self._call(prompt, model_name=model_name, with_search=with_search, thinking_budget=thinking_budget, _attempt=_attempt + 1)
            if (is_unavailable or is_internal) and _attempt < 3:
                wait = 15 * (2 ** _attempt)  # 15s, 30s, 60s
                code = "500 INTERNAL" if is_internal else "503 UNAVAILABLE"
                self.logger.warning("%s on %s — retrying in %ds (attempt %d/3)", code, model_name, wait, _attempt + 1)
                await asyncio.sleep(wait)
                return await self._call(prompt, model_name=model_name, with_search=with_search, thinking_budget=thinking_budget, _attempt=_attempt + 1)
            if is_unavailable or is_internal:
                fallback = self._MODEL_FALLBACKS.get(model_name)
                if fallback:
                    code = "500 INTERNAL" if is_internal else "503 UNAVAILABLE"
                    self.logger.warning("%s persists on %s after 3 retries — switching to fallback %s", code, model_name, fallback)
                    return await self._call(prompt, model_name=fallback, with_search=with_search, thinking_budget=thinking_budget, _attempt=0)
                raise RuntimeError(
                    f"{model_name} returned a server error and no fallback is available. "
                    "Please wait a few minutes and try again."
                ) from e
            raise

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"```(?:json)?\s*([\[{].*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        if match:
            return match.group(1).strip()
        return text.strip()

    @staticmethod
    def _extract_image_prompts(text: str) -> List[str]:
        prompts: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("PROMPT:"):
                p = stripped[7:].strip()
                if p:
                    prompts.append(p)
        return prompts

    @staticmethod
    def _extract_thumbnail_prompt(text: str) -> str:
        for line in text.splitlines():
            if line.strip().upper().startswith("THUMBNAIL_PROMPT:"):
                return line.split(":", 1)[1].strip()
        return text.strip()

    # ── Step 1: Trend Discovery ────────────────────────────────────────────────

    async def discover_trends(self) -> str:
        await self._report(5, "Searching for trending AI topics…", "trends")
        today = date.today()
        yesterday = today - timedelta(days=1)
        prompt = _TREND_PROMPT.format(
            today=today.strftime("%B %d, %Y"),
            yesterday=yesterday.strftime("%B %d, %Y"),
            channel=self.channel_name,
        )
        if not self._is_english():
            prompt += (
                f"\n\nAUDIENCE LANGUAGE: This channel publishes in {self._lang_name()}. "
                f"Present the Top 5 recommendations and Best Topic summary in {self._lang_name()}."
            )
        result = await self._call(prompt, model_name=self.pro_model, with_search=True)
        (self.input_dir / "trends.txt").write_text(result, encoding="utf-8")
        await self._report(100, "Trend discovery complete", "trends")
        return result

    # ── Step 2: Research ──────────────────────────────────────────────────────

    async def research_topic(self, topic: str) -> str:
        await self._report(5, f"Researching: {topic}…", "research")
        prompt = _RESEARCH_PROMPT.format(topic=topic)
        if not self._is_english():
            prompt += (
                f"\n\nNote: This dossier will be used for a {self._lang_name()}-language documentary. "
                "You may write the research in English for accuracy and completeness."
            )
        result = await self._call(prompt, model_name=self.pro_model, with_search=True)
        (self.input_dir / "research.txt").write_text(result, encoding="utf-8")
        await self._report(100, "Research complete", "research")
        return result

    # ── Step 3: Script ────────────────────────────────────────────────────────

    async def generate_script(self, research: str) -> str:
        await self._report(5, "Writing documentary script…", "script")
        prompt = _SCRIPT_PROMPT.format(research=research, channel=self.channel_name)
        if not self._is_english():
            prompt += (
                f"\n\nLANGUAGE REQUIREMENT: Write the ENTIRE script in {self._lang_name()}. "
                "Every word of [NARRATOR] narration must be in this language. "
                "[VISUAL] descriptions may stay in English. "
                "Do not mix languages in narration blocks."
            )
        text = await self._call(prompt, model_name=self.script_model)
        (self.input_dir / "script.md").write_text(text, encoding="utf-8")
        await self._report(100, "script.md saved", "script")
        return text

    # ── Step 4: Scenes JSON ───────────────────────────────────────────────────

    async def generate_scenes(self, script: str) -> str:
        await self._report(5, "Breaking script into scenes…", "scenes")
        prompt = _SCENES_PROMPT.format(script=script)
        if not self._is_english():
            prompt += (
                f"\n\nLANGUAGE REQUIREMENT: "
                f"The 'narration' and 'title' fields in every scene MUST be written in {self._lang_name()}. "
                "The 'visual_description' field MUST remain in English (it is used for image generation). "
                "Do not write English narration."
            )
        # Use pro_model (gemini-2.5-flash) with thinking disabled — much faster than script_model
        # for pure JSON generation; flash-lite is still too unreliable for 100-120 objects.
        raw = await self._call(
            prompt,
            model_name=self.pro_model,
            thinking_budget=0,
        )
        json_text = self._extract_json(raw)
        try:
            json.loads(json_text)
        except json.JSONDecodeError:
            self.logger.warning("Scenes JSON parse failed — returning raw text")
            json_text = raw
        (self.input_dir / "scenes.json").write_text(json_text, encoding="utf-8")
        await self._report(100, "scenes.json saved", "scenes")
        return json_text

    # ── Step 5: Image Prompts ─────────────────────────────────────────────────

    async def generate_image_prompts(self, scenes_json: str) -> str:
        backend = self.image_backend.lower()
        prompt_template = _IMAGE_PROMPTS_GEMINI if backend == "gemini" else _IMAGE_PROMPTS_FLUX
        label = "Gemini" if backend == "gemini" else "FLUX"
        await self._report(5, f"Generating {label}-optimized image prompts…", "image_prompts")
        raw = await self._call(
            prompt_template.format(scenes_json=scenes_json), model_name=self.flash_model
        )
        prompts = self._extract_image_prompts(raw)
        if prompts:
            (self.input_dir / "image_prompts.txt").write_text(
                "\n".join(prompts), encoding="utf-8"
            )
        else:
            (self.input_dir / "image_prompts.txt").write_text(raw, encoding="utf-8")
        await self._report(100, "image_prompts.txt saved", "image_prompts")
        return raw

    # ── Step 6: Thumbnail ─────────────────────────────────────────────────────

    async def generate_thumbnail(self, script: str) -> str:
        await self._report(5, "Creating thumbnail concept…", "thumbnail")
        prompt = _THUMBNAIL_PROMPT.format(script=script[:4000], channel=self.channel_name)
        if not self._is_english():
            prompt += (
                f"\n\nLANGUAGE REQUIREMENT: "
                f"Write THUMBNAIL_TITLE, THUMBNAIL_TEXT, and THUMBNAIL_CONCEPT in {self._lang_name()}. "
                "The THUMBNAIL_PROMPT field MUST remain in English (used for FLUX image generation)."
            )
        raw = await self._call(prompt, model_name=self.flash_model)
        prompt_line = self._extract_thumbnail_prompt(raw)
        (self.input_dir / "thumbnail_prompt.txt").write_text(prompt_line, encoding="utf-8")
        (self.input_dir / "thumbnail_full.txt").write_text(raw, encoding="utf-8")
        await self._report(100, "thumbnail_prompt.txt saved", "thumbnail")
        return raw

    # ── Step 7: SEO ───────────────────────────────────────────────────────────

    async def generate_seo(self, script: str) -> str:
        await self._report(5, "Generating SEO metadata…", "seo")
        prompt = _SEO_PROMPT.format(script=script[:4000], channel=self.channel_name)
        if not self._is_english():
            prompt += (
                f"\n\nLANGUAGE REQUIREMENT: Generate ALL metadata in {self._lang_name()}. "
                "This includes: title, alternate_titles, description, tags, hashtags, chapters, and keywords. "
                f"Optimise tags and keywords for {self._lang_name()}-language YouTube search. "
                "Return valid JSON only."
            )
        # JSON output — same reason as scenes: use larger model for reliable structure
        raw = await self._call(prompt, model_name=self.script_model)
        json_text = self._extract_json(raw)
        try:
            json.loads(json_text)
            (self.input_dir / "seo.json").write_text(json_text, encoding="utf-8")
        except json.JSONDecodeError:
            self.logger.warning("SEO JSON parse failed — saving raw text")
            (self.input_dir / "seo.json").write_text(raw, encoding="utf-8")
        await self._report(100, "seo.json saved", "seo")
        return raw

    # ── Full pipeline ─────────────────────────────────────────────────────────

    async def generate_all(
        self,
        topic: str,
        research: Optional[str] = None,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {"topic": topic}

        # Suppress per-step internal callbacks so they don't stomp pipeline %
        cb = self.progress_callback
        self.progress_callback = None

        async def report(pct: float, msg: str, step: str = "") -> None:
            if cb:
                await cb(pct, msg, {"step": step})

        try:
            # Step 2: Research (skip if provided)
            if not research:
                await report(5, "Researching topic…", "research")
                research = await self.research_topic(topic)
            results["research"] = research

            # Step 3: Script
            await report(20, "Writing documentary script…", "script")
            script = await self.generate_script(research)
            results["script"] = script

            # Step 4: Scenes
            await report(40, "Breaking script into scenes…", "scenes")
            scenes_json = await self.generate_scenes(script)
            results["scenes"] = scenes_json

            # Steps 5-7 run in parallel — report once before, once after
            await report(60, "Generating image prompts, thumbnail & SEO…", "image_prompts")
            image_raw, thumb_raw, seo_raw = await asyncio.gather(
                self.generate_image_prompts(scenes_json),
                self.generate_thumbnail(script),
                self.generate_seo(script),
            )
            results["image_prompts"] = image_raw
            results["thumbnail"] = thumb_raw
            results["seo"] = seo_raw

            await report(100, "All content generated — files saved to input/", "complete")

        finally:
            self.progress_callback = cb  # always restore

        return results
