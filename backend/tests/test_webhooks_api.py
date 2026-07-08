"""Integration tests for the WhatsApp webhook receiver (/api/v1/webhooks/whatsapp)."""
import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.repositories.project_repo import ProjectRepository


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _configure_whatsapp(client: AsyncClient, secret: str = "test-secret", verify_token: str = "verify-me") -> None:
    r = await client.put(
        "/api/v1/settings",
        json={"whatsapp": {
            "phone_number_id": "123", "access_token": "tok",
            "webhook_verify_token": verify_token, "app_secret": secret,
            "recipient_number": "15551234567", "enabled": True,
        }},
    )
    assert r.status_code == 200


def _reply_payload(row_id: str, context_id: str) -> dict:
    return {
        "entry": [{"changes": [{"value": {"messages": [{
            "from": "15551234567", "id": "wamid.INCOMING",
            "context": {"id": context_id},
            "interactive": {"type": "list_reply", "list_reply": {"id": row_id, "title": "Picked"}},
        }]}}]}]
    }


class TestWebhookVerification:
    @pytest.mark.asyncio
    async def test_verification_handshake_succeeds(self, client: AsyncClient):
        await _configure_whatsapp(client, verify_token="my-token")
        r = await client.get(
            "/api/v1/webhooks/whatsapp",
            params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": "my-token"},
        )
        assert r.status_code == 200
        assert r.text == "12345"

    @pytest.mark.asyncio
    async def test_verification_handshake_wrong_token_fails(self, client: AsyncClient):
        await _configure_whatsapp(client, verify_token="my-token")
        r = await client.get(
            "/api/v1/webhooks/whatsapp",
            params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": "wrong"},
        )
        assert r.status_code == 403


class TestWebhookSignature:
    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, client: AsyncClient):
        await _configure_whatsapp(client, secret="right-secret")
        body = json.dumps(_reply_payload("0", "wamid.X")).encode()
        r = await client.post(
            "/api/v1/webhooks/whatsapp",
            content=body,
            headers={"x-hub-signature-256": "sha256=deadbeef", "content-type": "application/json"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_no_pending_prompt_returns_ok(self, client: AsyncClient):
        secret = "right-secret"
        await _configure_whatsapp(client, secret=secret)
        body = json.dumps(_reply_payload("0", "wamid.NEVER_SENT")).encode()
        r = await client.post(
            "/api/v1/webhooks/whatsapp",
            content=body,
            headers={"x-hub-signature-256": _sign(body, secret), "content-type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "no_pending_prompt"

    @pytest.mark.asyncio
    async def test_non_interactive_event_ignored(self, client: AsyncClient):
        secret = "right-secret"
        await _configure_whatsapp(client, secret=secret)
        body = json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.X"}]}}]}]}).encode()
        r = await client.post(
            "/api/v1/webhooks/whatsapp",
            content=body,
            headers={"x-hub-signature-256": _sign(body, secret), "content-type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"


class TestWebhookResolution:
    @pytest.mark.asyncio
    async def test_resolves_pending_prompt_and_enqueues_job(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path,
    ):
        secret = "right-secret"
        await _configure_whatsapp(client, secret=secret)

        repo = ProjectRepository(db_session)
        project = await repo.create(name="WA Test Project", project_dir=str(tmp_path), project_type="deep_dive")
        candidates = [{"id": "0", "title": "Topic A", "summary": "a"}, {"id": "1", "title": "Topic B", "summary": "b"}]
        await repo.set_awaiting_whatsapp_reply(project.id, candidates, "wamid.OUTBOUND", job_id="job-1")
        await db_session.commit()

        (tmp_path / "input").mkdir(parents=True, exist_ok=True)
        for sub in ["output", "cache", "logs", "temp", "metadata"]:
            (tmp_path / sub).mkdir(exist_ok=True)

        body = json.dumps(_reply_payload("1", "wamid.OUTBOUND")).encode()
        r = await client.post(
            "/api/v1/webhooks/whatsapp",
            content=body,
            headers={"x-hub-signature-256": _sign(body, secret), "content-type": "application/json"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "resumed"
        assert data["selected_topic"] == "Topic B"
        assert (tmp_path / "input" / "trend_selected.json").exists()
        selected = json.loads((tmp_path / "input" / "trend_selected.json").read_text())
        assert selected["title"] == "Topic B"

    @pytest.mark.asyncio
    async def test_duplicate_reply_is_idempotent(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path,
    ):
        secret = "right-secret"
        await _configure_whatsapp(client, secret=secret)

        repo = ProjectRepository(db_session)
        project = await repo.create(name="WA Test Project 2", project_dir=str(tmp_path), project_type="deep_dive")
        candidates = [{"id": "0", "title": "Only Topic", "summary": "a"}]
        await repo.set_awaiting_whatsapp_reply(project.id, candidates, "wamid.OUTBOUND2", job_id="job-1")
        await db_session.commit()

        (tmp_path / "input").mkdir(parents=True, exist_ok=True)
        for sub in ["output", "cache", "logs", "temp", "metadata"]:
            (tmp_path / sub).mkdir(exist_ok=True)

        body = json.dumps(_reply_payload("0", "wamid.OUTBOUND2")).encode()
        headers = {"x-hub-signature-256": _sign(body, secret), "content-type": "application/json"}

        r1 = await client.post("/api/v1/webhooks/whatsapp", content=body, headers=headers)
        assert r1.json()["status"] == "resumed"

        r2 = await client.post("/api/v1/webhooks/whatsapp", content=body, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "already_resolved"
