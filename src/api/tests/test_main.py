import asyncio
import os
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from chatbot.agent import ChatbotAgent, ensure_google_settings_node
from chatbot.main import app

client = TestClient(app)
TEST_USER_ID = "test-user"


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

    with patch("chatbot.agent.get_user_profile", return_value={"profile": "", "digest": ""}):
        # OAuth設定がないテスト環境では ensure_google_settings_node をスキップ
        with patch("chatbot.agent.ensure_google_settings_node", return_value=Command(goto="get_user_profile")):
            agent_graph = ChatbotAgent(checkpointer=MemorySaver())
        messages = [{"type": "human", "content": "こんにちは"}]

        response = asyncio.run(
            agent_graph.ainvoke(messages=messages, userid=TEST_USER_ID, session_id=generate_test_session_id())
        )

    assert "messages" in response
    assert len(response["messages"][-1].content) > 0


def test_chatbot_agent_web_search_response():
    """
    ChatbotAgentがWeb検索を利用できるかのテスト
    - 昨日の日付を含む質問を投げ、Web検索の可否をYes/Noで答えさせる
    - レスポンスがYes（大文字・小文字を問わず）を含むことを確認
    """
    require_openai_api_key()

    with patch("chatbot.agent.get_user_profile", return_value={"profile": "", "digest": ""}):
        # OAuth設定がないテスト環境では ensure_google_settings_node をスキップ
        with patch("chatbot.agent.ensure_google_settings_node", return_value=Command(goto="get_user_profile")):
            agent_graph = ChatbotAgent(checkpointer=MemorySaver())
        yesterday = date.today() - timedelta(days=1)
        messages = [
            {
                "type": "human",
                "content": (f"あなたは{yesterday:%Y-%m-%d}の情報についてweb検索できますか。YesかNoで教えて"),
            }
        ]

        response = asyncio.run(
            agent_graph.ainvoke(messages=messages, userid=TEST_USER_ID, session_id=generate_test_session_id())
        )

    assert "messages" in response
    assert "yes" in response["messages"][-1].content.lower()


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

    import chatbot.agent

    with patch("chatbot.agent.get_user_profile", return_value={"profile": "", "digest": ""}):
        # OAuth設定がないテスト環境では ensure_google_settings_node をスキップ
        with patch("chatbot.agent.ensure_google_settings_node", return_value=Command(goto="get_user_profile")):
            # get_mcp_toolsを空のリストを返すようにモック
            with patch.object(chatbot.agent, "get_mcp_tools", new_callable=AsyncMock) as mock_get_mcp_tools:
                mock_get_mcp_tools.return_value = []

                # routerをモックしてspotify_agentに直接ルーティング
                with patch.object(chatbot.agent, "router_node") as mock_router:
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

    with patch("chatbot.agent.get_mcp_tools", new_callable=AsyncMock) as mock_get_mcp_tools:
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

    monkeypatch.setattr("chatbot.agent.UserRepository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.GoogleDriveOAuthManager", lambda repo: dummy_manager)

    state = {"userid": "user", "session_id": "session", "messages": []}

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == "__end__"
    message = result.update["messages"][0]
    assert isinstance(message, AIMessage)
    assert "https://example.com/auth" in message.content


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

    monkeypatch.setattr("chatbot.agent.UserRepository", lambda: DummyUserRepository())
    monkeypatch.setattr("chatbot.agent.GoogleDriveOAuthManager", lambda repo: dummy_manager)
    monkeypatch.setattr(
        "chatbot.agent.interrupt",
        lambda payload: "https://drive.google.com/drive/folders/test-folder-id",
    )

    state = {"userid": "user", "session_id": "session", "messages": []}

    result = ensure_google_settings_node(state)

    assert isinstance(result, Command)
    assert result.goto == "get_user_profile"
    message = result.update["messages"][0]
    assert isinstance(message, AIMessage)
    assert "フォルダIDを登録" in message.content
    assert saved_folder_ids == ["test-folder-id"]


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

    with patch("chatbot.agent.diary_search_tool", dummy_diary_tool):
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
