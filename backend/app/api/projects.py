import re
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session, get_project_repo
from app.core.exceptions import FileValidationError, ProjectNotFoundError
from app.models.project import ProjectStatus
from app.repositories.project_repo import ProjectRepository
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.project import (
    FileUploadStatus,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.config import get_settings

router = APIRouter()


def _slugify(name: str) -> str:
    """Turn a project name into a safe filesystem folder name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)       # drop special chars
    slug = re.sub(r"[\s]+", "_", slug)          # spaces → underscores
    slug = re.sub(r"_+", "_", slug).strip("_")  # collapse duplicates
    return slug[:60] or "project"               # cap length, never empty


def _unique_dir(base: Path) -> Path:
    """Return *base* if it does not exist, otherwise *base_2*, *base_3*, …"""
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = base.parent / f"{base.name}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


ALLOWED_FILE_TYPES = {
    "script": [".txt", ".md"],
    "scenes": [".json"],
    "image_prompts": [".txt"],
    "thumbnail_prompt": [".txt"],
    "seo": [".json"],
}

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def _validate_file(file_type: str, filename: str, file_size: int) -> None:
    ext = Path(filename).suffix.lower()
    allowed = ALLOWED_FILE_TYPES.get(file_type, [])
    if allowed and ext not in allowed:
        raise FileValidationError(
            filename, f"Expected one of {allowed}, got {ext!r}"
        )
    if file_size > MAX_FILE_SIZE:
        raise FileValidationError(filename, f"File too large ({file_size} bytes, max {MAX_FILE_SIZE})")


@router.get("", response_model=PaginatedResponse[ProjectListResponse])
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    repo: ProjectRepository = Depends(get_project_repo),
):
    projects, total = await repo.get_all(
        page=page,
        page_size=page_size,
        status=status,
        exclude_archived=not include_archived,
    )
    return PaginatedResponse.create(
        items=[ProjectListResponse.model_validate(p, from_attributes=True) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    repo: ProjectRepository = Depends(get_project_repo),
):
    existing = await repo.get_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A project named \"{data.name}\" already exists. Please choose a different name.",
        )

    settings = get_settings()
    project_id = str(uuid.uuid4())
    project_dir = settings.PROJECTS_DIR / _slugify(data.name)
    project_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ["input", "images", "audio", "subtitles", "thumbnail",
                   "output", "cache", "logs", "temp", "metadata"]:
        (project_dir / subdir).mkdir(exist_ok=True)
    for cache_sub in ["images", "audio", "subtitles", "thumbnail"]:
        (project_dir / "cache" / cache_sub).mkdir(exist_ok=True)

    project = await repo.create(
        name=data.name,
        description=data.description,
        project_dir=str(project_dir),
        language=data.language,
        project_type=data.project_type,
    )
    # Patch the ID to use our generated one (workaround: recreate with ID)
    return ProjectResponse.model_validate(project, from_attributes=True)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    repo: ProjectRepository = Depends(get_project_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)
    return ProjectResponse.model_validate(project, from_attributes=True)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    repo: ProjectRepository = Depends(get_project_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    update_kwargs = data.model_dump(exclude_none=True)
    project = await repo.update(project_id, **update_kwargs)
    return ProjectResponse.model_validate(project, from_attributes=True)


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: str,
    delete_files: bool = Query(default=False),
    repo: ProjectRepository = Depends(get_project_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    if delete_files and project.project_dir:
        project_path = Path(project.project_dir)
        if project_path.exists():
            shutil.rmtree(project_path, ignore_errors=True)

    deleted = await repo.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete project")
    return MessageResponse(message=f"Project {project_id} deleted successfully")


@router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: str,
    repo: ProjectRepository = Depends(get_project_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)
    project = await repo.archive(project_id)
    return ProjectResponse.model_validate(project, from_attributes=True)


@router.post("/{project_id}/duplicate", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_project(
    project_id: str,
    repo: ProjectRepository = Depends(get_project_repo),
):
    source = await repo.get_by_id(project_id)
    if not source:
        raise ProjectNotFoundError(project_id)

    settings = get_settings()
    new_id = str(uuid.uuid4())
    new_dir = _unique_dir(settings.PROJECTS_DIR / _slugify(f"{source.name} copy"))
    new_dir.mkdir(parents=True, exist_ok=True)

    if source.project_dir and Path(source.project_dir).exists():
        shutil.copytree(source.project_dir, str(new_dir), dirs_exist_ok=True)

    new_project = await repo.create(
        name=f"{source.name} (copy)",
        description=source.description,
        project_dir=str(new_dir),
        language=source.language or "en",
    )
    return ProjectResponse.model_validate(new_project, from_attributes=True)


async def _handle_file_upload(
    project_id: str,
    file_type: str,
    file: UploadFile,
    repo: ProjectRepository,
) -> FileUploadStatus:
    project = await repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    content = await file.read()
    _validate_file(file_type, file.filename or "unknown", len(content))

    project_dir = Path(project.project_dir) if project.project_dir else (get_settings().PROJECTS_DIR / project_id)
    input_dir = project_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "file").suffix.lower()
    dest_filename = f"{file_type}{ext}"
    dest_path = input_dir / dest_filename

    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(content)

    file_data = {
        "status": "ready",
        "filename": file.filename,
        "path": str(dest_path),
        "size": len(content),
    }
    await repo.update_input_files_status(project_id, file_type, file_data)

    return FileUploadStatus(
        file_type=file_type,
        filename=file.filename or dest_filename,
        size=len(content),
        status="ready",
        path=str(dest_path),
    )


@router.post("/{project_id}/files/script", response_model=FileUploadStatus)
async def upload_script(
    project_id: str,
    file: UploadFile = File(...),
    repo: ProjectRepository = Depends(get_project_repo),
):
    return await _handle_file_upload(project_id, "script", file, repo)


@router.post("/{project_id}/files/scenes", response_model=FileUploadStatus)
async def upload_scenes(
    project_id: str,
    file: UploadFile = File(...),
    repo: ProjectRepository = Depends(get_project_repo),
):
    return await _handle_file_upload(project_id, "scenes", file, repo)


@router.post("/{project_id}/files/image_prompts", response_model=FileUploadStatus)
async def upload_image_prompts(
    project_id: str,
    file: UploadFile = File(...),
    repo: ProjectRepository = Depends(get_project_repo),
):
    return await _handle_file_upload(project_id, "image_prompts", file, repo)


@router.post("/{project_id}/files/thumbnail_prompt", response_model=FileUploadStatus)
async def upload_thumbnail_prompt(
    project_id: str,
    file: UploadFile = File(...),
    repo: ProjectRepository = Depends(get_project_repo),
):
    return await _handle_file_upload(project_id, "thumbnail_prompt", file, repo)



@router.post("/{project_id}/files/seo", response_model=FileUploadStatus)
async def upload_seo(
    project_id: str,
    file: UploadFile = File(...),
    repo: ProjectRepository = Depends(get_project_repo),
):
    return await _handle_file_upload(project_id, "seo", file, repo)


@router.post("/{project_id}/validate", response_model=dict)
async def validate_project_files(
    project_id: str,
    repo: ProjectRepository = Depends(get_project_repo),
):
    """Deep-validate all input files for a project."""
    project = await repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    project_dir = Path(project.project_dir) if project.project_dir else (get_settings().PROJECTS_DIR / project_id)

    from app.services.validation_service import ProjectValidationService
    svc = ProjectValidationService(project_dir)
    result = svc.validate_all()

    # Update project status based on validation
    all_valid = result["all_valid"]
    if all_valid:
        await repo.update_status(project_id, ProjectStatus.CREATED)

    return result


@router.delete("/{project_id}/files/{file_type}", response_model=MessageResponse)
async def delete_file(
    project_id: str,
    file_type: str,
    repo: ProjectRepository = Depends(get_project_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise ProjectNotFoundError(project_id)

    file_status = (project.input_files_status or {}).get(file_type, {})
    file_path = file_status.get("path")
    if file_path and Path(file_path).exists():
        Path(file_path).unlink(missing_ok=True)

    await repo.update_input_files_status(
        project_id, file_type,
        {"status": "missing", "filename": None, "path": None, "size": None},
    )
    return MessageResponse(message=f"File '{file_type}' removed from project")
