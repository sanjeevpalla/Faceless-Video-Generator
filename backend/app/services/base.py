import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, Optional
# (Any is also used in retry_async return type)

from app.core.logging import get_logger


class BaseService(ABC):
    """Abstract base service for all generation services."""

    service_name: str = "base"

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        progress_callback: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
        settings: Optional[Any] = None,
    ) -> None:
        self.project_id = project_id
        self.project_dir = project_dir
        self.progress_callback = progress_callback
        self.settings = settings
        self.logger = get_logger(f"{__name__}.{self.service_name}")
        self._cancelled = False
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Initially not paused

    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """Execute the service task and return result data."""
        raise NotImplementedError

    async def report_progress(
        self,
        progress: float,
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Report progress to the callback if provided."""
        clamped = min(100.0, max(0.0, progress))
        self.logger.debug(f"Progress {clamped:.1f}% - {message}")
        if self.progress_callback:
            if asyncio.iscoroutinefunction(self.progress_callback):
                await self.progress_callback(clamped, message, data or {})
            else:
                self.progress_callback(clamped, message, data or {})

    def cancel(self) -> None:
        """Request cancellation of the service."""
        self._cancelled = True
        self._pause_event.set()
        self.logger.info(f"Cancellation requested for {self.service_name}")

    def pause(self) -> None:
        """Pause execution."""
        self._paused = True
        self._pause_event.clear()
        self.logger.info(f"Pause requested for {self.service_name}")

    def resume(self) -> None:
        """Resume execution."""
        self._paused = False
        self._pause_event.set()
        self.logger.info(f"Resume requested for {self.service_name}")

    async def check_cancelled(self) -> None:
        """Raise if cancelled; wait if paused."""
        await self._pause_event.wait()
        if self._cancelled:
            from app.core.exceptions import ServiceError
            raise ServiceError(self.service_name, "Operation was cancelled")

    def ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_output_dir(self, subdir: str) -> Path:
        output_path = self.project_dir / subdir
        return self.ensure_dir(output_path)

    async def retry_async(
        self,
        coro_factory: Callable,
        max_attempts: int = 3,
        base_delay: float = 2.0,
        label: str = "operation",
    ) -> Any:
        """
        Retry an async operation with exponential backoff.
        Raises the last exception if all attempts fail.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            await self.check_cancelled()
            try:
                return await coro_factory()
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    self.logger.warning(
                        f"{label} attempt {attempt}/{max_attempts} failed: {exc}. "
                        f"Retrying in {delay:.1f}s…"
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"{label} failed after {max_attempts} attempts: {exc}")
        raise last_exc
