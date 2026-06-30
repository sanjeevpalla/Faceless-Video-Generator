from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    project_id: str
    job_type: str
    priority: float = Field(default=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    project_id: str
    job_type: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    priority: float = 0.0
    retry_count: float = 0.0
    max_retries: float = 3.0

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, job) -> "JobResponse":
        return cls(
            id=job.id,
            project_id=job.project_id,
            job_type=job.job_type,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            progress=job.progress,
            error_message=job.error_message,
            metadata=job.metadata_ or {},
            priority=job.priority,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
        )


class JobProgressUpdate(BaseModel):
    job_id: str
    project_id: str
    job_type: str
    status: str
    progress: float
    message: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
