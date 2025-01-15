import os

from chatbot.utils.config import create_logger
from fastapi import HTTPException, WebSocket

# 固定のトークン
VALID_TOKEN = os.environ.get("JWT_TOKEN", "your-secret-token")

# ログ設定
logger = create_logger(__name__)


async def verify_token_ws(websocket: WebSocket) -> bool:
    """WebSocket接続時のトークン検証

    Args:
        websocket (WebSocket): WebSocket接続

    Returns:
        bool: 認証成功時にTrue

    Raises:
        HTTPException: トークンが無効な場合
    """
    # token = websocket.query_params.get("token")
    protocol = websocket.headers.get("Sec-WebSocket-Protocol")

    if protocol is None:
        await websocket.close(code=4001, reason="Authentication required")
        return False, None

    # 最初のプロトコルを取得
    token = protocol.split(",")[0].strip()

    if token != VALID_TOKEN:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return False, None

    logger.info("Authentication successful for WebSocket connection")
    return True, token
