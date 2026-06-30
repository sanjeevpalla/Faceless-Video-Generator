"""
AiNewsService — generates all 5 project input files from 10 user-provided news stories.

Inherits ContentGenerationService and reuses its Gemini client, scenes, image prompts,
thumbnail, and SEO methods. Only the script step is replaced with a news-anchor prompt.
"""
from __future__ import annotations

import asyncio
import json as _json
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
import urllib.request

from app.services.content_service import ContentGenerationService
from app.core.logging import get_logger

logger = get_logger(__name__)

_NEWS_SCRAPE_PROMPT = """You are an AI news curator with access to real-time Google Search.

TODAY: {today}

TASK: Find the 10 most important AI news stories from the LAST 24 HOURS (since {yesterday}).

Use Google Search to find real, current news published today or yesterday only.

FOCUS AREAS: AI model releases, major company announcements, AI research breakthroughs, AI regulation, AI investments, AI tools and products, AI safety.

REQUIREMENTS:
- All 10 stories MUST be from the last 24 hours — verify publication dates
- Cover diverse topics (avoid 2 stories about the same company unless both are landmark)
- Prioritize breaking news, major product launches, large investments, regulatory actions
- No recycled or generic AI stories — each must be a specific real event

OUTPUT: Return ONLY a valid JSON array. No markdown, no explanation, no code blocks:
[
  {{
    "title": "Concise headline under 80 characters",
    "summary": "2-3 sentences — what happened, key detail, and why it matters for AI",
    "source": "Publisher name (e.g. TechCrunch, The Verge, Reuters)"
  }}
]

Return exactly 10 stories, most significant first. Return ONLY the JSON array, nothing else."""


async def scrape_rss_news(n: int = 10) -> List[Dict]:
    """Fetch AI news from public RSS feeds — no API key required."""
    feeds = [
        "https://news.google.com/rss/search?q=artificial+intelligence+AI&hl=en-US&gl=US&ceid=US:en",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://venturebeat.com/category/ai/feed/",
    ]
    stories: List[Dict] = []
    seen: set = set()

    for url in feeds:
        if len(stories) >= n:
            break
        try:
            def _fetch(u: str = url) -> str:
                req = urllib.request.Request(
                    u, headers={"User-Agent": "Mozilla/5.0 (compatible; FacelessVideoBot/1.0)"}
                )
                with urllib.request.urlopen(req, timeout=8) as r:
                    return r.read().decode("utf-8", errors="replace")

            content = await asyncio.to_thread(_fetch)
            root = ET.fromstring(content)

            for item in root.findall(".//item"):
                if len(stories) >= n:
                    break
                title_el = item.find("title")
                if title_el is None or not title_el.text:
                    continue
                full_title = title_el.text.strip()
                # Google News format: "Headline - Publisher Name"
                if " - " in full_title:
                    parts = full_title.rsplit(" - ", 1)
                    title, source = parts[0].strip(), parts[1].strip()
                else:
                    title, source = full_title, ""
                key = title.lower()[:60]
                if key in seen:
                    continue
                seen.add(key)
                desc_el = item.find("description")
                summary = ""
                if desc_el is not None and desc_el.text:
                    summary = re.sub(r"<[^>]+>", "", desc_el.text).strip()[:300]
                stories.append({"title": title, "summary": summary, "source": source})
        except Exception as exc:
            logger.warning("RSS fetch failed for %s: %s", url, exc)

    return stories[:n]

