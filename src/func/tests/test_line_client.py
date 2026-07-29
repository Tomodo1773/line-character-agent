"""reply / push のフォールバック判断のテスト。"""

import pytest
from linebot.v3.messaging.exceptions import ApiException

import line_client


class FakeMessagingApi:
    def __init__(self, reply_status: int | None = None) -> None:
        self.reply_status = reply_status
        self.replied: list = []
        self.pushed: list = []

    def reply_message(self, request) -> None:
        if self.reply_status:
            raise ApiException(status=self.reply_status, reason="Invalid reply token")
        self.replied.append(request)

    def push_message(self, request) -> None:
        self.pushed.append(request)


def _use(api: FakeMessagingApi, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(line_client, "_messaging_api", lambda: api)


def test_uses_reply_when_the_token_is_still_valid(monkeypatch: pytest.MonkeyPatch):
    api = FakeMessagingApi()
    _use(api, monkeypatch)

    line_client.reply_or_push("U123", "reply-token", "やっほー")

    assert len(api.replied) == 1
    assert api.pushed == []


def test_falls_back_to_push_when_the_reply_token_expired(monkeypatch: pytest.MonkeyPatch):
    # reply token は受信から1分で失効し、LINE は 400 を返す。
    api = FakeMessagingApi(reply_status=400)
    _use(api, monkeypatch)

    line_client.reply_or_push("U123", "reply-token", "やっほー")

    assert api.replied == []
    assert len(api.pushed) == 1
    assert api.pushed[0].to == "U123"
