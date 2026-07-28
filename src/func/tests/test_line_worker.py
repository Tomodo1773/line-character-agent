"""Worker の会話 ID の扱いと返信のテスト。"""

import json

import pytest

import agent
import line_client
import line_worker
import users


class FakeQueueMessage:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def get_body(self) -> bytes:
        return self._body


@pytest.fixture
def stubs(monkeypatch: pytest.MonkeyPatch):
    """外部依存（LINE / Cosmos DB / エージェント）を差し替える。"""

    class Stubs:
        def __init__(self) -> None:
            self.stored: dict[str, str] = {}
            self.replies: list[tuple[str, str, str]] = []
            self.responded: list[tuple[str, str]] = []
            self.created = 0

    stubs = Stubs()

    def create_conversation() -> str:
        stubs.created += 1
        return f"conv-{stubs.created}"

    def respond(conversation_id: str, text: str) -> str:
        stubs.responded.append((conversation_id, text))
        return "エージェントの応答"

    monkeypatch.setattr(line_client, "show_loading_animation", lambda user_id: None)
    monkeypatch.setattr(line_client, "reply_or_push", lambda *args: stubs.replies.append(args))
    monkeypatch.setattr(users, "get_conversation_id", stubs.stored.get)
    monkeypatch.setattr(users, "save_conversation_id", stubs.stored.__setitem__)
    monkeypatch.setattr(agent, "create_conversation", create_conversation)
    monkeypatch.setattr(agent, "respond", respond)
    return stubs


def _run(text: str) -> None:
    line_worker.line_worker(
        FakeQueueMessage({"user_id": "U123", "reply_token": "reply-token", "text": text, "trace_context": {}})
    )


def test_starts_a_conversation_when_user_has_none(stubs):
    _run("こんにちは")

    assert stubs.stored == {"U123": "conv-1"}
    assert stubs.responded == [("conv-1", "こんにちは")]
    assert stubs.replies == [("U123", "reply-token", "エージェントの応答")]


def test_continues_the_stored_conversation(stubs):
    stubs.stored["U123"] = "conv-existing"

    _run("その続き")

    assert stubs.created == 0
    assert stubs.responded == [("conv-existing", "その続き")]


def test_reset_keyword_switches_to_a_new_conversation(stubs):
    stubs.stored["U123"] = "conv-old"

    _run(f"  {line_worker.RESET_KEYWORD}  ")

    assert stubs.stored == {"U123": "conv-1"}
    # リセット時はエージェントを呼ばずに定型文を返す。
    assert stubs.responded == []
    assert stubs.replies == [("U123", "reply-token", line_worker.RESET_REPLY)]


def test_replies_error_message_when_the_agent_fails(stubs, monkeypatch: pytest.MonkeyPatch):
    def boom(conversation_id: str, text: str) -> str:
        raise RuntimeError("agent is down")

    monkeypatch.setattr(agent, "respond", boom)

    _run("こんにちは")

    assert stubs.replies == [("U123", "reply-token", line_worker.ERROR_REPLY)]
