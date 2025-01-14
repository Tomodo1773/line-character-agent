import json
import asyncio
import logging
from fastapi import WebSocket
from chatbot.utils.sentiment import sentiment_tagging
from .utils import split_text

logger = logging.getLogger(__name__)

class WebSocketHandler:
    def __init__(self, agent, cosmos_repository):
        self.agent = agent
        self.cosmos_repository = cosmos_repository

    async def process_and_send_messages(self, text: str, websocket: WebSocket, type: str):
        messages = split_text(text)
        messages = [msg for msg in messages if msg.strip()]

        for message in messages:
            sentiment = await sentiment_tagging(message)
            logger.info(f"[Websocket]Assistant: {sentiment} >> {message}")
            await send_websocket_message(websocket, message, "assistant", type, sentiment)

async def send_websocket_message(websocket: WebSocket, message: str, role: str, type: str = "", emotion: str = "neutral"):
    role = "assistant" if role == "message" else role

    if not websocket:
        logger.error("Can't send message, WebSocket connection is closed.")
        return
    elif type == "" and message == "":
        logger.error("Can't send message, message is empty.")
        return

    json_data = json.dumps(
        {"role": role, "text": message, "emotion": emotion, "type": type},
        ensure_ascii=False,
    )
    await websocket.send_text(json_data)
    await asyncio.sleep(0.01)
