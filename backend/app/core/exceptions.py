from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse


class FacelessBaseException(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        detail: Optional[str] = None,
        status_code: int = 500,
    ) -> None:
        self.message = message
        self.code = code or self.__class__.__name__
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


class ProjectNotFoundError(FacelessBaseException):
    def __init__(self, project_id: str) -> None:
        super().__init__(
            message=f"Project '{project_id}' not found",
            code="PROJECT_NOT_FOUND",
            status_code=404,
        )
        self.project_id = project_id


class FileValidationError(FacelessBaseException):
    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(
            message=f"File validation failed for '{filename}': {reason}",
            code="FILE_VALIDATION_ERROR",
            status_code=422,
        )
        self.filename = filename
        self.reason = reason


class ServiceError(FacelessBaseException):
    def __init__(self, service: str, message: str, detail: Optional[str] = None) -> None:
        super().__init__(
            message=f"Service '{service}' error: {message}",
            code="SERVICE_ERROR",
            detail=detail,
            status_code=500,
        )
        self.service = service


class JobQueueError(FacelessBaseException):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=f"Job queue error: {message}",
            code="JOB_QUEUE_ERROR",
            status_code=500,
        )


class JobNotFoundError(FacelessBaseException):
    def __init__(self, job_id: str) -> None:
        super().__init__(
            message=f"Job '{job_id}' not found",
            code="JOB_NOT_FOUND",
            status_code=404,
        )


class SettingsError(FacelessBaseException):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=f"Settings error: {message}",
            code="SETTINGS_ERROR",
            status_code=400,
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found_handler(request: Request, exc: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.code},
        )

    @app.exception_handler(FileValidationError)
    async def file_validation_handler(request: Request, exc: FileValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.code, "detail": exc.reason},
        )

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.code, "detail": exc.detail},
        )

    @app.exception_handler(JobQueueError)
    async def job_queue_error_handler(request: Request, exc: JobQueueError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.code},
        )

    @app.exception_handler(JobNotFoundError)
    async def job_not_found_handler(request: Request, exc: JobNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.code},
        )

    @app.exception_handler(FacelessBaseException)
    async def base_exception_handler(request: Request, exc: FacelessBaseException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.code, "detail": exc.detail},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "code": "HTTP_ERROR"},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "code": "INTERNAL_ERROR", "detail": str(exc)},
        )
