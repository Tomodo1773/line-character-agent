from typing import List
from fastapi import WebSocket
from .handlers import send_websocket_message

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None):
        """WebSocket接続を確立

        Args:
            websocket (WebSocket): WebSocket接続
            subprotocol (str | None): 使用するサブプロトコル
        """
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def send_message_to_all(self, message: str, type: str):
        closed_connections = []
        for websocket in self.active_connections:
            try:
                await send_websocket_message(websocket, "", "assistant", "start")
                await send_websocket_message(websocket, message, type)
                await send_websocket_message(websocket, "", "assistant", "end")
            except RuntimeError:
                closed_connections.append(websocket)

        for closed_websocket in closed_connections:
            self.disconnect(closed_websocket)
