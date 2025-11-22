import logging
import os
from typing import List, Tuple

# 必要な環境変数のリスト
REQUIRED_ENV_VARS = [
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_CHANNEL_SECRET",
    "OPENAI_API_KEY",
    "LANGSMITH_API_KEY",
    "COSMOS_DB_ACCOUNT_URL",
    "COSMOS_DB_ACCOUNT_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "DRIVE_FOLDER_ID",
    "MCP_FUNCTION_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
]


def create_logger(name: str) -> logging.Logger:
    """
    ロガーを作成するファクトリー関数

    Args:
        name (str): ロガーの名前（通常は__name__を使用）

    Returns:
        logging.Logger: 設定済みのロガーインスタンス
    """
    # ルートロガーの伝搬を無効化
    logger = logging.getLogger(name)
    logger.propagate = False

    if not logger.handlers:  # 既にハンドラーが設定されている場合は追加しない
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        handler.encoding = "utf-8"
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = create_logger(__name__)


def get_env_variable(key: str) -> str:
    """必須の環境変数を取得するヘルパー関数"""

    value = os.getenv(key)
    if not value:
        logger.error("環境変数 %s が設定されていません", key)
        raise EnvironmentError(f"環境変数 {key} が設定されていません")
    return value


def check_environment_variables() -> Tuple[bool, List[str]]:
    """
    必要な環境変数が設定されているかチェックする関数

    Returns:
        Tuple[bool, List[str]]:
            - bool: すべての環境変数が設定されている場合はTrue、そうでない場合はFalse
            - List[str]: 未設定の環境変数のリスト
    """
    missing_vars = []

    for var in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            missing_vars.append(var)
            logger.error(f"環境変数 {var} が設定されていません")

    return len(missing_vars) == 0, missing_vars
