from dotenv import load_dotenv
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage

from utils.chat import GenerateChatResponseChain

# .envファイルを読み込む
load_dotenv()

def test_invoke() -> None:
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
