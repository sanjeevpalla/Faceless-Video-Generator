import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus, JobType
from app.core.logging import get_logger

logger = get_logger(__name__)


class JobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        project_id: str,
        job_type: JobType,
        priority: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            project_id=project_id,
            job_type=job_type,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
            progress=0.0,
            priority=priority,
            metadata_=metadata or {},
            retry_count=0.0,
            max_retries=3.0,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        logger.info(f"Created job {job.id} type={job.job_type} for project={project_id}")
        return job

    async def get_by_id(self, job_id: str) -> Optional[Job]:
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def get_by_project(
        self,
        project_id: str,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> List[Job]:
        query = select(Job).where(Job.project_id == project_id)
        if status:
            query = query.where(Job.status == status)
        if job_type:
            query = query.where(Job.job_type == job_type)
        query = query.order_by(Job.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> Optional[Job]:
        values = {"status": status}
        if status == JobStatus.RUNNING:
            values["started_at"] = datetime.utcnow()
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            values["completed_at"] = datetime.utcnow()
        if error_message is not None:
            values["error_message"] = error_message

        await self.db.execute(update(Job).where(Job.id == job_id).values(**values))
        await self.db.flush()
        return await self.get_by_id(job_id)

    async def update_progress(self, job_id: str, progress: float) -> Optional[Job]:
        await self.db.execute(
            update(Job).where(Job.id == job_id).values(progress=min(100.0, max(0.0, progress)))
        )
        await self.db.flush()
        return await self.get_by_id(job_id)

    async def get_pending_jobs(self, limit: int = 10) -> List[Job]:
        result = await self.db.execute(
            select(Job)
            .where(Job.status == JobStatus.PENDING)
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_retry(self, job_id: str) -> Optional[Job]:
        job = await self.get_by_id(job_id)
        if not job:
            return None
        new_count = job.retry_count + 1
        await self.db.execute(
            update(Job).where(Job.id == job_id).values(
                retry_count=new_count,
                status=JobStatus.PENDING if new_count <= job.max_retries else JobStatus.FAILED,
            )
        )
        await self.db.flush()
        return await self.get_by_id(job_id)

    async def count_active_jobs(self) -> int:
        result = await self.db.execute(
            select(func.count(Job.id)).where(Job.status.in_([JobStatus.RUNNING, JobStatus.PENDING]))
        )
        return result.scalar_one()
