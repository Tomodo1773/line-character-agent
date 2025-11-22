import json
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from chatbot.utils.config import create_logger, get_env_variable

logger = create_logger(__name__)


def _get_fernet() -> Fernet:
    """環境変数から取得した鍵でFernetインスタンスを返す"""
    key = get_env_variable("GOOGLE_TOKEN_ENC_KEY")
    return Fernet(key.encode("utf-8"))


def encrypt_dict(data: Dict[str, Any]) -> str:
    """辞書をJSONにしてFernetで暗号化し、文字列を返す"""
    fernet = _get_fernet()
    payload = json.dumps(data).encode("utf-8")
    return fernet.encrypt(payload).decode("utf-8")


def decrypt_dict(token: str) -> Dict[str, Any]:
    """Fernetで復号して辞書を返す。失敗時は空dictを返す。"""
    if not token:
        return {}

    fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(token.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError) as error:
        logger.error("Failed to decrypt google token: %s", error)
        return {}
