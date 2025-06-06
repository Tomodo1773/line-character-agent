import os

from chatbot.utils.config import create_logger
from dotenv import load_dotenv

load_dotenv()

logger = create_logger(__name__)


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
