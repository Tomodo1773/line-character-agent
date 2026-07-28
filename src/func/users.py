"""Cosmos DB `users` コンテナへのアクセス。

保持するのはユーザーごとの「現在の会話 ID」だけで、会話履歴そのものは Foundry が持つ
（ADR-0001 §3）。接続はマネージド ID による RBAC で、アカウントキーは使わない。
"""

from functools import lru_cache
from typing import Any

from azure.cosmos import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential

from config import get_settings
from logger import create_logger

logger = create_logger(__name__)

DATABASE_NAME = "main"
CONTAINER_NAME = "users"


@lru_cache(maxsize=1)
def _container() -> ContainerProxy:
    # データプレーンのロールしか持たないため、データベースやコンテナの作成は行わない。
    client = CosmosClient(url=get_settings().cosmos_db_account_url, credential=DefaultAzureCredential())
    return client.get_database_client(DATABASE_NAME).get_container_client(CONTAINER_NAME)


def _read_user(user_id: str) -> dict[str, Any] | None:
    try:
        return _container().read_item(item=user_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return None


def get_conversation_id(user_id: str) -> str | None:
    """ユーザーの現在の会話 ID を返す。未登録なら None。"""
    logger.info("get_conversation_id が呼び出されました: user_id=%s", user_id)
    user = _read_user(user_id)
    return user.get("conversation_id") if user else None


def save_conversation_id(user_id: str, conversation_id: str) -> None:
    """会話 ID を保存する。プロフィールなど他のフィールドは残す。"""
    logger.info("save_conversation_id が呼び出されました: user_id=%s", user_id)
    user = _read_user(user_id) or {"id": user_id, "userid": user_id}
    user["conversation_id"] = conversation_id
    _container().upsert_item(user)
