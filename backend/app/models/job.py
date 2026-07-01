import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, JSON, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class JobType(str, PyEnum):
    TRANSLATE = "translate"
    IMAGE = "image"
    VOICE = "voice"
    SUBTITLE = "subtitle"
    VIDEO = "video"
    THUMBNAIL = "thumbnail"
    METADATA = "metadata"
    WAN2 = "wan2"
    PIPELINE = "pipeline"


class JobStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_type = Column(Enum(JobType), nullable=False, index=True)
    status = Column(
        Enum(JobStatus),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Float, nullable=False, default=0.0)
    error_message = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    priority = Column(Float, nullable=False, default=0.0)
    retry_count = Column(Float, nullable=False, default=0.0)
    max_retries = Column(Float, nullable=False, default=3.0)

    # Relationships
    project = relationship("Project", back_populates="jobs")

    def __repr__(self) -> str:
        return f"<Job id={self.id} type={self.job_type} status={self.status}>"
