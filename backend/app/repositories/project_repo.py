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

    async def create(
        self,
        name: str,
        description: Optional[str] = None,
        project_dir: Optional[str] = None,
        language: str = "en",
        languages: Optional[List[str]] = None,
        language_voices: Optional[Dict[str, str]] = None,
        project_type: str = "deep_dive",
    ) -> Project:
        project = Project(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            project_dir=project_dir,
            language=language,
            languages=languages or [language],
            language_voices=language_voices or {},
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

    async def update_language_progress(
        self, project_id: str, language: str, step: str, progress_data: Dict[str, Any]
    ) -> Optional[Project]:
        project = await self.get_by_id(project_id)
        if not project:
            return None
        current_state = dict(project.language_progress or {})
        lang_state = dict(current_state.get(language) or {})
        lang_state[step] = progress_data
        current_state[language] = lang_state
        return await self.update(project_id, language_progress=current_state)

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

    # ── WhatsApp HITL gate ───────────────────────────────────────────────────

    async def set_awaiting_whatsapp_reply(
        self,
        project_id: str,
        candidates: List[Dict[str, Any]],
        whatsapp_message_id: str,
        job_id: str,
    ) -> Optional[Project]:
        project = await self.get_by_id(project_id)
        if not project:
            return None
        resume_data = dict(project.resume_state or {})
        resume_data["whatsapp"] = {
            "status": "awaiting_whatsapp_reply",
            "candidate_topics": candidates,
            "whatsapp_message_id": whatsapp_message_id,
            "job_id": job_id,
            "sent_at": datetime.utcnow().isoformat(),
            "selected_topic": None,
        }
        await self.update(project_id, resume_state=resume_data, status=ProjectStatus.AWAITING_INPUT)
        return await self.get_by_id(project_id)

    async def resolve_whatsapp_reply(
        self, project_id: str, selected_topic: Dict[str, Any]
    ) -> Optional[Project]:
        project = await self.get_by_id(project_id)
        if not project:
            return None
        resume_data = dict(project.resume_state or {})
        wa = dict(resume_data.get("whatsapp") or {})
        if wa.get("status") != "awaiting_whatsapp_reply":
            return project  # already resolved — idempotent no-op
        wa["status"] = "resolved"
        wa["selected_topic"] = selected_topic
        resume_data["whatsapp"] = wa
        resume_data["last_completed_step"] = "trend_discovery"
        await self.update(project_id, resume_state=resume_data, status=ProjectStatus.CREATED)
        return await self.get_by_id(project_id)

    async def clear_awaiting_whatsapp_reply(self, project_id: str) -> Optional[Project]:
        project = await self.get_by_id(project_id)
        if not project:
            return None
        resume_data = dict(project.resume_state or {})
        resume_data.pop("whatsapp", None)
        await self.update(project_id, resume_state=resume_data, status=ProjectStatus.CREATED)
        return await self.get_by_id(project_id)

    async def get_by_pending_whatsapp_message_id(self, whatsapp_message_id: str) -> Optional[Project]:
        """Look up the project a WhatsApp reply belongs to, by the outbound message id
        it's replying to — matches regardless of whether that prompt is still pending
        or already resolved, so a duplicate/retried webhook delivery can still be
        recognised as "already_resolved" instead of falling through as unmatched.

        Filters in Python rather than a SQLite json_extract WHERE clause — the
        expected row count is always small for a single-user app, so this avoids
        any dependency on SQLite's JSON1 extension being available.
        """
        result = await self.db.execute(select(Project))
        for project in result.scalars().all():
            wa = (project.resume_state or {}).get("whatsapp") or {}
            if wa.get("whatsapp_message_id") == whatsapp_message_id:
                return project
        return None
