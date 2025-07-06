import asyncio
import os

from fastapi.testclient import TestClient

from chatbot.agent import ChatbotAgent
from chatbot.main import app

client = TestClient(app)


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
    agent_graph = ChatbotAgent()
    userid = os.environ.get("LINE_USER_ID")
    if not userid:
        raise ValueError("LINE_USER_ID environment variable is not set")

    messages = [{"type": "human", "content": "こんにちは"}]

    response = asyncio.run(agent_graph.ainvoke(messages=messages, userid=userid))

    assert "messages" in response
    assert len(response["messages"][-1].content) > 0


def test_chatbot_agent_websearch_invocation():
    """
    ChatbotAgentのwebsearch呼び出しテスト
    - エージェントが適切にwebsearchを呼び出すことを確認
    - レスポンスのdocuments内にweb_contentsが含まれていることを確認
    """
    agent_graph = ChatbotAgent()
    userid = os.environ.get("LINE_USER_ID")
    if not userid:
        raise ValueError("LINE_USER_ID environment variable is not set")

    messages = [{"type": "human", "content": "今のセリーグの順位は？"}]

    response = asyncio.run(agent_graph.ainvoke(messages=messages, userid=userid))

    assert "messages" in response


def test_diary_transcription():
    """
    DiaryTranscriptionクラスのテスト
    - sample.mp3を読み込んで文字起こしができることを確認
    - 返り値が文字列型であることを確認
    - 返り値に「ランニング」が含まれていることを確認
    """
    from chatbot.utils.transcript import DiaryTranscription

    # サンプル音声ファイルを読み込む
    with open("src/api/tests/sample.m4a", "rb") as f:
        audio_content = f.read()

    # DiaryTranscriptionクラスのインスタンスを作成
    transcriber = DiaryTranscription()

    # 文字起こしを実行
    result = transcriber.invoke(audio_content)

    # 結果の検証
    assert isinstance(result, str)
    assert len(result) > 0
    assert "ランニング" in result
