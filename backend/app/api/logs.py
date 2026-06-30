from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session, get_project_repo
from app.core.exceptions import ProjectNotFoundError
from app.repositories.log_repo import LogRepository
from app.repositories.project_repo import ProjectRepository

router = APIRouter()


@router.get("/project/{project_id}", response_model=list)
async def get_project_logs(
    project_id: str,
    level: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)
    log_repo = LogRepository(db)
    logs = await log_repo.get_by_project(project_id, level=level, limit=limit, offset=offset)
    return [
        {
            "id": log.id,
            "level": log.level.value if hasattr(log.level, "value") else log.level,
            "message": log.message,
            "timestamp": log.timestamp.isoformat() + "Z",
            "source": log.source,
            "job_id": log.job_id,
            "context": log.context or {},
        }
        for log in logs
    ]


@router.delete("/project/{project_id}")
async def clear_project_logs(
    project_id: str,
    db: AsyncSession = Depends(get_db_session),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)
    log_repo = LogRepository(db)
    count = await log_repo.delete_by_project(project_id)
    return {"message": f"Deleted {count} log entries", "count": count}