_NEWS_SCRIPT_PROMPT = """You are a professional AI news anchor script writer for the YouTube channel {channel}.

DATE: {today}

NEWS STORIES TO COVER:
{stories_text}

TASK: Write a complete 10-11 minute YouTube AI news script covering all 10 stories above.

REQUIREMENTS:
- Total runtime: 10-11 minutes at ~130 words/minute narration
- Exactly 12 SECTIONS: Introduction + 10 news stories + Outro
- Section 1 — Introduction: ~30 seconds, ~65 narrator words (welcome, hook, brief preview)
- Sections 2-11 — Each story: ~60 seconds, ~130 narrator words (what happened, why it matters, impact)
- Section 12 — Outro: ~30 seconds, ~60 narrator words (recap top 3, subscribe CTA)
- Tone: Professional, confident, engaging news anchor delivery
- Smooth natural transitions between stories

OUTPUT FORMAT — follow this structure EXACTLY:

{channel} — Top 10 AI News — {today}

SECTION 1: Introduction
[VISUAL]
Sleek AI news studio with holographic displays showing AI headlines, breaking news ticker, Deep Dive AI logo prominently displayed
[NARRATOR]
{intro narration ~65 words — welcome viewers, hook with the biggest story, brief preview of today's top 10}

SECTION 2: {Exact title of Story 1}
[VISUAL]
{What to show on screen — relevant tech imagery, company headquarters, data centers, relevant product or person}
[NARRATOR]
{Story 1 narration ~130 words — what happened, context, why it matters, impact on AI landscape}

SECTION 3: {Exact title of Story 2}
[VISUAL]
{Visual description for story 2}
[NARRATOR]
{Story 2 narration ~130 words}

SECTION 4: {Exact title of Story 3}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 3 narration ~130 words}

SECTION 5: {Exact title of Story 4}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 4 narration ~130 words}

SECTION 6: {Exact title of Story 5}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 5 narration ~130 words}

SECTION 7: {Exact title of Story 6}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 6 narration ~130 words}

SECTION 8: {Exact title of Story 7}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 7 narration ~130 words}

SECTION 9: {Exact title of Story 8}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 8 narration ~130 words}

SECTION 10: {Exact title of Story 9}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 9 narration ~130 words}

SECTION 11: {Exact title of Story 10}
[VISUAL]
{Visual description}
[NARRATOR]
{Story 10 narration ~130 words}

SECTION 12: Outro
[VISUAL]
Deep Dive AI subscribe animation, notification bell, channel logo, subscribe button highlighted
[NARRATOR]
{Outro narration ~60 words — brief recap of top 3 stories, call to subscribe, "see you in the next one"}

IMPORTANT RULES:
- Use [VISUAL] and [NARRATOR] tags EXACTLY as shown above — no variations, no extra tags
- Return the COMPLETE script with all 12 sections — do not skip or abbreviate any section
- Never introduce stories with "Story number X" or "Number X" — open directly with the news
- Write narration that flows naturally when read aloud at a steady pace
- Keep each story segment self-contained with a clear opening and closing sentence"""


