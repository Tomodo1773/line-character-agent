import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from chatbot.agent import ChatbotAgent, ensure_google_settings_node
from chatbot.main import _get_effective_userid, app, extract_agent_text

client = TestClient(app)
TEST_USER_ID = "test-user"


def test_get_effective_userid_without_local_override():
    """
    LOCAL_USER_IDが設定されていない場合、元のuseridが返されることを確認
    """
    original_userid = "line-user-12345"
    # LOCAL_USER_ID を含まない環境で実行
    with patch.dict(os.environ, {}, clear=True):
        result = _get_effective_userid(original_userid)
        assert result == original_userid


def test_get_effective_userid_with_local_override():
    """
    LOCAL_USER_IDが設定されている場合、その値が返されることを確認
    """
    original_userid = "line-user-12345"
    local_userid = "local-dev-user"
    # LOCAL_USER_ID ありの環境で実行
    with patch.dict(os.environ, {"LOCAL_USER_ID": local_userid}):
        result = _get_effective_userid(original_userid)
        assert result == local_userid


def generate_test_session_id() -> str:
    """テストごとにユニークなセッションIDを生成する"""
    return uuid.uuid4().hex


def require_openai_api_key() -> None:
    """OpenAI API キーが未設定の場合はテストをスキップする"""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY が設定されていないためスキップします")


def test_read_root():
    """
    ルートパス（/）へのGETリクエストのテスト
    - ステータスコードが200であることを確認
    - レスポンスが期待通りのJSONフォーマットであることを確認
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "The server is up and running."}


def test_chatbot_agent_response():
    """
    ChatbotAgentのレスポンステスト
    - エージェントが適切なレスポンスを返すことを確認
    - レスポンスのmessages内、最新のcontentが空でないことを確認
    """
    require_openai_api_key()

    with patch("chatbot.agent.character_graph.nodes.get_user_profile", return_value=""):
        with patch("chatbot.agent.character_graph.nodes.get_user_digest", return_value=""):
            # OAuth設定がないテスト環境では ensure_google_settings_node をスキップ
            # グラフビルド時にgraph.pyからインポートされた関数を使用するため、graph.pyのパスをパッチ
            with patch(
                "chatbot.agent.character_graph.graph.ensure_google_settings_node",
                return_value=Command(goto=["get_profile", "get_digest"]),
            ):
                agent_graph = ChatbotAgent(checkpointer=MemorySaver())
                messages = [{"type": "human", "content": "こんにちは"}]

                response = asyncio.run(
                    agent_graph.ainvoke(messages=messages, userid=TEST_USER_ID, session_id=generate_test_session_id())
                )

    assert "messages" in response
    assert len(response["messages"][-1].content) > 0


def test_diary_transcription():
    """
    DiaryTranscriptionクラスのテスト
    - sample.mp3を読み込んで文字起こしができることを確認
    - 返り値が文字列型であることを確認
    - 返り値に「ランニング」が含まれていることを確認
    """
    require_openai_api_key()

    from chatbot.utils.transcript import DiaryTranscription

    # サンプル音声ファイルを読み込む
    with open("tests/sample.m4a", "rb") as f:
        audio_content = f.read()

    # DiaryTranscriptionクラスのインスタンスを作成
    transcriber = DiaryTranscription()

    # 文字起こしを実行
    result = transcriber.invoke(audio_content)

    # 結果の検証
    assert isinstance(result, str)
    assert len(result) > 0
    assert "ランニング" in result


def test_spotify_agent_mcp_fallback():
    """
    MCPサーバー未接続時のSpotifyエージェントフォールバックテスト
    - MCPツールが取得できない状態でSpotifyエージェントにルーティングされた場合
    - フォールバックメッセージが返されることを確認
    - メッセージ内容が「ごめんね。MCP サーバーに接続できなかったみたい。」であることを確認
    """
    require_openai_api_key()

    from chatbot.agent.character_graph import nodes

    with patch("chatbot.agent.character_graph.nodes.get_user_profile", return_value=""):
        with patch("chatbot.agent.character_graph.nodes.get_user_digest", return_value=""):
            # OAuth設定がないテスト環境では ensure_google_settings_node をスキップ
            # グラフビルド時にgraph.pyからインポートされた関数を使用するため、graph.pyのパスをパッチ
            with patch(
                "chatbot.agent.character_graph.graph.ensure_google_settings_node",
                return_value=Command(goto=["get_profile", "get_digest"]),
            ):
                # get_mcp_toolsを空のリストを返すようにモック
                with patch.object(nodes, "get_mcp_tools", new_callable=AsyncMock) as mock_get_mcp_tools:
                    mock_get_mcp_tools.return_value = []

                    # routerをモックしてspotify_agentに直接ルーティング
                    with patch.object(nodes, "router_node") as mock_router:
                        mock_router.return_value = Command(goto="spotify_agent")

                        agent_graph = ChatbotAgent(checkpointer=MemorySaver())
                    # B'zの曲検索をリクエスト
                    messages = [{"type": "human", "content": "SpotifyでB'zの曲を検索して"}]

                    response = asyncio.run(
                        agent_graph.ainvoke(messages=messages, userid=TEST_USER_ID, session_id=generate_test_session_id())
                    )

                    # レスポンスの検証
                    assert "messages" in response
                    last_message = response["messages"][-1].content
                    assert "ごめんね。MCP サーバーに接続できなかったみたい。" in last_message


def test_spotify_agent():
    """
    spotify_agent_node が create_agent を正しいシグネチャで呼び出すことを検証するテスト
    - MCPツールが取得できる状態で正常系の動作を確認
    - 実際の OpenAI API を使用してエージェントが正常に動作することを確認
    - ダミーの MCP ツールを使用（実際の MCP サーバー接続は不要）
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.tools import tool

    from chatbot.agent import spotify_agent_node

    require_openai_api_key()

    @tool
    def dummy_tool(query: str) -> str:
        """A dummy tool for testing."""
        return "dummy response"

    async def fake_get_mcp_tools():
        """MCPツールが取得できる状態をシミュレート"""
        # ダミーツールを返す（実際のツールは使用しない）
        return [dummy_tool]

    with patch("chatbot.agent.character_graph.nodes.get_mcp_tools", new_callable=AsyncMock) as mock_get_mcp_tools:
        mock_get_mcp_tools.side_effect = fake_get_mcp_tools

        # spotify_agent_node を直接呼び出す
        initial_state = {
            "messages": [HumanMessage(content="こんにちは")],
            "userid": TEST_USER_ID,
            "profile": "",
            "digest": "",
        }

        # 正常系：例外が発生せずに完了することを確認
        result = asyncio.run(spotify_agent_node(initial_state))

        # レスポンスの検証
        assert result is not None
        # Command オブジェクトが返されることを確認
        from langgraph.types import Command

        assert isinstance(result, Command)
        assert result.goto == "__end__"
        # update に messages が含まれていることを確認
        assert "messages" in result.update
        # AIMessage が返されていることを確認
        returned_messages = result.update["messages"]
        assert len(returned_messages) > 0
        assert isinstance(returned_messages[0], AIMessage)
        # 応答が空でないことを確認
        assert len(returned_messages[0].content) > 0


