import asyncio
import os
import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest

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
        agent = await ChatbotAgent.create()
        messages = [{"type": "human", "content": "こんにちは"}]
        return await agent.ainvoke(messages=messages, userid=TEST_USER_ID, session_id=generate_test_session_id())

    response = asyncio.run(run())

    assert "messages" in response
    assert len(response["messages"][-1].content) > 0


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

    # LOCAL_USER_ID を含まない環境で実行
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LOCAL_USER_ID", None)
        with patch("chatbot.main.create_user_repository", return_value=mock_user_repo):
            with patch("chatbot.main.LineMessenger") as mock_messenger_class:
                mock_messenger = MagicMock()
                mock_messenger_class.return_value = mock_messenger

                asyncio.run(handle_text_async(event))

    # reset_sessionが呼ばれたことを確認
    mock_user_repo.reset_session.assert_called_once_with(TEST_USER_ID)

    # 適切なメッセージが返信されたことを確認
    mock_messenger.reply_message.assert_called_once()
    reply_messages = mock_messenger.reply_message.call_args[0][0]
    assert len(reply_messages) == 1
    assert "会話履歴をリセットしたよ" in reply_messages[0].text
