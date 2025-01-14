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
    token = websocket.query_params.get("token")
    if token is None:
        await websocket.close(code=4001, reason="Authentication required")
        raise HTTPException(status_code=401, detail="Authentication required")

    if token != VALID_TOKEN:
        await websocket.close(code=4001, reason="Invalid authentication token")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    # 認証成功のログを出力
    logger.info("Authentication successful for WebSocket connection")
    return True
