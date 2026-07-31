"""
AutomationService — creates a new project and kicks off its pipeline job, for
use by the cron scheduler (backend/app/workers/scheduler.py). Zero human input
required to reach this point; Deep Dive projects then gate on a WhatsApp topic
reply via the trend_discovery pipeline step, AI News projects run straight
through unattended.
"""
import re
from datetime import date

from app.config import get_settings
from app.core.logging import get_logger
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.services.pipeline_runner import enqueue_pipeline_job

logger = get_logger(__name__)


def _slugify(name: str) -> str:
    """Turn a project name into a safe filesystem folder name (mirrors app/api/projects.py)."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:60] or "project"


async def create_and_start_deep_dive() -> str:
    return await _create_and_start("deep_dive", "Deep Dive")


async def create_and_start_ai_news() -> str:
    return await _create_and_start("ai_news", "AI News")


async def _create_and_start(project_type: str, label: str) -> str:
    from app.database import get_session_factory

    async with get_session_factory()() as sess:
        project_repo = ProjectRepository(sess)
        settings_repo = SettingsRepository(sess)
        job_repo = JobRepository(sess)

        automation = await settings_repo.get_automation_settings()
        name = f"{label} {date.today().isoformat()}"

        cfg = get_settings()
        project_dir = cfg.PROJECTS_DIR / _slugify(name)
        project_dir.mkdir(parents=True, exist_ok=True)
        for subdir in ["input", "images", "audio", "subtitles", "thumbnail",
                       "output", "cache", "logs", "temp", "metadata"]:
            (project_dir / subdir).mkdir(exist_ok=True)
        for cache_sub in ["images", "audio", "subtitles", "thumbnail"]:
            (project_dir / "cache" / cache_sub).mkdir(exist_ok=True)

        languages = automation.languages or [automation.default_language]
        project = await project_repo.create(
            name=name,
            project_dir=str(project_dir),
            language=languages[0],
            languages=languages,
            project_type=project_type,
        )
        await sess.commit()

        job_id = await enqueue_pipeline_job(project, job_repo, settings_repo)
        await sess.commit()

    logger.info("Automation created project %s (%s) and enqueued job %s", project.id, name, job_id)
    return project.id
