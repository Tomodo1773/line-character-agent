from dotenv import load_dotenv

from chatbot.utils.config import create_logger, get_env_variable

load_dotenv()

logger = create_logger(__name__)


def verify_api_key(api_key: str) -> bool:
    """APIキーを検証する

    Args:
        api_key (str): 検証するAPIキー

    Returns:
        bool: 検証結果（Trueなら有効）
    """
    valid_api_key = get_env_variable("OPENAI_COMPATIBLE_API_KEY")
    return api_key == valid_api_key
