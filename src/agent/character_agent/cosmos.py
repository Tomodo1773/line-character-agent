"""Cosmos DB へのアクセス。

保存先は現行スキーマを踏襲する（ADR-0001 §3, §4）。

| 対象 | データベース / コンテナ | パーティションキー |
|------|------------------------|--------------------|
| 日記本文・埋め込みベクトル | `diary` / `entries` | `/userId` |
| プロフィール・ダイジェスト・会話 ID | `main` / `users` | ドキュメント ID（= LINE ユーザ ID） |

接続はマネージド ID（`DefaultAzureCredential`）で、アカウントキーは使わない。
データプレーンのロールしか持たないため、データベースやコンテナの作成は行わない。
"""

import datetime
import uuid
from functools import lru_cache
from typing import Any

from azure.cosmos import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential

from character_agent.config import create_logger, get_settings

logger = create_logger(__name__)

USERS_DATABASE = "main"
USERS_CONTAINER = "users"
DIARY_DATABASE = "diary"
DIARY_CONTAINER = "entries"


@lru_cache(maxsize=1)
def _client() -> CosmosClient:
    return CosmosClient(url=get_settings().cosmos_db_account_url, credential=DefaultAzureCredential())


@lru_cache(maxsize=2)
def _container(database: str, container: str) -> ContainerProxy:
    return _client().get_database_client(database).get_container_client(container)


def _user_id() -> str:
    return get_settings().diary_user_id


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
def read_user() -> dict[str, Any] | None:
    """日記の持ち主のユーザドキュメントを返す。未登録なら None。"""
    user_id = _user_id()
    try:
        return _container(USERS_DATABASE, USERS_CONTAINER).read_item(item=user_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        logger.info("ユーザドキュメントが見つかりませんでした: user_id=%s", user_id)
        return None


def save_user(user: dict[str, Any]) -> None:
    """ユーザドキュメントを保存する。conversation_id など他のフィールドは呼び出し元が保持する。"""
    _container(USERS_DATABASE, USERS_CONTAINER).upsert_item(user)


# ---------------------------------------------------------------------------
# diary entries
# ---------------------------------------------------------------------------
def _date_fields(date: datetime.date) -> dict[str, Any]:
    """既存ドキュメントと同じ日付フィールド一式を組み立てる。"""
    return {
        "date": date.isoformat(),
        "year": date.year,
        "month": date.month,
        "day": date.day,
        "dayOfWeek": date.weekday(),
    }


def find_entry(date: datetime.date) -> dict[str, Any] | None:
    """指定日の日記を返す。無ければ None。"""
    user_id = _user_id()
    items = list(
        _container(DIARY_DATABASE, DIARY_CONTAINER).query_items(
            query="SELECT * FROM c WHERE c.userId = @userId AND c.date = @date",
            parameters=[{"name": "@userId", "value": user_id}, {"name": "@date", "value": date.isoformat()}],
            partition_key=user_id,
        )
    )
    return items[0] if items else None


def create_entry(date: datetime.date, content: str, content_vector: list[float]) -> None:
    """日記を新規作成する。"""
    logger.info("create_entry が呼び出されました: date=%s", date)
    entry = {
        "id": str(uuid.uuid4()),
        "userId": _user_id(),
        "content": content,
        "contentVector": content_vector,
        **_date_fields(date),
    }
    _container(DIARY_DATABASE, DIARY_CONTAINER).create_item(entry)


def update_entry(entry: dict[str, Any], content: str, content_vector: list[float]) -> None:
    """日記の本文と埋め込みベクトルを差し替える。"""
    logger.info("update_entry が呼び出されました: id=%s", entry["id"])
    _container(DIARY_DATABASE, DIARY_CONTAINER).upsert_item({**entry, "content": content, "contentVector": content_vector})


def move_entry(entry: dict[str, Any], new_date: datetime.date) -> None:
    """日記の日付を付け替える。"""
    logger.info("move_entry が呼び出されました: id=%s, new_date=%s", entry["id"], new_date)
    _container(DIARY_DATABASE, DIARY_CONTAINER).upsert_item({**entry, **_date_fields(new_date)})


def delete_entry(entry: dict[str, Any]) -> None:
    """日記を削除する。"""
    logger.info("delete_entry が呼び出されました: id=%s", entry["id"])
    _container(DIARY_DATABASE, DIARY_CONTAINER).delete_item(item=entry["id"], partition_key=entry["userId"])


def search_entries(
    content_vector: list[float] | None,
    keywords: list[str],
    top_k: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """日記を検索する。

    キーワードがあればベクトル検索と全文検索を RRF で統合したハイブリッド検索を行い、
    無ければ日付の新しい順に返す（特定の日や期間を読み返す用途）。

    キーワードは `FullTextScore` の引数としてクエリ本文に埋め込む必要がありパラメータ化できないため、
    引用符とバックスラッシュを取り除いてから埋め込む。
    """
    logger.info("search_entries が呼び出されました: top_k=%d, keywords=%s", top_k, keywords)
    user_id = _user_id()
    conditions = ["c.userId = @userId"]
    parameters: list[dict[str, Any]] = [{"name": "@userId", "value": user_id}]
    if start_date:
        conditions.append("c.date >= @startDate")
        parameters.append({"name": "@startDate", "value": start_date})
    if end_date:
        conditions.append("c.date <= @endDate")
        parameters.append({"name": "@endDate", "value": end_date})

    if keywords:
        parameters.append({"name": "@vector", "value": content_vector})
        keyword_list = ", ".join('"{}"'.format(keyword.replace('"', "").replace("\\", "")) for keyword in keywords)
        ranking = f"ORDER BY RANK RRF(VectorDistance(c.contentVector, @vector), FullTextScore(c.content, {keyword_list}))"
    else:
        ranking = "ORDER BY c.date DESC"

    query = f"""
        SELECT TOP {int(top_k)} c.id, c.date, c.content
        FROM c
        WHERE {" AND ".join(conditions)}
        {ranking}
    """
    return list(
        _container(DIARY_DATABASE, DIARY_CONTAINER).query_items(query=query, parameters=parameters, partition_key=user_id)
    )
