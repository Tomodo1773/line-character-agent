import logging
import os


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
