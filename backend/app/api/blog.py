"""
Blog Post API — generate a long-form article from script.md and serve
platform-formatted copy text for Medium, LinkedIn, and generic tech blogs.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config import get_settings
from app.core.dependencies import get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.exceptions import ProjectNotFoundError
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository

router = APIRouter()


def _project_dir(project) -> Path:
    settings = get_settings()
    return Path(project.project_dir) if project.project_dir else (settings.PROJECTS_DIR / project.id)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _format_copy_text(platform: str, meta: Dict[str, Any], body: str) -> str:
    title = meta.get("title", "")
    subtitle = meta.get("subtitle", "")
    tags = meta.get("tags", []) or []

    if platform == "linkedin":
        hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags)
        parts = [title]
        if subtitle:
            parts.append(subtitle)
        parts.append("")
        parts.append(body)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts)

    if platform == "generic":
        lines = [f"# {title}"]
        if subtitle:
            lines.append(f"*{subtitle}*")
        lines.append("")
        lines.append(body)
        if tags:
            lines.append("")
            lines.append(f"Tags: {', '.join(tags)}")
        return "\n".join(lines)

    # medium (default)
    lines = [title]
    if subtitle:
        lines.append(subtitle)
    lines.append("")
    lines.append(body)
    if tags:
        lines.append("")
        lines.append(f"Tags: {', '.join(tags)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GET /blog/project/{project_id}
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}")
async def get_blog_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    meta = _read_json(pdir / "output" / "blog_meta.json")
    body_path = pdir / "output" / "blog_post.md"

    return {
        "available": meta is not None and body_path.exists(),
        "title": (meta or {}).get("title", ""),
        "subtitle": (meta or {}).get("subtitle", ""),
        "tag_count": len((meta or {}).get("tags", [])),
        "word_count": (meta or {}).get("word_count", 0),
        "generated_at": (meta or {}).get("generated_at"),
        "script_available": (pdir / "input" / "script.md").exists(),
    }


# ---------------------------------------------------------------------------
# GET /blog/project/{project_id}/content
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/content")
async def get_blog_content(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    meta = _read_json(pdir / "output" / "blog_meta.json")
    body_path = pdir / "output" / "blog_post.md"
    if meta is None or not body_path.exists():
        raise HTTPException(status_code=404, detail="Blog post not generated yet")

    return {
        "title": meta.get("title", ""),
        "subtitle": meta.get("subtitle", ""),
        "tags": meta.get("tags", []),
        "word_count": meta.get("word_count", 0),
        "generated_at": meta.get("generated_at"),
        "body": body_path.read_text(encoding="utf-8"),
    }


# ---------------------------------------------------------------------------
# PUT /blog/project/{project_id} — edit generated blog post
# ---------------------------------------------------------------------------
class BlogUpdatePayload(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    tags: Optional[List[str]] = None
    body: Optional[str] = None


@router.put("/project/{project_id}")
async def update_blog(
    project_id: str,
    payload: BlogUpdatePayload,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    output_dir = pdir / "output"
    meta_path = output_dir / "blog_meta.json"
    body_path = output_dir / "blog_post.md"
    meta = _read_json(meta_path)
    if meta is None or not body_path.exists():
        raise HTTPException(status_code=404, detail="Blog post not generated yet")

    if payload.title is not None:
        meta["title"] = payload.title
    if payload.subtitle is not None:
        meta["subtitle"] = payload.subtitle
    if payload.tags is not None:
        meta["tags"] = payload.tags
    if payload.body is not None:
        body_path.write_text(payload.body, encoding="utf-8")
        meta["word_count"] = len(payload.body.split())

    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "title": meta.get("title", ""),
        "subtitle": meta.get("subtitle", ""),
        "tags": meta.get("tags", []),
        "word_count": meta.get("word_count", 0),
        "generated_at": meta.get("generated_at"),
        "body": body_path.read_text(encoding="utf-8"),
    }


# ---------------------------------------------------------------------------
# GET /blog/project/{project_id}/copy — platform-formatted copy text
# ---------------------------------------------------------------------------
@router.get("/project/{project_id}/copy")
async def get_blog_copy_text(
    project_id: str,
    platform: str = Query("medium", pattern="^(medium|linkedin|generic)$"),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    pdir = _project_dir(project)
    meta = _read_json(pdir / "output" / "blog_meta.json")
    body_path = pdir / "output" / "blog_post.md"
    if meta is None or not body_path.exists():
        raise HTTPException(status_code=404, detail="Blog post not generated yet")

    body = body_path.read_text(encoding="utf-8")
    text = _format_copy_text(platform, meta, body)
    return {"text": text, "platform": platform, "char_count": len(text)}


# ---------------------------------------------------------------------------
# POST /blog/project/{project_id}/generate — trigger blog generation
# ---------------------------------------------------------------------------
@router.post("/project/{project_id}/generate")
async def generate_blog(
    project_id: str,
    background_tasks: BackgroundTasks,
    project_repo: ProjectRepository = Depends(get_project_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    gemini = await settings_repo.get_gemini_settings()
    if not gemini.api_key:
        raise HTTPException(
            status_code=400,
            detail="Gemini API key not configured. Go to Settings → Gemini AI.",
        )

    pdir = _project_dir(project)
    if not (pdir / "input" / "script.md").exists():
        raise HTTPException(
            status_code=400,
            detail="script.md not found — generate the script first.",
        )

    channel_name = (await settings_repo.get_by_key("channel.name")) or "Deep Dive AI"

    async def progress_cb(progress: float, message: str, data: dict):
        await connection_manager.broadcast_to_project(
            project_id,
            "job_progress",
            {"job_type": "blog", "progress": progress, "message": message, **data},
        )

    async def run():
        try:
            await connection_manager.broadcast_to_project(
                project_id, "job_progress",
                {"job_type": "blog", "progress": 0, "message": "Starting blog generation…"},
            )
            from app.services.blog_service import BlogPostService

            svc = BlogPostService(
                project_id=project.id,
                project_dir=pdir,
                api_key=gemini.api_key,
                pro_model=gemini.pro_model,
                script_model=gemini.script_model,
                flash_model=gemini.flash_model,
                search_grounding=gemini.search_grounding,
                image_backend=gemini.image_backend,
                language=project.language or "en",
                channel_name=channel_name,
                progress_callback=progress_cb,
            )
            result = await svc.generate_blog_post()
            await connection_manager.broadcast_to_project(
                project_id, "job_completed",
                {"job_type": "blog", "result": result},
            )
        except Exception as exc:
            await connection_manager.broadcast_to_project(
                project_id, "job_failed",
                {"job_type": "blog", "error": str(exc)},
            )

    background_tasks.add_task(run)
    return {"status": "started", "message": "Blog generation started — watch progress via WebSocket"}
