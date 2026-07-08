"""
WhatsAppService — Meta WhatsApp Cloud API client for the Human-In-The-Loop topic
approval gate and unattended-run failure alerts.

Sends interactive list messages (tappable topic rows) and parses/validates the
webhook replies Meta delivers back. Uses httpx (already a project dependency)
for the Graph API calls and stdlib hmac/hashlib for webhook signature
verification — no new third-party dependency needed for this service.
"""
import hashlib
import hmac
import json
from typing import Any, Dict, List, NamedTuple, Optional

import httpx

from app.core.logging import get_logger
from app.schemas.settings import WhatsAppSettings

logger = get_logger(__name__)

GRAPH_API_VERSION = "v22.0"

# Meta's interactive-list-message row limits.
MAX_ROW_TITLE_CHARS = 24
MAX_ROW_DESCRIPTION_CHARS = 72
MAX_ROWS = 10


class WhatsAppReply(NamedTuple):
    row_id: str
    row_title: str
    from_wa_id: str
    context_message_id: Optional[str]


class WhatsAppConfigError(Exception):
    """Raised when WhatsApp credentials are missing/incomplete."""


class WhatsAppService:
    def __init__(self, settings: WhatsAppSettings) -> None:
        if not settings.phone_number_id or not settings.access_token or not settings.recipient_number:
            raise WhatsAppConfigError(
                "WhatsApp is not configured — set phone_number_id, access_token, and "
                "recipient_number in Settings before using the WhatsApp HITL gate."
            )
        self.settings = settings
        self._base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.phone_number_id}/messages"

    async def send_topic_list(
        self,
        candidates: List[Dict[str, str]],
        header_text: str = "New video — pick a topic",
        body_text: str = "Tap a topic below to start generating this video.",
    ) -> str:
        """Send an interactive list message with up to MAX_ROWS candidate topics.

        Returns Meta's outbound message id (wamid), used later to match the
        user's reply back to this specific prompt.
        """
        rows = [
            {
                "id": str(c["id"]),
                "title": (c.get("title") or "")[:MAX_ROW_TITLE_CHARS],
                "description": (c.get("summary") or "")[:MAX_ROW_DESCRIPTION_CHARS],
            }
            for c in candidates[:MAX_ROWS]
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": self.settings.recipient_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": header_text[:60]},
                "body": {"text": body_text},
                "action": {
                    "button": "View Topics",
                    "sections": [{"title": "Candidate Topics", "rows": rows}],
                },
            },
        }
        data = await self._post(payload)
        messages = data.get("messages") or []
        if not messages:
            raise RuntimeError(f"WhatsApp send did not return a message id: {data}")
        return messages[0]["id"]

    async def send_alert_text(self, message: str) -> None:
        """Best-effort failure notification — never raises, since a WhatsApp outage
        must not mask the underlying pipeline failure it's reporting."""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": self.settings.recipient_number,
                "type": "text",
                "text": {"body": message[:4096]},
            }
            await self._post(payload)
        except Exception as exc:
            logger.warning("WhatsApp alert failed to send: %s", exc)

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self._base_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.settings.access_token}"},
            )
            if response.status_code >= 400:
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text
                logger.error("WhatsApp API error %s: %s", response.status_code, detail)
                response.raise_for_status()
            return response.json()

    @staticmethod
    def verify_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
        if not signature_header or not app_secret:
            return False
        prefix = "sha256="
        if not signature_header.startswith(prefix):
            return False
        expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header[len(prefix):])

    @staticmethod
    def parse_interactive_reply(payload: Dict[str, Any]) -> Optional[WhatsAppReply]:
        """Extract a list_reply from Meta's webhook payload, or None for
        non-interactive events (delivery/read receipts, status updates, etc.)."""
        try:
            entries = payload.get("entry") or []
            for entry in entries:
                for change in entry.get("changes") or []:
                    value = change.get("value") or {}
                    for message in value.get("messages") or []:
                        interactive = message.get("interactive") or {}
                        list_reply = interactive.get("list_reply")
                        if not list_reply:
                            continue
                        return WhatsAppReply(
                            row_id=str(list_reply.get("id")),
                            row_title=str(list_reply.get("title") or ""),
                            from_wa_id=str(message.get("from") or ""),
                            context_message_id=(message.get("context") or {}).get("id"),
                        )
        except Exception as exc:
            logger.warning("Failed to parse WhatsApp webhook payload: %s", exc)
        return None
