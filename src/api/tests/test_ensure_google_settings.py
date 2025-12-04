"""Tests for ensure_google_settings_command behavior with state management"""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from chatbot.agent.character import ensure_google_settings_node


def test_ensure_google_settings_node_returns_auth_message(monkeypatch):
    """OAuth設定がない場合に認可URLを案内するレスポンスになることを検証"""

    class DummyUserRepository:
        def ensure_user(self, userid: str) -> None:  # pragma: no cover - no-op for test
            return None

        def fetch_drive_folder_id(self, userid: str) -> str:  # pragma: no cover - no-op for test
            return ""

        def save_drive_folder_id(self, userid: str, folder_id: str) -> None:  # pragma: no cover
            return None

    dummy_manager = type(
        "DummyManager",
        (),
        {
            "get_user_credentials": lambda self, userid: None,
            "generate_authorization_url": lambda self, state: ("https://example.com/auth", state),
        },
    )()

    monkeypatch.setattr("chatbot.agent.character.UserRepository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.character.GoogleDriveOAuthManager", lambda repo: dummy_manager)

    state = {"userid": "user", "session_id": "session", "messages": [], "awaiting_folder_id": False}

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == "__end__"
    message = result.update["messages"][0]
    assert isinstance(message, AIMessage)
    assert "https://example.com/auth" in message.content
    assert result.update["awaiting_folder_id"] is False


def test_ensure_google_settings_node_triggers_interrupt(monkeypatch):
    """フォルダIDが未設定の場合にinterruptを発生させて待ち状態に設定することを検証"""

    class DummyUserRepository:
        def ensure_user(self, userid: str) -> None:  # pragma: no cover - no-op for test
            return None

        def fetch_drive_folder_id(self, userid: str) -> str:  # pragma: no cover
            return ""

        def save_drive_folder_id(self, userid: str, folder_id: str) -> None:  # pragma: no cover
            return None

    dummy_manager = type(
        "DummyManager",
        (),
        {
            "get_user_credentials": lambda self, userid: object(),
            "generate_authorization_url": lambda self, state: ("https://example.com/auth", state),
        },
    )()

    interrupt_called = []

    def mock_interrupt(payload):
        interrupt_called.append(payload)

    monkeypatch.setattr("chatbot.agent.character.UserRepository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.character.GoogleDriveOAuthManager", lambda repo: dummy_manager)
    monkeypatch.setattr("chatbot.agent.character.interrupt", mock_interrupt)

    state = {"userid": "user", "session_id": "session", "messages": [], "awaiting_folder_id": False}

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == "__end__"
    assert result.update["awaiting_folder_id"] is True
    assert len(interrupt_called) == 1
    assert interrupt_called[0]["type"] == "missing_drive_folder_id"


def test_ensure_google_settings_node_registers_folder_id(monkeypatch):
    """フォルダID入力待ち状態でユーザーがフォルダIDを送信した場合に登録するフローを検証"""

    saved_folder_ids: list[str] = []

    class DummyUserRepository:
        def ensure_user(self, userid: str) -> None:  # pragma: no cover - no-op for test
            return None

        def fetch_drive_folder_id(self, userid: str) -> str:  # pragma: no cover
            return ""

        def save_drive_folder_id(self, userid: str, folder_id: str) -> None:
            saved_folder_ids.append(folder_id)

    dummy_manager = type(
        "DummyManager",
        (),
        {
            "get_user_credentials": lambda self, userid: object(),
            "generate_authorization_url": lambda self, state: ("https://example.com/auth", state),
        },
    )()

    monkeypatch.setattr("chatbot.agent.character.UserRepository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.character.GoogleDriveOAuthManager", lambda repo: dummy_manager)

    # awaiting_folder_id=True の状態でフォルダIDを含むメッセージを送信
    state = {
        "userid": "user",
        "session_id": "session",
        "messages": [{"type": "human", "content": "https://drive.google.com/drive/folders/test-folder-id"}],
        "awaiting_folder_id": True,
    }

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == "get_user_profile"
    message = result.update["messages"][0]
    assert isinstance(message, AIMessage)
    assert "フォルダIDを登録" in message.content
    assert saved_folder_ids == ["test-folder-id"]
    assert result.update["awaiting_folder_id"] is False


def test_ensure_google_settings_node_fails_to_extract_folder_id(monkeypatch):
    """フォルダID入力待ち状態でユーザーが無効な入力を送信した場合を検証"""

    class DummyUserRepository:
        def ensure_user(self, userid: str) -> None:  # pragma: no cover - no-op for test
            return None

        def fetch_drive_folder_id(self, userid: str) -> str:  # pragma: no cover
            return ""

        def save_drive_folder_id(self, userid: str, folder_id: str) -> None:  # pragma: no cover
            return None

    dummy_manager = type(
        "DummyManager",
        (),
        {
            "get_user_credentials": lambda self, userid: object(),
            "generate_authorization_url": lambda self, state: ("https://example.com/auth", state),
        },
    )()

    monkeypatch.setattr("chatbot.agent.character.UserRepository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.character.GoogleDriveOAuthManager", lambda repo: dummy_manager)

    # awaiting_folder_id=True の状態で無効な入力を送信
    state = {
        "userid": "user",
        "session_id": "session",
        "messages": [{"type": "human", "content": "this is not a folder id"}],
        "awaiting_folder_id": True,
    }

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == "__end__"
    message = result.update["messages"][0]
    assert isinstance(message, AIMessage)
    assert "フォルダIDを読み取れなかった" in message.content
    # 待ち状態が継続されることを確認
    assert result.update["awaiting_folder_id"] is True


def test_ensure_google_settings_node_with_existing_folder_id(monkeypatch):
    """フォルダIDが既に登録されている場合の正常系を検証"""

    class DummyUserRepository:
        def ensure_user(self, userid: str) -> None:  # pragma: no cover - no-op for test
            return None

        def fetch_drive_folder_id(self, userid: str) -> str:  # pragma: no cover
            return "existing-folder-id"

        def save_drive_folder_id(self, userid: str, folder_id: str) -> None:  # pragma: no cover
            return None

    dummy_manager = type(
        "DummyManager",
        (),
        {
            "get_user_credentials": lambda self, userid: object(),
            "generate_authorization_url": lambda self, state: ("https://example.com/auth", state),
        },
    )()

    monkeypatch.setattr("chatbot.agent.character.UserRepository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.character.GoogleDriveOAuthManager", lambda repo: dummy_manager)

    state = {"userid": "user", "session_id": "session", "messages": [], "awaiting_folder_id": False}

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == "get_user_profile"
    assert result.update["awaiting_folder_id"] is False
