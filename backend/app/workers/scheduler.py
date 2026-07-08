"""
AutomationScheduler — thin wrapper around APScheduler's AsyncIOScheduler that
drives the "100% automation" trigger: on a cron schedule, create a new project
and kick off its pipeline job with zero human input (see
backend/app/services/automation_service.py).

Started/stopped in main.py's lifespan alongside the existing queue_manager.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import get_logger

logger = get_logger(__name__)

_DEEP_DIVE_JOB_ID = "automation_deep_dive"
_AI_NEWS_JOB_ID = "automation_ai_news"


class AutomationScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        self._scheduler.start()
        from app.database import get_session_factory
        from app.repositories.settings_repo import SettingsRepository

        async with get_session_factory()() as sess:
            settings_repo = SettingsRepository(sess)
            await self.reschedule(settings_repo)
        logger.info("Automation scheduler started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Automation scheduler stopped")

    async def reschedule(self, settings_repo) -> None:
        """(Re)apply the automation.* cron settings. Safe to call any time,
        including from the Settings API right after the user changes a
        schedule — no restart needed."""
        automation = await settings_repo.get_automation_settings()

        for job_id in (_DEEP_DIVE_JOB_ID, _AI_NEWS_JOB_ID):
            existing = self._scheduler.get_job(job_id)
            if existing:
                self._scheduler.remove_job(job_id)

        if automation.deep_dive_enabled:
            from app.services.automation_service import create_and_start_deep_dive
            self._scheduler.add_job(
                create_and_start_deep_dive,
                trigger=CronTrigger.from_crontab(automation.deep_dive_cron),
                id=_DEEP_DIVE_JOB_ID,
                replace_existing=True,
            )

        if automation.ai_news_enabled:
            from app.services.automation_service import create_and_start_ai_news
            self._scheduler.add_job(
                create_and_start_ai_news,
                trigger=CronTrigger.from_crontab(automation.ai_news_cron),
                id=_AI_NEWS_JOB_ID,
                replace_existing=True,
            )

        logger.info(
            "Automation schedule applied: deep_dive_enabled=%s (%s), ai_news_enabled=%s (%s)",
            automation.deep_dive_enabled, automation.deep_dive_cron,
            automation.ai_news_enabled, automation.ai_news_cron,
        )


# Global singleton, mirroring app.workers.queue_manager's pattern.
automation_scheduler = AutomationScheduler()
