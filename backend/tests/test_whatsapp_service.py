"""Unit tests for WhatsAppService — signature verification and webhook parsing."""
import hashlib
import hmac
import json

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.whatsapp_service import WhatsAppService, WhatsAppConfigError
from app.schemas.settings import WhatsAppSettings


class TestVerifySignature:
    def test_valid_signature_passes(self):
        body = b'{"hello": "world"}'
        secret = "shh"
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        header = f"sha256={digest}"
        assert WhatsAppService.verify_signature(body, header, secret) is True

    def test_invalid_signature_fails(self):
        body = b'{"hello": "world"}'
        assert WhatsAppService.verify_signature(body, "sha256=deadbeef", "shh") is False

    def test_missing_prefix_fails(self):
        body = b'{"hello": "world"}'
        digest = hmac.new(b"shh", body, hashlib.sha256).hexdigest()
        assert WhatsAppService.verify_signature(body, digest, "shh") is False

    def test_empty_header_fails(self):
        assert WhatsAppService.verify_signature(b"x", "", "shh") is False

    def test_empty_secret_fails(self):
        assert WhatsAppService.verify_signature(b"x", "sha256=abc", "") is False

    def test_tampered_body_fails(self):
        secret = "shh"
        digest = hmac.new(secret.encode(), b"original", hashlib.sha256).hexdigest()
        header = f"sha256={digest}"
        assert WhatsAppService.verify_signature(b"tampered", header, secret) is False


class TestParseInteractiveReply:
    def _payload(self, row_id="2", context_id="wamid.OUTBOUND"):
        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "15551234567",
                            "id": "wamid.INCOMING",
                            "context": {"id": context_id},
                            "interactive": {
                                "type": "list_reply",
                                "list_reply": {"id": row_id, "title": "Some Topic"},
                            },
                        }]
                    }
                }]
            }]
        }

    def test_parses_list_reply(self):
        reply = WhatsAppService.parse_interactive_reply(self._payload())
        assert reply is not None
        assert reply.row_id == "2"
        assert reply.row_title == "Some Topic"
        assert reply.from_wa_id == "15551234567"
        assert reply.context_message_id == "wamid.OUTBOUND"

    def test_non_interactive_event_returns_none(self):
        payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.X"}]}}]}]}
        assert WhatsAppService.parse_interactive_reply(payload) is None

    def test_malformed_payload_returns_none(self):
        assert WhatsAppService.parse_interactive_reply({"garbage": True}) is None

    def test_missing_context_returns_none_context_id(self):
        payload = self._payload()
        del payload["entry"][0]["changes"][0]["value"]["messages"][0]["context"]
        reply = WhatsAppService.parse_interactive_reply(payload)
        assert reply is not None
        assert reply.context_message_id is None


class TestWhatsAppServiceConfig:
    def test_missing_credentials_raises(self):
        with pytest.raises(WhatsAppConfigError):
            WhatsAppService(WhatsAppSettings())

    def test_complete_credentials_construct_ok(self):
        svc = WhatsAppService(WhatsAppSettings(
            phone_number_id="123", access_token="tok", recipient_number="1555",
        ))
        assert svc.settings.phone_number_id == "123"


class TestSendTopicListRowLimits:
    @pytest.mark.asyncio
    async def test_truncates_and_caps_rows(self, monkeypatch):
        svc = WhatsAppService(WhatsAppSettings(
            phone_number_id="123", access_token="tok", recipient_number="1555",
        ))

        captured = {}

        async def fake_post(self, payload):
            captured["payload"] = payload
            return {"messages": [{"id": "wamid.NEW"}]}

        monkeypatch.setattr(WhatsAppService, "_post", fake_post)

        candidates = [
            {"id": str(i), "title": "X" * 40, "summary": "Y" * 100}
            for i in range(15)
        ]
        message_id = await svc.send_topic_list(candidates)

        assert message_id == "wamid.NEW"
        rows = captured["payload"]["interactive"]["action"]["sections"][0]["rows"]
        assert len(rows) == 10  # capped at MAX_ROWS
        assert all(len(r["title"]) <= 24 for r in rows)
        assert all(len(r["description"]) <= 72 for r in rows)
