import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from chatbot.agent import ChatbotAgent
from chatbot.main import _get_effective_userid, extract_agent_text, root

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
    result = asyncio.run(root())
    assert result == {"message": "The server is up and running."}


def test_chatbot_agent_response():
    """
    ChatbotAgentのレスポンステスト
    - エージェントが適切なレスポンスを返すことを確認
    - レスポンスのmessages内、最新のcontentが空でないことを確認
    """
    require_openai_api_key()

    with patch("chatbot.agent.character_graph.nodes.get_user_profile", return_value=""):
        with patch("chatbot.agent.character_graph.nodes.get_user_digest", return_value=""):
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
    from langchain_core.messages import HumanMessage
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
    from langchain_core.messages import HumanMessage
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

    mock_user_repository = MagicMock()

    config = {"configurable": {"user_repository": mock_user_repository}}

    with (
        patch("chatbot.agent.character_graph.nodes.diary_search_tool", dummy_diary_tool),
        patch("chatbot.agent.character_graph.nodes._create_drive_handler", return_value=None),
    ):
        initial_state = {
            "messages": [HumanMessage(content="こんにちは")],
            "userid": TEST_USER_ID,
            "profile": "",
            "digest": "",
        }

        result = asyncio.run(diary_agent_node(initial_state, config))

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

    # app.state をモック
    app.state.users_container = MagicMock()

    # DI パターン用のモック設定: create_user_repository をモック
    # LOCAL_USER_ID を含まない環境で実行
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LOCAL_USER_ID", None)
        with patch("chatbot.main.create_user_repository", return_value=mock_user_repo):
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


class TestHandleAudioAsyncPreChecks:
    """handle_audio_async の OAuth/フォルダID 事前チェックのテスト"""

    def _create_audio_event(self):
        from unittest.mock import Mock

        event = Mock()
        event.message.id = "audio-msg-123"
        event.source.user_id = TEST_USER_ID
        event.reply_token = "test-reply-token"
        return event

    def _run_with_mocks(self, mock_user_repo):
        """共通のモック設定で handle_audio_async を実行し、LineMessenger のモックを返す"""
        from unittest.mock import MagicMock, patch

        from chatbot.database.models import SessionMetadata
        from chatbot.main import app, handle_audio_async

        event = self._create_audio_event()
        mock_user_repo.ensure_session.return_value = SessionMetadata(session_id="test-session", last_accessed=MagicMock())
        app.state.users_container = MagicMock()
        app.state.checkpointer = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOCAL_USER_ID", None)
            with patch("chatbot.main.create_user_repository", return_value=mock_user_repo):
                with patch("chatbot.main.LineMessenger") as mock_messenger_class:
                    mock_messenger = MagicMock()
                    mock_messenger_class.return_value = mock_messenger

                    asyncio.run(handle_audio_async(event))

                    return mock_messenger

    def test_oauth_not_configured(self):
        """OAuth未設定の場合、認証URLを含むメッセージが返される"""
        from unittest.mock import MagicMock, patch

        mock_user_repo = MagicMock()
        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = None
        mock_oauth_manager.generate_authorization_url.return_value = ("https://example.com/auth", TEST_USER_ID)

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            mock_messenger = self._run_with_mocks(mock_user_repo)

        mock_messenger.reply_message.assert_called_once()
        messages = mock_messenger.reply_message.call_args[0][0]
        assert len(messages) == 2
        assert "Google Drive へのアクセス許可がまだ設定されていない" in messages[0].text
        assert messages[1].text == "https://example.com/auth"

    def test_oauth_configured_but_folder_missing(self):
        """OAuth設定済みだがフォルダID未設定の場合、フォルダID入力を促すメッセージが返される"""
        from unittest.mock import MagicMock, patch

        mock_user_repo = MagicMock()
        mock_user_repo.fetch_drive_folder_id.return_value = None

        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = MagicMock()  # credentials あり

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            mock_messenger = self._run_with_mocks(mock_user_repo)

        mock_messenger.reply_message.assert_called_once()
        reply_text = mock_messenger.reply_message.call_args[0][0][0].text
        assert "日記フォルダのID" in reply_text

    def test_oauth_and_folder_configured(self):
        """OAuth・フォルダID 両方設定済みの場合、ワークフローが呼び出される"""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_user_repo = MagicMock()
        mock_user_repo.fetch_drive_folder_id.return_value = "test-folder-id"

        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = MagicMock()

        mock_drive_handler = MagicMock()

        mock_workflow = MagicMock()
        mock_workflow.ainvoke = AsyncMock(
            return_value={"diary_text": "今日はテストした", "messages": [], "saved_filename": "2026-03-28.md"}
        )

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            with patch("chatbot.main.GoogleDriveHandler", return_value=mock_drive_handler):
                with patch("chatbot.main.get_diary_workflow", return_value=mock_workflow):
                    mock_messenger = self._run_with_mocks(mock_user_repo)

        # ワークフローが呼び出されたことを確認
        mock_workflow.ainvoke.assert_called_once()
        # drive_handler が config に含まれていることを確認
        invoke_config = mock_workflow.ainvoke.call_args[0][1]
        assert invoke_config["configurable"]["drive_handler"] is not None
        # state に drive_handler が含まれていないことを確認
        invoke_state = mock_workflow.ainvoke.call_args[0][0]
        assert "drive_handler" not in invoke_state
        # reply_message が呼ばれたことを確認（ワークフロー結果の返信）
        mock_messenger.reply_message.assert_called_once()


