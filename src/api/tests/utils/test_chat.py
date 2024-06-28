from unittest.mock import patch

from dotenv import load_dotenv
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage

from .utils.chat import GenerateChatResponseChain

# .envファイルを読み込む
load_dotenv()


@patch(".utils.chat.fetch_recent_chat_messages")
def test_invoke(mock_fetch_recent_chat_messages) -> None:
    # fetch_recent_chat_messagesの戻り値をモック化
    mock_fetch_recent_chat_messages.return_value = [
        ("human", "こんにちは"),
        ("ai", "こんにちは！元気ですか？"),
    ]
    response = """こんにちは！ 😊

お元気ですか？何かお手伝いできることはありますか？
"""

    responses: list[BaseMessage] = [AIMessage(content=response)]
    llm = FakeMessagesListChatModel(responses=responses)
    chain = GenerateChatResponseChain(llm=llm)
    actual = chain.invoke("こんにちは")

    expected = """こんにちは！ 😊

お元気ですか？何かお手伝いできることはありますか？
"""
    assert actual == expected
