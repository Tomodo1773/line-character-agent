import os

import jwt
from chatbot.utils.config import create_logger
from dotenv import load_dotenv

load_dotenv()

# 環境変数
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key")

# ログ設定
logger = create_logger(__name__)

ALGORITHM = "HS256"




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


def verify_api_key(api_key: str) -> bool:
    """APIキーを検証する

    Args:
        api_key (str): 検証するAPIキー

    Returns:
        bool: 検証結果（Trueなら有効）
    """
    valid_api_key = os.environ.get("OPENAI_COMPATIBLE_API_KEY", "")
    
    if not valid_api_key:
        logger.error("OPENAI_COMPATIBLE_API_KEYが設定されていません")
        return False
    
    return api_key == valid_api_key


if __name__ == "__main__":
    userid = os.environ.get("LINE_USER_ID")
    print(userid)

    token = create_jwt_token(userid)
    print(f"Generated token: {token}")
