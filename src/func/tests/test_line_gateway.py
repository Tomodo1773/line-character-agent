"""Gateway の webhook 検証とキュー投入のテスト。"""

import base64
import hashlib
import hmac
import json

import azure.functions as func
import pytest

CHANNEL_SECRET = "test-channel-secret"

TEXT_MESSAGE = {"type": "text", "id": "1", "text": "こんにちは", "quoteToken": "q1"}
AUDIO_MESSAGE = {"type": "audio", "id": "1", "duration": 1000, "contentProvider": {"type": "line"}}


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", CHANNEL_SECRET)
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("COSMOS_DB_ACCOUNT_URL", "https://example.documents.azure.com:443/")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.services.ai.azure.com/api/projects/dummy")
    monkeypatch.setenv("HOSTED_AGENT_NAME", "character-agent")

    import config
    import line_client

    config.get_settings.cache_clear()
    line_client._webhook_parser.cache_clear()
    yield
    config.get_settings.cache_clear()
    line_client._webhook_parser.cache_clear()


class FakeQueue:
    """`func.Out` の代わり。投入されたメッセージを覚えておく。"""

    def __init__(self) -> None:
        self.messages: list[str] | None = None

    def set(self, value: list[str]) -> None:
        self.messages = value


def _sign(body: str) -> str:
    digest = hmac.new(CHANNEL_SECRET.encode(), body.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _request(body: str, signature: str) -> func.HttpRequest:
    return func.HttpRequest(
        method="POST",
        url="/api/line/callback",
        headers={"x-line-signature": signature},
        body=body.encode("utf-8"),
    )


def _webhook_body(message: dict) -> str:
    return json.dumps(
        {
            "destination": "Ubot",
            "events": [
                {
                    "type": "message",
                    "mode": "active",
                    "timestamp": 1700000000000,
                    "replyToken": "reply-token",
                    "source": {"type": "user", "userId": "U123"},
                    "webhookEventId": "01",
                    "deliveryContext": {"isRedelivery": False},
                    "message": message,
                }
            ],
        }
    )


def test_rejects_invalid_signature():
    import line_gateway

    body = _webhook_body(TEXT_MESSAGE)
    response = line_gateway.line_gateway(_request(body, "invalid"), FakeQueue())

    assert response.status_code == 400


def test_enqueues_text_message_with_trace_context():
    import line_gateway

    body = _webhook_body(TEXT_MESSAGE)
    queue = FakeQueue()
    response = line_gateway.line_gateway(_request(body, _sign(body)), queue)

    assert response.status_code == 200
    payload = json.loads(queue.messages[0])
    assert payload["user_id"] == "U123"
    assert payload["reply_token"] == "reply-token"
    assert payload["text"] == "こんにちは"
    # Storage Queue は trace context を運ばないため、本文に載せて Worker へ渡す。
    assert "trace_context" in payload


def test_replies_guidance_for_non_text_message(monkeypatch: pytest.MonkeyPatch):
    import line_client
    import line_gateway

    replies = []
    monkeypatch.setattr(line_client, "reply_or_push", lambda *args: replies.append(args))

    body = _webhook_body(AUDIO_MESSAGE)
    queue = FakeQueue()
    response = line_gateway.line_gateway(_request(body, _sign(body)), queue)

    assert response.status_code == 200
    assert queue.messages is None
    assert replies == [("U123", "reply-token", line_gateway.NON_TEXT_GUIDANCE)]
