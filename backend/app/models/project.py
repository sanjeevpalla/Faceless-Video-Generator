import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Dict, Optional

from sqlalchemy import Column, String, DateTime, JSON, Enum, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ProjectStatus(str, PyEnum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class ProjectType(str, PyEnum):
    DEEP_DIVE = "deep_dive"
    AI_NEWS = "ai_news"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    status = Column(
        Enum(ProjectStatus),
        nullable=False,
        default=ProjectStatus.CREATED,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    project_dir = Column(String(1024), nullable=True)
    description = Column(Text, nullable=True)
    language = Column(String(16), nullable=True, default="en")
    project_type = Column(String(32), nullable=False, default="deep_dive")

    # JSON fields for flexible state storage
    input_files_status = Column(
        JSON,
        nullable=False,
        default=lambda: {
            "script": {"status": "missing", "filename": None, "path": None, "size": None},
            "scenes": {"status": "missing", "filename": None, "path": None, "size": None},
            "image_prompts": {"status": "missing", "filename": None, "path": None, "size": None},
            "thumbnail_prompt": {"status": "missing", "filename": None, "path": None, "size": None},
            "seo": {"status": "missing", "filename": None, "path": None, "size": None},
            "music": {"status": "missing", "filename": None, "path": None, "size": None},
        },
    )
    progress_state = Column(
        JSON,
        nullable=False,
        default=lambda: {
            "translate": {"status": "pending", "progress": 0, "total": 0, "completed": 0},
            "images": {"status": "pending", "progress": 0, "total": 0, "completed": 0},
            "voice": {"status": "pending", "progress": 0, "total": 0, "completed": 0},
            "subtitles": {"status": "pending", "progress": 0, "total": 0, "completed": 0},
            "thumbnail": {"status": "pending", "progress": 0, "total": 0, "completed": 0},
            "video": {"status": "pending", "progress": 0, "total": 0, "completed": 0},
            "metadata": {"status": "pending", "progress": 0, "total": 0, "completed": 0},
        },
    )
    resume_state = Column(
        JSON,
        nullable=False,
        default=lambda: {
            "last_completed_step": None,
            "failed_scenes": [],
            "checkpoint_data": {},
        },
    )

    # Relationships
    jobs = relationship("Job", back_populates="project", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r} status={self.status}>"
