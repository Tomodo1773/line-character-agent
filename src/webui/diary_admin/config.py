"""ロガーと Web UI が使う環境変数の定義。

ランタイム側に `os.environ` を散在させず、必要な値をここで一括して検証する
（CLAUDE.md「環境変数追加時の注意」）。値が足りなければ最初の利用時に明確なエラーで落ちる。

Cosmos DB の接続情報をここに持たないのは、`DefaultAzureCredential` が
`AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`（または `az login`）を
自前で読むため。詳細は `cosmos.py` の docstring を参照。
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache


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


@dataclass(frozen=True)
class Settings:
    """日記管理 UI が必要とする設定値。"""

    cosmos_db_account_url: str
    diary_user_id: str
    admin_user: str
    admin_password: str


def _required(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(f"環境変数 {key} が設定されていません")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定値を読み込む（プロセス内で1回だけ評価する）。"""
    return Settings(
        cosmos_db_account_url=_required("COSMOS_DB_ACCOUNT_URL"),
        # 日記の持ち主（LINE ユーザ ID）。日記コンテナのパーティションキーとして使う。
        diary_user_id=_required("DIARY_USER_ID"),
        admin_user=_required("ADMIN_USER"),
        admin_password=_required("ADMIN_PASSWORD"),
    )