def test_ensure_google_settings_node_returns_auth_interrupt(monkeypatch):
    """OAuth設定がない場合にinterruptで認可URLを案内することを検証"""
    captured_payloads: list[dict] = []

    def capture_interrupt(payload):
        captured_payloads.append(payload)
        return "oauth_completed"

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

    # DI パターン用のモック設定: create_user_repository をモック（インポート元をパッチ）
    monkeypatch.setattr("chatbot.dependencies.create_user_repository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.services.google_settings.GoogleDriveOAuthManager", lambda repo: dummy_manager)
    monkeypatch.setattr("chatbot.agent.services.google_settings.interrupt", capture_interrupt)

    state = {"userid": "user", "session_id": "session", "messages": []}

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    # interruptからresumeした後はsuccess_gotoへ遷移
    assert result.goto == ["get_profile", "get_digest"]
    # interruptペイロードを検証
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["type"] == "missing_oauth"
    assert "https://example.com/auth" in captured_payloads[0]["message"]


def test_ensure_google_settings_node_registers_folder_id(monkeypatch):
    """フォルダIDが未設定の場合に入力を促し登録するフローを検証"""
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

    # DI パターン用のモック設定: create_user_repository をモック（インポート元をパッチ）
    monkeypatch.setattr("chatbot.dependencies.create_user_repository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.services.google_settings.GoogleDriveOAuthManager", lambda repo: dummy_manager)
    monkeypatch.setattr(
        "chatbot.agent.services.google_settings.interrupt",
        lambda payload: "https://drive.google.com/drive/folders/test-folder-id",
    )

    state = {"userid": "user", "session_id": "session", "messages": []}

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == ["get_profile", "get_digest"]
    # 確認メッセージは削除され、会話履歴に追加されない
    assert result.update is None
    assert saved_folder_ids == ["test-folder-id"]


def test_extract_agent_text_non_interrupt():
    """__interrupt__ が無い場合に messages[-1].content からテキストを取得できることを検証"""
    response = {"messages": [{"content": "hello"}]}

    text, is_interrupt = extract_agent_text(response)

    assert text == "hello"
    assert is_interrupt is False


