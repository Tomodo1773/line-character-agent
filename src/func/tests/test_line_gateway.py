"""Gateway の webhook 検証とキュー投入のテスト。"""

import base64
import hashlib
import hmac
import json

import azure.functions as func
import pytest

from tests.conftest import CHANNEL_SECRET, DIARY_USER_ID

TEXT_MESSAGE = {"type": "text", "id": "1", "text": "こんにちは", "quoteToken": "q1"}
AUDIO_MESSAGE = {"type": "audio", "id": "1", "duration": 1000, "contentProvider": {"type": "line"}}


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


def _webhook_body(message: dict, user_id: str = DIARY_USER_ID) -> str:
    return json.dumps(
        {
            "destination": "Ubot",
            "events": [
                {
                    "type": "message",
                    "mode": "active",
                    "timestamp": 1700000000000,
                    "replyToken": "reply-token",
                    "source": {"type": "user", "userId": user_id},
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
    assert payload["user_id"] == DIARY_USER_ID
    assert payload["reply_token"] == "reply-token"
    assert payload["text"] == "こんにちは"
    assert payload["webhook_event_id"] == "01"
    assert payload["timestamp"] == 1700000000000
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
    assert replies == [(DIARY_USER_ID, "reply-token", line_gateway.NON_TEXT_GUIDANCE)]


@pytest.mark.parametrize("message", [TEXT_MESSAGE, AUDIO_MESSAGE])
def test_ignores_messages_from_unauthorized_user(message: dict, monkeypatch: pytest.MonkeyPatch):
    import line_client
    import line_gateway

    replies = []
    monkeypatch.setattr(line_client, "reply_or_push", lambda *args: replies.append(args))

    body = _webhook_body(message, user_id="U-other")
    queue = FakeQueue()
    response = line_gateway.line_gateway(_request(body, _sign(body)), queue)

    assert response.status_code == 200
    assert queue.messages is None
    assert replies == []
