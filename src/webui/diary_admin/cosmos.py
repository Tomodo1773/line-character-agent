"""日記コンテナ（`diary` / `entries`、パーティションキー `/userId`）へのアクセス。

この UI が行うのは **閲覧・日付変更・削除だけ**で、作成と本文の編集は LINE 経由が本線となる。
本文が変わらない以上 `contentVector` を作り直す必要がないため、埋め込みモデルには一切依存しない。
日付変更は `date` 系フィールドだけを差し替え、`contentVector` はそのまま残す。

接続は `DefaultAzureCredential` を使う。ホスト先の Azure Container Apps Express は
プレビュー段階でマネージド ID とシークレット管理の双方が未対応のため、日記コンテナだけに
権限を絞ったサービスプリンシパルの資格情報を環境変数で渡す（README「日記 Web UI のデプロイ」）。
ローカルでは `az login` したユーザの権限がそのまま使われる。
"""

import datetime
from functools import lru_cache
from typing import Any

from azure.cosmos import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential

from diary_admin.config import create_logger, get_settings

logger = create_logger(__name__)

DIARY_DATABASE = "diary"
DIARY_CONTAINER = "entries"


@lru_cache(maxsize=1)
def _container() -> ContainerProxy:
    client = CosmosClient(url=get_settings().cosmos_db_account_url, credential=DefaultAzureCredential())
    return client.get_database_client(DIARY_DATABASE).get_container_client(DIARY_CONTAINER)


def _query(query: str, parameters: list[dict[str, Any]]) -> list[Any]:
    """持ち主のパーティションに閉じたクエリを実行する。`@userId` は常に補われる。"""
    user_id = get_settings().diary_user_id
    return list(
        _container().query_items(
            query=query,
            parameters=[{"name": "@userId", "value": user_id}, *parameters],
            partition_key=user_id,
        )
    )


def list_entries(month: str | None) -> list[dict[str, Any]]:
    """日記の一覧を日付の降順で返す。`month`（`YYYY-MM`）を渡すとその月だけに絞る。

    一覧では本文の冒頭しか表示しないため、本文全体は取得しない。
    """
    logger.info("list_entries が呼び出されました: month=%s", month)
    condition = " AND STARTSWITH(c.date, @month)" if month else ""
    parameters = [{"name": "@month", "value": month}] if month else []
    return _query(
        f"SELECT c.id, c.date, LEFT(c.content, 80) AS preview FROM c WHERE c.userId = @userId{condition} ORDER BY c.date DESC",
        parameters,
    )


def list_months() -> list[str]:
    """日記が存在する月（`YYYY-MM`）を新しい順に返す。月別フィルタの選択肢に使う。"""
    return sorted(_query("SELECT DISTINCT VALUE LEFT(c.date, 7) FROM c WHERE c.userId = @userId", []), reverse=True)


def read_entry(entry_id: str) -> dict[str, Any] | None:
    """指定 ID の日記を返す。無ければ None。"""
    user_id = get_settings().diary_user_id
    try:
        return _container().read_item(item=entry_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        logger.info("日記が見つかりませんでした: id=%s", entry_id)
        return None


def change_date(entry: dict[str, Any], new_date: datetime.date) -> None:
    """日記の日付を付け替える。本文は変わらないので `contentVector` はそのまま残す。

    upsert ではなく replace を使うのは、この UI の資格情報に作成権限を持たせないため。
    """
    logger.info("change_date が呼び出されました: id=%s, new_date=%s", entry["id"], new_date)
    date_fields = {
        "date": new_date.isoformat(),
        "year": new_date.year,
        "month": new_date.month,
        "day": new_date.day,
        "dayOfWeek": new_date.weekday(),
    }
    _container().replace_item(item=entry["id"], body={**entry, **date_fields})


def delete_entry(entry: dict[str, Any]) -> None:
    """日記を削除する。"""
    logger.info("delete_entry が呼び出されました: id=%s", entry["id"])
    _container().delete_item(item=entry["id"], partition_key=entry["userId"])
