import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import Log
from app.core.logging import get_logger

logger = get_logger(__name__)


class LogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        level: str,
        message: str,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        source: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Log:
        log = Log(
            id=str(uuid.uuid4()),
            project_id=project_id,
            level=level.upper(),
            message=message,
            timestamp=datetime.utcnow(),
            source=source or "",
            job_id=job_id,
            context=context or {},
        )
        self.db.add(log)
        await self.db.flush()
        return log

    async def get_by_project(
        self,
        project_id: str,
        level: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Log]:
        query = select(Log).where(Log.project_id == project_id)
        if level:
            query = query.where(Log.level == level.upper())
        query = query.order_by(Log.timestamp.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 100) -> List[Log]:
        result = await self.db.execute(
            select(Log).order_by(Log.timestamp.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_by_project(self, project_id: str) -> int:
        result = await self.db.execute(
            delete(Log).where(Log.project_id == project_id)
        )
        return result.rowcount

    async def delete_old(self, keep_count: int = 10000) -> int:
        subq = (
            select(Log.id)
            .order_by(Log.timestamp.desc())
            .limit(keep_count)
            .subquery()
        )
        result = await self.db.execute(
            delete(Log).where(Log.id.not_in(select(subq.c.id)))
        )
        return result.rowcount
