import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from chatbot.agent import ChatbotAgent
from chatbot.main import _get_effective_userid, root

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

    async def run():
        with patch("chatbot.agent.tools.get_mcp_tools", new_callable=AsyncMock, return_value=[]):
            agent = await ChatbotAgent.create(checkpointer=MemorySaver())
            messages = [{"type": "human", "content": "こんにちは"}]
            return await agent.ainvoke(messages=messages, userid=TEST_USER_ID, session_id=generate_test_session_id())

    response = asyncio.run(run())

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


def test_reset_session():
    """
    UserRepository.reset_session のテスト
    - reset_sessionを呼び出すと新しいセッションIDが生成されることを確認
    - 同じユーザーで2回reset_sessionを呼ぶと異なるセッションIDが返されることを確認
    """

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
    from unittest.mock import Mock, patch

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
    app.state.oauth_states_container = MagicMock()

    # DI パターン用のモック設定: create_user_repository / create_oauth_state_repository をモック
    # LOCAL_USER_ID を含まない環境で実行
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LOCAL_USER_ID", None)
        with patch("chatbot.main.create_user_repository", return_value=mock_user_repo):
            with patch("chatbot.main.create_oauth_state_repository", return_value=MagicMock()):
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

    def _run_with_mocks(self, mock_user_repo, mock_oauth_state_repo=None):
        """共通のモック設定で handle_audio_async を実行し、LineMessenger のモックを返す"""
        from unittest.mock import patch

        from chatbot.database.models import SessionMetadata
        from chatbot.main import app, handle_audio_async

        event = self._create_audio_event()
        mock_user_repo.ensure_session.return_value = SessionMetadata(session_id="test-session", last_accessed=MagicMock())
        app.state.users_container = MagicMock()
        app.state.oauth_states_container = MagicMock()
        app.state.checkpointer = MagicMock()

        oauth_state_repo = mock_oauth_state_repo if mock_oauth_state_repo is not None else MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOCAL_USER_ID", None)
            with patch("chatbot.main.create_user_repository", return_value=mock_user_repo):
                with patch("chatbot.main.create_oauth_state_repository", return_value=oauth_state_repo):
                    with patch("chatbot.main.LineMessenger") as mock_messenger_class:
                        mock_messenger = MagicMock()
                        mock_messenger_class.return_value = mock_messenger

                        asyncio.run(handle_audio_async(event))

                        return mock_messenger

    def test_oauth_not_configured(self):
        """OAuth未設定の場合、認証URLを含むメッセージが返され、oauth_states に保存される"""
        from unittest.mock import patch

        mock_user_repo = MagicMock()
        mock_oauth_state_repo = MagicMock()
        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = None
        mock_oauth_manager.generate_authorization_url.return_value = ("https://example.com/auth", "test-code-verifier")

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            mock_messenger = self._run_with_mocks(mock_user_repo, mock_oauth_state_repo)

        mock_messenger.reply_message.assert_called_once()
        messages = mock_messenger.reply_message.call_args[0][0]
        assert len(messages) == 2
        assert "Google Drive へのアクセス許可がまだ設定されていない" in messages[0].text
        assert messages[1].text == "https://example.com/auth"
        # state は乱数なので値そのものはアサートしないが、userid と code_verifier が正しく渡ることを検証
        mock_oauth_state_repo.save_state.assert_called_once()
        saved_state, saved_userid, saved_verifier = mock_oauth_state_repo.save_state.call_args[0]
        assert isinstance(saved_state, str) and len(saved_state) >= 32
        assert saved_userid == TEST_USER_ID
        assert saved_verifier == "test-code-verifier"
        # 認可 URL の生成時に state が渡っていることを確認
        mock_oauth_manager.generate_authorization_url.assert_called_once_with(saved_state)

    def test_oauth_configured_but_folder_missing(self):
        """OAuth設定済みだがフォルダID未設定の場合、フォルダID入力を促すメッセージが返される"""
        from unittest.mock import patch

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
        from unittest.mock import AsyncMock, patch

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

    def _run_with_mocks(self, mock_user_repo, text="こんにちは", mock_oauth_state_repo=None):
        from unittest.mock import patch

        from chatbot.main import app, handle_text_async

        event = self._create_text_event(text)
        app.state.users_container = MagicMock()
        app.state.oauth_states_container = MagicMock()
        app.state.checkpointer = MagicMock()

        oauth_state_repo = mock_oauth_state_repo if mock_oauth_state_repo is not None else MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOCAL_USER_ID", None)
            with patch("chatbot.main.create_user_repository", return_value=mock_user_repo):
                with patch("chatbot.main.create_oauth_state_repository", return_value=oauth_state_repo):
                    with patch("chatbot.main.LineMessenger") as mock_messenger_class:
                        mock_messenger = MagicMock()
                        mock_messenger_class.return_value = mock_messenger

                        asyncio.run(handle_text_async(event))

                        return mock_messenger

    def test_oauth_not_configured(self):
        """OAuth未設定の場合、認証URLを含むメッセージが返され、oauth_states に保存される"""
        from unittest.mock import patch

        mock_user_repo = MagicMock()
        mock_oauth_state_repo = MagicMock()
        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = None
        mock_oauth_manager.generate_authorization_url.return_value = ("https://example.com/auth", "test-code-verifier")

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            mock_messenger = self._run_with_mocks(mock_user_repo, mock_oauth_state_repo=mock_oauth_state_repo)

        mock_messenger.reply_message.assert_called_once()
        messages = mock_messenger.reply_message.call_args[0][0]
        assert len(messages) == 2
        assert "Google Drive へのアクセス許可がまだ設定されていない" in messages[0].text
        assert messages[1].text == "https://example.com/auth"
        # state は乱数なので値そのものはアサートしないが、userid と code_verifier が正しく渡ることを検証
        mock_oauth_state_repo.save_state.assert_called_once()
        saved_state, saved_userid, saved_verifier = mock_oauth_state_repo.save_state.call_args[0]
        assert isinstance(saved_state, str) and len(saved_state) >= 32
        assert saved_userid == TEST_USER_ID
        assert saved_verifier == "test-code-verifier"

    def test_folder_missing_with_unrelated_text(self):
        """フォルダID未設定かつ通常テキストの場合、入力を促すメッセージが返される"""
        from unittest.mock import patch

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
        from unittest.mock import patch

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


