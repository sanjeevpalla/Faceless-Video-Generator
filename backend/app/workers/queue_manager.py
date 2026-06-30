import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class QueueJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueJob:
    def __init__(
        self,
        job_id: str,
        project_id: str,
        job_type: str,
        coroutine_factory: Callable[[], Coroutine],
        priority: float = 0.0,
        on_progress: Optional[Callable[[float, str, Dict], None]] = None,
        on_complete: Optional[Callable[[Dict], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self.job_id = job_id
        self.project_id = project_id
        self.job_type = job_type
        self.coroutine_factory = coroutine_factory
        self.priority = priority
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.status = QueueJobStatus.PENDING
        self.progress = 0.0
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.result: Optional[Dict] = None
        self._task: Optional[asyncio.Task] = None
        self._cancel_event = asyncio.Event()


class QueueManager:
    """Async job queue manager with priority, pause, resume, and cancel support."""

    def __init__(self, max_concurrent: int = 1) -> None:
        self.max_concurrent = max_concurrent
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._active_jobs: Dict[str, QueueJob] = {}
        self._all_jobs: Dict[str, QueueJob] = {}
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info(f"QueueManager starting with max_concurrent={self.max_concurrent}")
        for i in range(self.max_concurrent):
            task = asyncio.create_task(self._worker(worker_id=i))
            self._worker_tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        logger.info("QueueManager stopped")

    async def enqueue(self, job: QueueJob) -> str:
        async with self._lock:
            self._all_jobs[job.job_id] = job
        # Priority queue: lower number = higher priority, negate for max-heap behavior
        priority_key = -job.priority
        await self._queue.put((priority_key, job.created_at.timestamp(), job.job_id))
        logger.info(f"Enqueued job {job.job_id} type={job.job_type} priority={job.priority}")
        return job.job_id

    async def cancel(self, job_id: str) -> bool:
        job = self._all_jobs.get(job_id)
        if not job:
            return False

        job.status = QueueJobStatus.CANCELLED
        job._cancel_event.set()

        if job._task and not job._task.done():
            job._task.cancel()
            try:
                await job._task
            except (asyncio.CancelledError, Exception):
                pass

        async with self._lock:
            self._active_jobs.pop(job_id, None)

        logger.info(f"Cancelled job {job_id}")
        return True

    async def pause(self, job_id: str) -> bool:
        job = self._all_jobs.get(job_id)
        if not job or job.status != QueueJobStatus.RUNNING:
            return False
        job.status = QueueJobStatus.PAUSED
        logger.info(f"Paused job {job_id}")
        return True

    async def resume(self, job_id: str) -> bool:
        job = self._all_jobs.get(job_id)
        if not job or job.status != QueueJobStatus.PAUSED:
            return False
        job.status = QueueJobStatus.RUNNING
        logger.info(f"Resumed job {job_id}")
        return True

    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self._all_jobs.get(job_id)
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error,
        }

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        return [self.get_status(jid) for jid in self._all_jobs]

    def get_queue_length(self) -> int:
        return self._queue.qsize()

    def get_active_count(self) -> int:
        return len(self._active_jobs)

    async def _worker(self, worker_id: int) -> None:
        logger.info(f"Worker {worker_id} started")
        while self._running:
            try:
                try:
                    _, _, job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                job = self._all_jobs.get(job_id)
                if not job or job.status == QueueJobStatus.CANCELLED:
                    self._queue.task_done()
                    continue

                async with self._semaphore:
                    await self._execute_job(job)

                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Worker {worker_id} error: {exc}", exc_info=True)

        logger.info(f"Worker {worker_id} stopped")

    async def _broadcast_queue_update(self, project_id: Optional[str] = None) -> None:
        """Emit a queue_updated event so dashboards stay in sync."""
        try:
            from app.core.progress import emit_queue_updated
            statuses = self.get_all_statuses()
            await emit_queue_updated(
                project_id=project_id,
                pending=sum(1 for s in statuses if s and s.get("status") == "pending"),
                running=sum(1 for s in statuses if s and s.get("status") == "running"),
                completed=sum(1 for s in statuses if s and s.get("status") == "completed"),
                failed=sum(1 for s in statuses if s and s.get("status") == "failed"),
            )
        except Exception:
            pass

    async def _execute_job(self, job: QueueJob) -> None:
        job.status = QueueJobStatus.RUNNING
        job.started_at = datetime.utcnow()

        async with self._lock:
            self._active_jobs[job.job_id] = job

        logger.info(f"Executing job {job.job_id} type={job.job_type}")
        await self._broadcast_queue_update(job.project_id)

        try:
            coro = job.coroutine_factory()
            job._task = asyncio.current_task()
            result = await coro
            job.status = QueueJobStatus.COMPLETED
            job.result = result
            job.progress = 100.0
            job.completed_at = datetime.utcnow()
            logger.info(f"Job {job.job_id} completed successfully")
            if job.on_complete:
                try:
                    await job.on_complete(result) if asyncio.iscoroutinefunction(job.on_complete) else job.on_complete(result)
                except Exception as cb_exc:
                    logger.error(f"on_complete callback error: {cb_exc}")
        except asyncio.CancelledError:
            job.status = QueueJobStatus.CANCELLED
            job.completed_at = datetime.utcnow()
            logger.info(f"Job {job.job_id} was cancelled")
        except Exception as exc:
            job.status = QueueJobStatus.FAILED
            job.error = str(exc)
            job.completed_at = datetime.utcnow()
            logger.error(f"Job {job.job_id} failed: {exc}", exc_info=True)
            if job.on_error:
                try:
                    await job.on_error(exc) if asyncio.iscoroutinefunction(job.on_error) else job.on_error(exc)
                except Exception as cb_exc:
                    logger.error(f"on_error callback error: {cb_exc}")
        finally:
            async with self._lock:
                self._active_jobs.pop(job.job_id, None)
            await self._broadcast_queue_update(job.project_id)


# Global singleton instance
queue_manager = QueueManager(max_concurrent=1)
