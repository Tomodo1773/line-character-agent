"""日記コンテナ（`diary` / `entries`、パーティションキー `/userId`）の読み取り。

この UI が行うのは一覧・月別絞り込み・本文表示だけで、日記の変更は LINE Agent に一本化する。
読み取り専用のため、埋め込みモデルや Cosmos DB の書き込み権限には依存しない。

接続は `DefaultAzureCredential` を使う。ホスト先の Azure Container Apps Express は
プレビュー段階でマネージド ID とシークレット管理の双方が未対応のため、日記コンテナだけに
権限を絞ったサービスプリンシパルの資格情報を環境変数で渡す（README「日記 Web UI のデプロイ」）。
ローカルでは `az login` したユーザの権限がそのまま使われる。
"""

from functools import lru_cache
from typing import Any

from azure.cosmos import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential

from diary_admin.config import create_logger, get_settings, log_safe

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
    logger.info("list_entries が呼び出されました: month=%s", log_safe(month))
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
        logger.info("日記が見つかりませんでした: id=%s", log_safe(entry_id))
        return None
