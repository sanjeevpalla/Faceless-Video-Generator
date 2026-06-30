from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import Settings, get_settings


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


def get_app_settings() -> Settings:
    return get_settings()


async def get_project_repo(
    db: AsyncSession = Depends(get_db_session),
):
    from app.repositories.project_repo import ProjectRepository
    return ProjectRepository(db)


async def get_settings_repo(
    db: AsyncSession = Depends(get_db_session),
):
    from app.repositories.settings_repo import SettingsRepository
    return SettingsRepository(db)


async def get_job_repo(
    db: AsyncSession = Depends(get_db_session),
):
    from app.repositories.job_repo import JobRepository
    return JobRepository(db)


async def get_queue_manager():
    from app.workers.queue_manager import queue_manager
    return queue_manager


async def get_log_repo(
    db: AsyncSession = Depends(get_db_session),
):
    from app.repositories.log_repo import LogRepository
    return LogRepository(db)