class AiNewsService(ContentGenerationService):
    """Generates all project input files from 10 user-supplied news stories."""

    async def scrape_news_stories(self, n: int = 10) -> List[Dict]:
        """Fetch the latest AI news stories via Gemini search grounding.
        Falls back to RSS scraping if Gemini returns unparseable output."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        prompt = _NEWS_SCRAPE_PROMPT.format(
            today=today.strftime("%B %d, %Y"),
            yesterday=yesterday.strftime("%B %d, %Y"),
        )
        try:
            raw = await self._call(prompt, model_name=self.pro_model, with_search=True)
            json_text = self._extract_json(raw)
            import json as _json
            stories = _json.loads(json_text)
            if isinstance(stories, list) and stories:
                return stories[:n]
        except Exception as exc:
            self.logger.warning("Gemini news scrape parse failed: %s — falling back to RSS", exc)
        return await scrape_rss_news(n)

    async def generate_news_script(self, stories: List[Dict[str, str]]) -> str:
        """Step 1 — Write a 12-section news anchor script from 10 provided stories."""
        await self._report(5, "Writing AI news anchor script…", "script")
        today = date.today().strftime("%B %d, %Y")
        stories_text = "\n".join(
            f"{i + 1}. {s['title']}\n   {s.get('summary', '').strip()}"
            for i, s in enumerate(stories)
        )
        # Use .replace() instead of .format() — the prompt contains many
        # literal {…} placeholders for the AI that would confuse str.format().
        prompt = (
            _NEWS_SCRIPT_PROMPT
            .replace("{channel}", self.channel_name)
            .replace("{today}", today)
            .replace("{stories_text}", stories_text)
        )
        if not self._is_english():
            prompt += (
                f"\n\nLANGUAGE REQUIREMENT: Write ALL [NARRATOR] narration entirely in {self._lang_name()}. "
                "[VISUAL] descriptions MUST remain in English (used for image generation). "
                "Do not mix languages within any narration block."
            )
        text = await self._call(prompt, model_name=self.script_model)
        (self.input_dir / "script.md").write_text(text, encoding="utf-8")
        await self._report(100, "script.md saved", "script")
        return text

    # ------------------------------------------------------------------
    # Story-number assignment (used by VideoGenerationService for overlays)
    # ------------------------------------------------------------------

    @staticmethod
    def _assign_story_numbers(script: str, scenes_raw: str) -> Optional[str]:
        """Tag each scene with story_number by matching its narration against script sections.

        story_number 0  = Introduction or Outro
        story_number 1–10 = News stories (SECTION 2–11)

        Uses word-overlap between scene narration and each section's [NARRATOR] block
        rather than proportional distribution, so all 10 stories are reliably tagged even
        when the AI generates fewer or more SECTION headers than expected.
        """
        try:
            scenes = _json.loads(scenes_raw)
        except Exception:
            return None

        if not isinstance(scenes, list) or not scenes:
            return None

        section_pattern = re.compile(r'^SECTION\s+(\d+)[:\s—–-]+(.+)$', re.MULTILINE)
        matches = list(section_pattern.finditer(script))
        if not matches:
            return None

        script_len = len(script)
        sections_info: List[Dict] = []
        for i, m in enumerate(matches):
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else script_len
            section_text = script[m.start():end_pos]

            # Extract all [NARRATOR] text from this section
            narrator_blocks = re.findall(
                r'\[NARRATOR\]\s*([\s\S]*?)(?=\[VISUAL\]|\[NARRATOR\]|^SECTION|\Z)',
                section_text, re.MULTILINE,
            )
            narrator_text = " ".join(narrator_blocks) if narrator_blocks else section_text
            narrator_words = set(re.findall(r'\w+', narrator_text.lower()))

            sec_num = int(m.group(1))
            sections_info.append({
                "num":           sec_num,
                "title":         m.group(2).strip(),
                "narrator_words": narrator_words,
                "story_num":     (sec_num - 1) if 2 <= sec_num <= 11 else 0,
            })

        # Match each scene to the section whose [NARRATOR] overlaps most with the scene narration
        for scene in scenes:
            narration = (
                scene.get("narration") or
                scene.get("narrator") or
                scene.get("description") or ""
            )
            scene_words = set(re.findall(r'\w+', narration.lower()))

            best_sec   = None
            best_score = -1
            for sec in sections_info:
                score = len(scene_words & sec["narrator_words"])
                if score > best_score:
                    best_score = score
                    best_sec   = sec

            if best_sec:
                scene["story_number"] = best_sec["story_num"]
                scene["story_title"]  = best_sec["title"] if best_sec["story_num"] > 0 else ""
            else:
                scene["story_number"] = 0
                scene["story_title"]  = ""

        return _json.dumps(scenes, indent=2, ensure_ascii=False)

    async def generate_all_for_news(self, stories: List[Dict[str, str]]) -> Dict[str, Any]:
        """Run the full AI news pipeline: script → scenes → prompts/thumbnail/SEO."""
        results: Dict[str, Any] = {}

        cb = self.progress_callback
        self.progress_callback = None

        async def report(pct: float, msg: str, step: str = "") -> None:
            if cb:
                await cb(pct, msg, {"step": step})

        try:
            await report(5, "Writing AI news script…", "script")
            script = await self.generate_news_script(stories)
            results["script"] = script

            await report(30, "Breaking script into scenes…", "scenes")
            scenes_json = await self.generate_scenes(script)

            # Tag each scene with its story number (1-10) for video overlay
            tagged = self._assign_story_numbers(script, scenes_json)
            if tagged:
                scenes_json = tagged
                (self.input_dir / "scenes.json").write_text(
                    scenes_json, encoding="utf-8"
                )
                self.logger.info("scenes.json annotated with story_number fields")
            results["scenes"] = scenes_json

            await report(60, "Generating image prompts, thumbnail & SEO…", "image_prompts")
            image_raw, thumb_raw, seo_raw = await asyncio.gather(
                self.generate_image_prompts(scenes_json),
                self.generate_thumbnail(script),
                self.generate_seo(script),
            )
            results["image_prompts"] = image_raw
            results["thumbnail"] = thumb_raw
            results["seo"] = seo_raw

            await report(100, "All AI news content generated — files saved to input/", "complete")

        finally:
            self.progress_callback = cb

        return results
