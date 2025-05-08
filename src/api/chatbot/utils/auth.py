import os
from typing import Tuple

import jwt
from chatbot.database.repositories import UserRepository
from chatbot.utils.config import create_logger
from fastapi import WebSocket
from dotenv import load_dotenv

load_dotenv()

# 環境変数
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key")

# ログ設定
logger = create_logger(__name__)

ALGORITHM = "HS256"


async def verify_token_ws(websocket: WebSocket) -> Tuple[bool, str | None, str | None]:
    """WebSocket接続時のトークン検証とユーザーID取得

    Args:
        websocket (WebSocket): WebSocket接続

    Returns:
        Tuple[bool, str | None, str | None]: (認証成功フラグ, トークン, ユーザーID)

    Raises:
        HTTPException: トークンが無効な場合
    """
    protocol = websocket.headers.get("Sec-WebSocket-Protocol")

    if protocol is None:
        await websocket.close(code=4001, reason="Authentication required")
        return False, None, None

    token = protocol.split(",")[0].strip()

    try:
        # JWTトークンを検証してユーザーIDを取得
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            await websocket.close(code=4001, reason="Invalid token payload")
            return False, None, None

        # CosmosDBでユーザー存在確認
        cosmos = UserRepository()
        result = cosmos.fetch_profile(user_id)

        # 結果の厳密なチェック
        if not isinstance(result, list) or not result or "profile" not in result[0]:
            await websocket.close(code=4001, reason="User not found or invalid profile")
            return False, None, None

        logger.info(f"Authentication successful for WebSocket connection: {user_id}")
        return True, token, user_id

    except jwt.InvalidTokenError:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return False, None, None
    except Exception as e:
        logger.error(f"Database error during authentication: {str(e)}")
        await websocket.close(code=4001, reason="Authentication error")
        return False, None, None


def create_jwt_token(userid: str) -> str:
    """JWTトークンを生成する
    Args:
        userid (str): ユーザーID
        JWT_SECRET_KEY (str): シークレットキー
    Returns:
        str: 生成されたJWTトークン
    """
    payload = {"sub": userid}
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return token


if __name__ == "__main__":
    userid = os.environ.get("LINE_USER_ID")
    print(userid)

    token = create_jwt_token(userid)
    print(f"Generated token: {token}")
