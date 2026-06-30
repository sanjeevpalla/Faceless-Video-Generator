from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FileStatusDetail(BaseModel):
    status: str = "missing"
    filename: Optional[str] = None
    path: Optional[str] = None
    size: Optional[int] = None
    mime_type: Optional[str] = None
    uploaded_at: Optional[datetime] = None


class InputFilesStatus(BaseModel):
    script: FileStatusDetail = Field(default_factory=FileStatusDetail)
    scenes: FileStatusDetail = Field(default_factory=FileStatusDetail)
    image_prompts: FileStatusDetail = Field(default_factory=FileStatusDetail)
    thumbnail_prompt: FileStatusDetail = Field(default_factory=FileStatusDetail)
    seo: FileStatusDetail = Field(default_factory=FileStatusDetail)


class StepProgress(BaseModel):
    status: str = "pending"
    progress: float = 0.0
    total: int = 0
    completed: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ProgressState(BaseModel):
    images: StepProgress = Field(default_factory=StepProgress)
    voice: StepProgress = Field(default_factory=StepProgress)
    subtitles: StepProgress = Field(default_factory=StepProgress)
    thumbnail: StepProgress = Field(default_factory=StepProgress)
    video: StepProgress = Field(default_factory=StepProgress)
    metadata: StepProgress = Field(default_factory=StepProgress)


class ResumeState(BaseModel):
    last_completed_step: Optional[str] = None
    failed_scenes: List[int] = Field(default_factory=list)
    checkpoint_data: Dict[str, Any] = Field(default_factory=dict)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    language: str = Field(default="en", max_length=16)
    project_type: str = Field(default="deep_dive")


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    status: str
    description: Optional[str] = None
    language: str = "en"
    project_type: str = "deep_dive"
    created_at: datetime
    updated_at: datetime
    project_dir: Optional[str] = None
    input_files_status: Dict[str, Any] = Field(default_factory=dict)
    progress_state: Dict[str, Any] = Field(default_factory=dict)
    resume_state: Dict[str, Any] = Field(default_factory=dict)


class ProjectListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    status: str
    description: Optional[str] = None
    language: str = "en"
    project_type: str = "deep_dive"
    created_at: datetime
    updated_at: datetime
    progress_state: Dict[str, Any] = Field(default_factory=dict)


class FileUploadStatus(BaseModel):
    file_type: str
    filename: str
    size: int
    status: str = "ready"
    message: str = "File uploaded successfully"
    path: Optional[str] = None