class TestOAuthCallbackVerifierSymmetry:
    """`_check_oauth` が保存した (state, code_verifier) を `google_drive_oauth_callback` が
    同じ値で `exchange_code_for_credentials` に渡すこと（PKCE の対称性）を保証する。

    google-auth-oauthlib の autogenerate_code_verifier デフォルト変更のような、
    authorize / token 間で verifier が食い違う回帰を検出する目的のテスト。"""

    def test_state_and_verifier_saved_in_check_oauth_are_used_in_callback(self):
        from unittest.mock import patch

        from chatbot.main import _check_oauth, google_drive_oauth_callback

        mock_user_repo = MagicMock()

        # oauth_states コンテナの擬似実装: save_state で保存 → consume_state で取り出し即削除
        stored_states: dict[str, dict[str, str]] = {}
        mock_oauth_state_repo = MagicMock()

        def fake_save_state(state, userid, code_verifier):
            stored_states[state] = {"userid": userid, "code_verifier": code_verifier}

        def fake_consume_state(state):
            return stored_states.pop(state, None)

        mock_oauth_state_repo.save_state.side_effect = fake_save_state
        mock_oauth_state_repo.consume_state.side_effect = fake_consume_state

        generated_verifier = "pkce-verifier-abc123"
        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = None
        mock_oauth_manager.generate_authorization_url.return_value = (
            "https://example.com/auth",
            generated_verifier,
        )
        mock_oauth_manager.exchange_code_for_credentials.return_value = MagicMock()

        # 1. `_check_oauth` で認可URL生成 → state と verifier を保存
        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            _check_oauth(mock_user_repo, mock_oauth_state_repo, TEST_USER_ID, MagicMock())

        # 保存された state を取得
        assert len(stored_states) == 1
        saved_state = next(iter(stored_states.keys()))
        assert stored_states[saved_state]["userid"] == TEST_USER_ID
        assert stored_states[saved_state]["code_verifier"] == generated_verifier

        # 2. コールバックで saved_state を渡すと同じ verifier が exchange に渡ることを検証
        with patch("chatbot.main.LineMessenger"):
            asyncio.run(
                google_drive_oauth_callback(
                    code="auth-code-xyz",
                    state=saved_state,
                    oauth_state_repository=mock_oauth_state_repo,
                    oauth_manager=mock_oauth_manager,
                )
            )

        mock_oauth_manager.exchange_code_for_credentials.assert_called_once_with("auth-code-xyz", generated_verifier)
        # ワンタイム消費されていること
        assert stored_states == {}

    def test_callback_with_unknown_state_fails_gracefully(self):
        """未知 / 期限切れの state でコールバックが来た場合、exchange は呼ばれず案内メッセージが返る"""
        from unittest.mock import patch

        from chatbot.main import google_drive_oauth_callback

        mock_oauth_state_repo = MagicMock()
        mock_oauth_state_repo.consume_state.return_value = None

        mock_oauth_manager = MagicMock()

        with patch("chatbot.main.LineMessenger"):
            result = asyncio.run(
                google_drive_oauth_callback(
                    code="auth-code-xyz",
                    state="unknown-state",
                    oauth_state_repository=mock_oauth_state_repo,
                    oauth_manager=mock_oauth_manager,
                )
            )

        mock_oauth_manager.exchange_code_for_credentials.assert_not_called()
        assert "認可リンクの有効期限が切れたか" in result["message"]

    def test_check_oauth_generates_unique_state_each_call(self):
        """`_check_oauth` は呼び出しごとに異なる乱数 state を生成する"""
        from unittest.mock import patch

        from chatbot.main import _check_oauth

        mock_user_repo = MagicMock()
        mock_oauth_state_repo = MagicMock()
        mock_oauth_manager = MagicMock()
        mock_oauth_manager.get_user_credentials.return_value = None
        mock_oauth_manager.generate_authorization_url.return_value = ("https://example.com/auth", "verifier")

        with patch("chatbot.main.GoogleDriveOAuthManager", return_value=mock_oauth_manager):
            _check_oauth(mock_user_repo, mock_oauth_state_repo, TEST_USER_ID, MagicMock())
            _check_oauth(mock_user_repo, mock_oauth_state_repo, TEST_USER_ID, MagicMock())

        assert mock_oauth_state_repo.save_state.call_count == 2
        state_1 = mock_oauth_state_repo.save_state.call_args_list[0][0][0]
        state_2 = mock_oauth_state_repo.save_state.call_args_list[1][0][0]
        assert state_1 != state_2
