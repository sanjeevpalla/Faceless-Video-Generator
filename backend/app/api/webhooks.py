"""
WhatsApp webhook receiver — the resume side of the Deep Dive trend-approval gate.

Endpoints:
  GET  /webhooks/whatsapp  — Meta's verification handshake
  POST /webhooks/whatsapp  — incoming message events (topic-selection replies)
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.core.dependencies import get_job_repo, get_project_repo, get_settings_repo
from app.core.events import connection_manager
from app.core.logging import get_logger
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.settings_repo import SettingsRepository
from app.services.pipeline_runner import enqueue_pipeline_job
from app.services.whatsapp_service import WhatsAppService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Meta's one-time webhook verification handshake."""
    wa_settings = await settings_repo.get_whatsapp_settings()
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == wa_settings.webhook_verify_token:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    project_repo: ProjectRepository = Depends(get_project_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Receive a WhatsApp interactive-list reply and resume the matching project's pipeline."""
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")

    wa_settings = await settings_repo.get_whatsapp_settings()
    if not WhatsAppService.verify_signature(raw_body, signature, wa_settings.app_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    reply = WhatsAppService.parse_interactive_reply(payload)
    if reply is None:
        # Delivery/read receipts, status updates, non-interactive messages, etc.
        return {"status": "ignored"}

    project = None
    if reply.context_message_id:
        project = await project_repo.get_by_pending_whatsapp_message_id(reply.context_message_id)
    if project is None:
        logger.warning(
            "WhatsApp reply with no matching pending prompt (context_message_id=%s)",
            reply.context_message_id,
        )
        return {"status": "no_pending_prompt"}

    wa_state = (project.resume_state or {}).get("whatsapp") or {}
    if wa_state.get("status") != "awaiting_whatsapp_reply":
        return {"status": "already_resolved"}

    candidates = wa_state.get("candidate_topics") or []
    selected = next((c for c in candidates if str(c.get("id")) == reply.row_id), None)
    if selected is None:
        raise HTTPException(status_code=400, detail="Selected row id not found among candidates")

    await project_repo.resolve_whatsapp_reply(project.id, selected)

    from pathlib import Path
    from app.services.pipeline_runner import project_dir_for
    pdir = project_dir_for(project)
    (pdir / "input").mkdir(parents=True, exist_ok=True)
    (pdir / "input" / "trend_selected.json").write_text(
        json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    await connection_manager.broadcast_to_project(
        project.id, "whatsapp_topic_selected", {"selected_topic": selected}
    )

    project = await project_repo.get_by_id(project.id)  # refresh after resolve
    job_id = await enqueue_pipeline_job(project, job_repo, settings_repo)

    return {"status": "resumed", "project_id": project.id, "job_id": job_id, "selected_topic": selected.get("title")}