def test_extract_agent_text_with_interrupt():
    """__interrupt__ がある場合に interrupt メッセージが優先されることを検証"""

    class DummyInterrupt:
        def __init__(self, value):
            self.value = value

    interrupts = [DummyInterrupt({"message": "need input"})]
    response = {"__interrupt__": interrupts, "messages": [{"content": "ignored"}]}

    text, is_interrupt = extract_agent_text(response)

    assert text == "need input"
    assert is_interrupt is True


def test_diary_agent():
    """
    diary_agent_node が create_agent を正しいシグネチャで呼び出すことを検証するテスト
    - ダミーの diary search tool を使用し、エージェントが正常に動作することを確認
    - 実際の OpenAI API を使用してエージェントが正常に動作することを確認
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.tools import tool
    from langgraph.types import Command

    from chatbot.agent import diary_agent_node

    require_openai_api_key()

    @tool
    def dummy_diary_tool(
        query_text: str,
        top_k: int = 5,
        start_date: str | None = None,
        end_date: str | None = None,
        order: str = "asc",
    ) -> str:
        """A dummy diary search tool for testing."""

        return "dummy diary response"

    with patch("chatbot.agent.character_graph.nodes.diary_search_tool", dummy_diary_tool):
        initial_state = {
            "messages": [HumanMessage(content="こんにちは")],
            "userid": TEST_USER_ID,
            "profile": "",
            "digest": "",
        }

        result = asyncio.run(diary_agent_node(initial_state))

        assert isinstance(result, Command)
        assert result.goto == "__end__"
        assert "messages" in result.update

        returned_messages = result.update["messages"]
        assert len(returned_messages) > 0
        assert isinstance(returned_messages[0], AIMessage)
        assert len(returned_messages[0].content) > 0


def test_reset_session():
    """
    UserRepository.reset_session のテスト
    - reset_sessionを呼び出すと新しいセッションIDが生成されることを確認
    - 同じユーザーで2回reset_sessionを呼ぶと異なるセッションIDが返されることを確認
    """
    from unittest.mock import MagicMock

    from chatbot.database.repositories import UserRepository

    # CosmosCore のモック作成
    mock_core_instance = MagicMock()

    # UserRepositoryのインスタンスを作成（DI 対応）
    user_repository = UserRepository(mock_core_instance)

    # fetch_userをモック化
    user_repository.fetch_user = MagicMock(return_value={"id": TEST_USER_ID, "userid": TEST_USER_ID})

    # 最初のreset_sessionを呼び出し
    session1 = user_repository.reset_session(TEST_USER_ID)

    # セッションIDが生成されていることを確認
    assert session1.session_id is not None
    assert len(session1.session_id) > 0

    # 2回目のreset_sessionを呼び出し
    session2 = user_repository.reset_session(TEST_USER_ID)

    # 異なるセッションIDが生成されていることを確認
    assert session2.session_id != session1.session_id


def test_handle_text_async_with_reset_keyword():
    """
    handle_text_asyncで「閑話休題」キーワードを受け取った時のテスト
    - 「閑話休題」を送信するとセッションがリセットされることを確認
    - 適切なメッセージが返されることを確認
    """
    from unittest.mock import MagicMock, Mock, patch

    from chatbot.database.models import SessionMetadata
    from chatbot.main import app, handle_text_async

    # イベントオブジェクトのモック作成
    event = Mock()
    event.message.text = "閑話休題"
    event.source.user_id = TEST_USER_ID
    event.reply_token = "test-reply-token"

    # UserRepositoryのモック作成（DI 対応）
    mock_user_repo = MagicMock()

    # reset_sessionが呼ばれることを確認するためのモック設定
    new_session_id = "new-session-id"
    mock_user_repo.reset_session.return_value = SessionMetadata(session_id=new_session_id, last_accessed=MagicMock())

    # app.state.cosmos_client をモック
    mock_cosmos_client = MagicMock()
    app.state.cosmos_client = mock_cosmos_client

    # DI パターン用のモック設定: create_user_repository をモック
    with patch("chatbot.dependencies.create_user_repository", return_value=mock_user_repo):
        # LineMessengerのモック作成
        with patch("chatbot.main.LineMessenger") as mock_messenger_class:
            mock_messenger = MagicMock()
            mock_messenger_class.return_value = mock_messenger

            # handle_text_asyncを実行
            asyncio.run(handle_text_async(event))

            # reset_sessionが呼ばれたことを確認
            mock_user_repo.reset_session.assert_called_once_with(TEST_USER_ID)

            # 適切なメッセージが返信されたことを確認
            mock_messenger.reply_message.assert_called_once()
            reply_messages = mock_messenger.reply_message.call_args[0][0]
            assert len(reply_messages) == 1
            assert "会話履歴をリセットしたよ" in reply_messages[0].text
