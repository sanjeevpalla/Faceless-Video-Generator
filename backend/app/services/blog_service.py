"""
BlogPostService — turns a project's script.md into a long-form article
ready to publish on Medium, LinkedIn, and other tech blogs.

Reuses ContentGenerationService._call() for the actual Gemini request
(retry/quota/503 handling, model fallback chain) — see AiNewsService for
the same subclassing pattern.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.services.content_service import ContentGenerationService

_BLOG_POST_PROMPT = """You are an award-winning tech journalist and storyteller who writes long-form articles for Medium, LinkedIn, and developer blogs.

CHANNEL: {channel}

TASK: Rewrite the video script below as a standalone written article — NOT a video script. Remove all [VISUAL] and [NARRATOR] tags and camera directions; tell the story in prose the way a human writer would for a blog post.

SOURCE SCRIPT:
{script}
{keyword_hint}
REQUIREMENTS:
- Target length: 800-1500 words
- Strong hook opening paragraph (no "In this article..." framing)
- Use ## Markdown section headers to break up the story
- Story-driven, engaging, easy to understand — written for Medium/LinkedIn/tech-blog readers
- End with a short conclusion and a call-to-action inviting readers to watch the full video on the "{channel}" YouTube channel
- Do NOT include image prompts, scene numbers, or production notes

OUTPUT FORMAT (exactly this structure, no extra commentary):
TITLE: <catchy article title, under 100 characters>
SUBTITLE: <one-sentence subtitle/dek, under 200 characters>
TAGS: <5-8 comma-separated topic tags>
---
<the full Markdown article body>"""


class BlogPostService(ContentGenerationService):
    """Generates a publish-ready blog article from script.md."""

    async def generate_blog_post(self) -> Dict[str, Any]:
        await self._report(5, "Reading script...", "blog")

        script_path = self.input_dir / "script.md"
        if not script_path.exists():
            raise RuntimeError("script.md not found — generate the script first")
        script = script_path.read_text(encoding="utf-8")

        keyword_hint = ""
        seo_path = self.input_dir / "seo.json"
        if seo_path.exists():
            try:
                seo = json.loads(seo_path.read_text(encoding="utf-8"))
                keywords = seo.get("keywords") or seo.get("tags") or []
                if keywords:
                    keyword_hint = f"\nTARGET KEYWORDS (weave in naturally): {', '.join(keywords)}\n"
            except json.JSONDecodeError:
                pass

        await self._report(20, "Writing blog article...", "blog")
        prompt = _BLOG_POST_PROMPT.format(
            script=script, channel=self.channel_name, keyword_hint=keyword_hint
        )
        if not self._is_english():
            prompt += (
                f"\n\nLANGUAGE REQUIREMENT: Write the ENTIRE article — TITLE, SUBTITLE, TAGS, "
                f"and body — in {self._lang_name()}."
            )
        raw = await self._call(prompt, model_name=self.script_model)

        await self._report(80, "Saving article...", "blog")
        title, subtitle, tags, body = self._parse_blog_output(raw)

        output_dir = self.project_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        body_path = output_dir / "blog_post.md"
        body_path.write_text(body, encoding="utf-8")

        meta = {
            "title": title,
            "subtitle": subtitle,
            "tags": tags,
            "word_count": len(body.split()),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
        meta_path = output_dir / "blog_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        await self._report(100, "Blog post saved", "blog")
        return {
            "blog_path": str(body_path),
            "meta_path": str(meta_path),
            "title": title,
            "word_count": meta["word_count"],
        }

    @staticmethod
    def _parse_blog_output(raw: str) -> tuple[str, str, list[str], str]:
        header, _, body = raw.partition("\n---\n")
        if not body:
            # Marker not found on its own line — fall back to a bare "---" split.
            header, _, body = raw.partition("---")
        if not body.strip():
            # Model didn't follow the format at all — treat the whole thing as the body.
            return "Untitled Article", "", [], raw.strip()

        title, subtitle, tags = "Untitled Article", "", []
        for line in header.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("TITLE:"):
                title = stripped.split(":", 1)[1].strip()
            elif stripped.upper().startswith("SUBTITLE:"):
                subtitle = stripped.split(":", 1)[1].strip()
            elif stripped.upper().startswith("TAGS:"):
                tags = [t.strip() for t in stripped.split(":", 1)[1].split(",") if t.strip()]

        return title, subtitle, tags, body.strip()