class TestHandleTextAsyncPreChecks:
    """handle_text_async の OAuth/フォルダID 事前チェックのテスト"""

    def _create_text_event(self, text="こんにちは"):
        from unittest.mock import Mock

        event = Mock()
        event.message.text = text
        event.source.user_id = TEST_USER_ID
        event.reply_token = "test-reply-token"
        return event

    def _run_with_mocks(self, mock_user_repo, text="こんにちは"):
        from unittest.mock import MagicMock, patch

        from chatbot.main import app, handle_text_async

        event = self._create_text_event(text)
        app.state.users_container = MagicMock()
        app.state.checkpointer = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOCAL_USER_ID", None)
            with patch("chatbot.main.create_user_repository", return_value=mock_user_repo):
                with patch("chatbot.main.LineMessenger") as mock_messenger_class:
                    mock_messenger = MagicMock()
                    mock_messenger_class.return_value = mock_messenger

                    asyncio.run(handle_text_async(event))

                    return mock_messenger

    def test_oauth_not_configured(self):
        """OAuth未設定の場合、認証URLを含むメッセージが返される"""
        from unittest.mock import MagicMock, patch

        mock_user_repo = MagicMock()
        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = None
        mock_oauth_manager.generate_authorization_url.return_value = ("https://example.com/auth", TEST_USER_ID)

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            mock_messenger = self._run_with_mocks(mock_user_repo)

        mock_messenger.reply_message.assert_called_once()
        messages = mock_messenger.reply_message.call_args[0][0]
        assert len(messages) == 2
        assert "Google Drive へのアクセス許可がまだ設定されていない" in messages[0].text
        assert messages[1].text == "https://example.com/auth"

    def test_folder_missing_with_unrelated_text(self):
        """フォルダID未設定かつ通常テキストの場合、入力を促すメッセージが返される"""
        from unittest.mock import MagicMock, patch

        mock_user_repo = MagicMock()
        mock_user_repo.fetch_drive_folder_id.return_value = None

        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = MagicMock()

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            mock_messenger = self._run_with_mocks(mock_user_repo, text="こんにちは")

        mock_messenger.reply_message.assert_called_once()
        reply_text = mock_messenger.reply_message.call_args[0][0][0].text
        assert "日記フォルダのID" in reply_text

    def test_folder_missing_with_drive_url(self):
        """フォルダID未設定かつDrive URLが送られた場合、フォルダIDが登録される"""
        from unittest.mock import MagicMock, patch

        mock_user_repo = MagicMock()
        mock_user_repo.fetch_drive_folder_id.return_value = None

        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = MagicMock()

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            mock_messenger = self._run_with_mocks(
                mock_user_repo, text="https://drive.google.com/drive/folders/abc123_test-folder-id"
            )

        mock_user_repo.save_drive_folder_id.assert_called_once_with(TEST_USER_ID, "abc123_test-folder-id")
        reply_text = mock_messenger.reply_message.call_args[0][0][0].text
        assert "フォルダIDを設定したよ" in reply_text
