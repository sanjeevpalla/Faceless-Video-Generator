# Developer Guide

## Project layout

```
backend/
  app/
    api/          REST + WS endpoints (one file per domain)
    core/         Shared infrastructure: logging, events, exceptions, progress emitter
    models/       SQLAlchemy ORM (project, job, setting, log)
    repositories/ Async data-access layer (one class per model)
    schemas/      Pydantic v2 request/response models
    services/     Generation services — each extends BaseService
    workers/      Async priority job queue
  tests/          pytest suite (203 tests)

frontend/
  src/
    api/          Axios API clients, one per domain
    hooks/        React Query + custom hooks
    components/   Reusable UI (layout, common, project)
    pages/        8 page components
    store/        Zustand stores (projectStore, appStore)
```

---

## Adding a new generation service

1. Create `backend/app/services/my_service.py`:

```python
from app.services.base import BaseService
from app.core.exceptions import ServiceError

class MyService(BaseService):
    service_name = "my_service"

    async def execute(self) -> dict:
        await self.report_progress(10, "Starting...")
        await self.check_cancelled()
        # ... do work ...
        await self.report_progress(100, "Done")
        return {"result": "ok"}
```

2. Add a job type to `app/models/job.py` `JobType` enum.

3. Wire it in `app/api/jobs.py` `trigger_job` `make_coroutine` factory.

4. Add the frontend API client, hook, and page as needed.

---

## Adding a new API endpoint

1. Create `backend/app/api/my_feature.py` with an `APIRouter`.
2. Register it in `backend/app/api/router.py`:

```python
from app.api import my_feature
api_router.include_router(my_feature.router, prefix="/my_feature", tags=["my_feature"])
```

3. Add a corresponding `frontend/src/api/myFeature.ts` client.

---

## WebSocket event contract

Every event broadcast via `connection_manager.broadcast_to_project()` follows this shape:

```json
{
  "event": "job_progress",
  "project_id": "uuid",
  "job_id": "uuid",
  "data": { "progress": 42.5, "message": "Generating scene 5/20" },
  "timestamp": "2025-01-01T00:00:00Z"
}
```

**Known event types:**

| Event | When |
|---|---|
| `connected` | On WS connect (includes active jobs snapshot) |
| `job_started` | Job dequeued and begins running |
| `job_progress` | Incremental progress update |
| `job_completed` | Job finished successfully |
| `job_failed` | Job finished with error |
| `job_cancelled` | Job was cancelled |
| `scene_image_ready` | Single scene image generated |
| `scene_audio_ready` | Single scene audio generated |
| `log_entry` | Structured log line (streamed to LiveLogPanel) |
| `queue_updated` | Queue counts changed |

Frontend routing is in `frontend/src/hooks/useWebSocket.ts`.

---

## Job queue architecture

```
POST /jobs/trigger/{project_id}/{job_type}
  → creates DB Job record
  → creates QueueJob(coroutine_factory, on_complete, on_error)
  → QueueManager.enqueue(queue_job)
  → worker picks up job
  → service.execute() runs
  → progress_callback → broadcast_to_project("job_progress", ...)
  → on_complete → broadcast_to_project("job_completed", ...)
```

The queue is priority-based: single-scene regenerations get priority=10 (higher than batch=0).

---

## Retry logic

All services inherit `retry_async()` from `BaseService`:

```python
result = await self.retry_async(
    lambda: self.submit_to_comfyui(workflow),
    max_attempts=3,
    base_delay=2.0,
    label="ComfyUI submit",
)
```

Retries with exponential backoff: 2s, 4s, 8s.

---

## Resume support

Both `ImageGenerationService` and `VoiceGenerationService` skip scenes that already have output files on disk. This means you can:
- Kill a long generation mid-way
- Restart it — already-done scenes are skipped instantly
- Only the missing scenes run again

The image service checks `images/scene_NNN.png` exists and is non-zero.
The voice service checks `audio/scene_NNN.wav` exists and is non-zero.

---

## Asset cache

Content-addressed caching by prompt/narration hash:

- Image prompts → `cache/images/{sha256_16}.json`
- Voice narrations → `cache/audio/{sha256_16}.json`
- Subtitles → `cache/subtitles/{audio_hash_16}.json`

If the cached file still exists on disk, generation is skipped entirely.

---

## Running tests

```bash
cd backend
python -m pytest tests/ -v
python -m pytest tests/ -k "validation"     # run specific tests
python -m pytest tests/ --cov=app          # with coverage
```

Tests use:
- `StaticPool` in-memory SQLite (no file I/O)
- Mock services (no GPU/Piper/Whisper/FFmpeg required)
- Both `get_db` and `get_db_session` overridden in `conftest.py`

---

## Frontend state management

Two Zustand stores:

**`projectStore`**
- `currentProject` — the active project object
- `generationProgress` — per-step progress (images, voice, subtitles, thumbnail, video, metadata)
- Updated by `useWebSocket` event handler on `job_progress` / `job_completed` / `job_failed`

**`appStore`**
- `wsConnected` — connection status shown in TopBar
- `activeJobs` — map of currently running jobs (feeds `ActiveJobsBar`)
- `notifications` — toast-style notification queue

---

## Code style

- Python: type hints throughout, no `Any` unless unavoidable
- TypeScript: strict mode, no `any`
- No inline comments unless non-obvious
- Services: always call `await self.check_cancelled()` in loops
- Frontend hooks: always use React Query for server state, Zustand for client state
