import asyncio
import json
from typing import List

from chatbot.utils.config import create_logger
from chatbot.utils.sentiment import tag_sentiments_stream
from fastapi import WebSocket

logger = create_logger(__name__)


class ConnectionManager:
    def __init__(self, agent=None, cosmos_repository=None):
        self.active_connections: List[WebSocket] = []
        self.agent = agent
        self.cosmos_repository = cosmos_repository

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None):
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    @staticmethod
    def _split_text(text: str, max_length: int = 50) -> List[str]:
        """テキストを適切な長さに分割する

        Args:
            text (str): 分割する元のテキスト
            max_length (int, optional): 1メッセージの最大文字数. Defaults to 50.

        Returns:
            List[str]: 分割されたメッセージのリスト
        """
        lines = text.split("\n")
        result = []

        for line in lines:
            if not line:
                continue

            sentences = line.split("。")
            for sentence in sentences:
                if not sentence:
                    continue

                if len(sentence) > max_length:
                    parts = sentence.split("、")
                    result.extend([f"{p}、" for p in parts[:-1]] + [parts[-1]])
                else:
                    result.append(sentence)

        return [f"{msg}。" if i < len(result) - 1 else msg for i, msg in enumerate(result)]

    async def send_message(self, websocket: WebSocket, message: str, role: str, type: str = "", emotion: str = "neutral"):
        """単一のWebSocketメッセージを送信"""
        if not websocket:
            logger.error("Can't send message, WebSocket connection is closed.")
            return
        elif type == "" and message == "":
            logger.error("Can't send message, message is empty.")
            return

        role = "assistant" if role == "message" else role
        json_data = json.dumps(
            {"role": role, "text": message, "emotion": emotion, "type": type},
            ensure_ascii=False,
        )
        await websocket.send_text(json_data)
        await asyncio.sleep(0.01)

    async def process_and_send_messages(self, text: str, websocket: WebSocket, type: str):
        """メッセージを処理して送信"""
        messages = self._split_text(text)
        messages = [msg for msg in messages if msg.strip()]

        await self.send_message(websocket, "", "assistant", "start")

        async for message, sentiment in tag_sentiments_stream(messages):
            logger.info(f"[Websocket]Assistant: {sentiment} >> {message}")
            await self.send_message(websocket, message, "assistant", type, sentiment)

        await self.send_message(websocket, "", "assistant", "end")
