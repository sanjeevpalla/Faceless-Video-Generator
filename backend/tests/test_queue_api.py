"""Integration tests for the /api/v1/queue REST API."""
import pytest
from httpx import AsyncClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestQueueAPI:
    # ── GET /queue/status ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_queue_status_returns_200(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/status")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_queue_status_has_required_fields(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/status")
        assert r.status_code == 200
        data = r.json()
        assert "pending" in data
        assert "running" in data
        assert "queue_length" in data

    @pytest.mark.asyncio
    async def test_queue_status_all_fields(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/status")
        data = r.json()
        assert "pending" in data
        assert "running" in data
        assert "completed" in data
        assert "failed" in data
        assert "cancelled" in data
        assert "queue_length" in data
        assert "active_count" in data
        assert "total" in data
        assert "is_running" in data

    @pytest.mark.asyncio
    async def test_queue_status_counts_are_non_negative(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/status")
        data = r.json()
        for field in ["pending", "running", "completed", "failed", "cancelled",
                      "queue_length", "active_count", "total"]:
            assert data[field] >= 0, f"Field {field!r} should be >= 0"

    @pytest.mark.asyncio
    async def test_queue_status_is_running_is_bool(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/status")
        assert isinstance(r.json()["is_running"], bool)

    # ── GET /queue/jobs ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_queue_jobs_returns_200(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/jobs")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_list_queue_jobs_empty(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/jobs")
        assert r.status_code == 200
        data = r.json()
        assert "jobs" in data

    @pytest.mark.asyncio
    async def test_list_queue_jobs_has_total(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/jobs")
        data = r.json()
        assert "total" in data
        assert isinstance(data["total"], int)

    @pytest.mark.asyncio
    async def test_list_queue_jobs_is_list(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/jobs")
        data = r.json()
        assert isinstance(data["jobs"], list)

    @pytest.mark.asyncio
    async def test_list_queue_jobs_limit_param(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/jobs?limit=5")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_list_queue_jobs_status_filter(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/jobs?status=pending")
        assert r.status_code == 200
        data = r.json()
        # All returned jobs (if any) should have pending status
        for job in data["jobs"]:
            assert job["status"] == "pending"

    # ── GET /queue/jobs/{job_id} ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_queue_job_not_found(self, client: AsyncClient):
        r = await client.get("/api/v1/queue/jobs/nonexistent-job-id")
        assert r.status_code == 404

    # ── POST /queue/jobs/{job_id}/cancel ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self, client: AsyncClient):
        r = await client.post("/api/v1/queue/jobs/nonexistent-job-id/cancel")
        assert r.status_code == 404

    # ── POST /queue/pause ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_pause_queue_no_running_jobs(self, client: AsyncClient):
        r = await client.post("/api/v1/queue/pause")
        assert r.status_code == 200
        data = r.json()
        assert "paused" in data or "message" in data

    # ── POST /queue/resume ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_resume_queue_no_paused_jobs(self, client: AsyncClient):
        r = await client.post("/api/v1/queue/resume")
        assert r.status_code == 200
        data = r.json()
        assert "resumed" in data or "message" in data
