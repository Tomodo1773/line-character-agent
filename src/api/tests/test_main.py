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

def test_diary_transcription():
    """
    DiaryTranscriptionクラスのテスト
    - sample.mp3を読み込んで文字起こしができることを確認
    - 返り値が文字列型であることを確認
    - 返り値に「ランニング」が含まれていることを確認
    """
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
    from unittest.mock import AsyncMock, patch

    import chatbot.agent

    # get_mcp_toolsを空のリストを返すようにモック
    with patch.object(chatbot.agent, "get_mcp_tools", new_callable=AsyncMock) as mock_get_mcp_tools:
        mock_get_mcp_tools.return_value = []

        # routerをモックしてspotify_agentに直接ルーティング
        with patch.object(chatbot.agent, "router_node") as mock_router:
            from langgraph.types import Command

            mock_router.return_value = Command(goto="spotify_agent")

            agent_graph = ChatbotAgent()
            userid = os.environ.get("LINE_USER_ID")
            if not userid:
                raise ValueError("LINE_USER_ID environment variable is not set")

            # B'zの曲検索をリクエスト
            messages = [{"type": "human", "content": "SpotifyでB'zの曲を検索して"}]

            response = asyncio.run(agent_graph.ainvoke(messages=messages, userid=userid))

            # レスポンスの検証
            assert "messages" in response
            last_message = response["messages"][-1].content
            assert "ごめんね。MCP サーバーに接続できなかったみたい。" in last_message
