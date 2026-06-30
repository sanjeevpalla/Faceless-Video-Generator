import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, name: str, description: Optional[str] = None, project_dir: Optional[str] = None, language: str = "en", project_type: str = "deep_dive") -> Project:
        project = Project(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            project_dir=project_dir,
            language=language,
            project_type=project_type,
            status=ProjectStatus.CREATED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        logger.info(f"Created project: {project.id} - {project.name}")
        return project

    async def get_by_name(self, name: str) -> Optional[Project]:
        result = await self.db.execute(
            select(Project).where(func.lower(Project.name) == name.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, project_id: str) -> Optional[Project]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        exclude_archived: bool = True,
    ) -> tuple[List[Project], int]:
        query = select(Project)
        count_query = select(func.count(Project.id))

        if status:
            query = query.where(Project.status == status)
            count_query = count_query.where(Project.status == status)
        elif exclude_archived:
            query = query.where(Project.status != ProjectStatus.ARCHIVED)
            count_query = count_query.where(Project.status != ProjectStatus.ARCHIVED)

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        query = query.order_by(Project.updated_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        projects = list(result.scalars().all())
        return projects, total

    async def update(self, project_id: str, **kwargs) -> Optional[Project]:
        kwargs["updated_at"] = datetime.utcnow()
        await self.db.execute(
            update(Project).where(Project.id == project_id).values(**kwargs)
        )
        await self.db.flush()
        return await self.get_by_id(project_id)

    async def delete(self, project_id: str) -> bool:
        result = await self.db.execute(
            delete(Project).where(Project.id == project_id)
        )
        return result.rowcount > 0

    async def update_status(self, project_id: str, status: ProjectStatus) -> Optional[Project]:
        return await self.update(project_id, status=status)

    async def update_progress(
        self, project_id: str, step: str, progress_data: Dict[str, Any]
    ) -> Optional[Project]:
        project = await self.get_by_id(project_id)
        if not project:
            return None
        current_state = dict(project.progress_state or {})
        current_state[step] = progress_data
        return await self.update(project_id, progress_state=current_state)

    async def update_input_files_status(
        self, project_id: str, file_type: str, file_data: Dict[str, Any]
    ) -> Optional[Project]:
        project = await self.get_by_id(project_id)
        if not project:
            return None
        current_status = dict(project.input_files_status or {})
        current_status[file_type] = file_data
        return await self.update(project_id, input_files_status=current_status)

    async def update_resume_state(
        self, project_id: str, resume_data: Dict[str, Any]
    ) -> Optional[Project]:
        return await self.update(project_id, resume_state=resume_data)

    async def archive(self, project_id: str) -> Optional[Project]:
        return await self.update_status(project_id, ProjectStatus.ARCHIVED)

    async def count_by_status(self) -> Dict[str, int]:
        result = await self.db.execute(
            select(Project.status, func.count(Project.id)).group_by(Project.status)
        )
        return {row[0]: row[1] for row in result.all()}
