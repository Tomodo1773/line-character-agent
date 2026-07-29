"""日記を Markdown として Blob Storage へ日次エクスポートする Timer トリガー。

Cosmos DB の定期バックアップとは別に、人間がそのまま読める退避先を用意する（ADR-0001 §4）。
Cosmos DB / Blob Storage いずれもマネージド ID で接続し、アカウントキーは使わない。
"""

import datetime
from functools import lru_cache
from typing import Any

import azure.functions as func
from azure.cosmos import ContainerProxy, CosmosClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient

import line_client
from config import get_settings
from logger import create_logger

logger = create_logger(__name__)

bp = func.Blueprint()

DATABASE_NAME = "diary"
CONTAINER_NAME = "entries"

JST = datetime.timezone(datetime.timedelta(hours=9), "JST")

# NCRONTAB は既定で UTC 評価（WEBSITE_TIME_ZONE は未設定）。19:00 UTC = 翌 04:00 JST。
SCHEDULE = "0 0 19 * * *"

FAILURE_NOTICE = "日記のバックアップに失敗しちゃった。Application Insights のログを確認してね。"


@bp.timer_trigger(arg_name="timer", schedule=SCHEDULE, run_on_startup=False)
def diary_backup(timer: func.TimerRequest) -> None:
    logger.info("diary_backup が呼び出されました")
    try:
        export(datetime.datetime.now(JST).date())
    except Exception:
        logger.exception("日記のバックアップに失敗しました")
        # 能動的な push も月200通の枠を消費するため、成功時は通知しない（ADR-0001 リスク節）。
        line_client.push(get_settings().diary_user_id, FAILURE_NOTICE)
        raise


def export(run_date: datetime.date) -> None:
    """日記の全件を利用者ごとの Markdown にまとめ、実行日のフォルダへ書き出す。"""
    entries = _fetch_entries()
    for user_id, user_entries in _group_by_user(entries).items():
        _upload(f"{run_date.isoformat()}/{user_id}.md", render_markdown(user_id, run_date, user_entries))
    logger.info("%d 件の日記をバックアップしました: run_date=%s", len(entries), run_date)


def render_markdown(user_id: str, run_date: datetime.date, entries: list[dict[str, Any]]) -> str:
    """1人分の日記を、新しい順に並べた1つの Markdown にする。"""
    lines = [
        f"# 日記バックアップ ({user_id})",
        "",
        f"- 出力日: {run_date.isoformat()}（JST）",
        f"- 件数: {len(entries)}",
    ]
    for entry in sorted(entries, key=lambda entry: entry["date"], reverse=True):
        lines += ["", f"## {entry['date']}", "", entry["content"].strip()]
    return "\n".join(lines) + "\n"


def _fetch_entries() -> list[dict[str, Any]]:
    """全利用者の日記を読む。

    パーティションキーを指定しないクエリはクロスパーティションで実行される。
    埋め込みベクトルは人が読めずサイズも大きいため、射影して除外する。
    """
    return list(_diary_container().query_items(query="SELECT c.userId, c.date, c.content FROM c"))


def _group_by_user(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(entry["userId"], []).append(entry)
    return grouped


def _upload(blob_name: str, markdown: str) -> None:
    logger.info("バックアップを書き出します: blob=%s", blob_name)
    _backup_container().upload_blob(name=blob_name, data=markdown.encode("utf-8"), overwrite=True)


@lru_cache(maxsize=1)
def _diary_container() -> ContainerProxy:
    client = CosmosClient(url=get_settings().cosmos_db_account_url, credential=DefaultAzureCredential())
    return client.get_database_client(DATABASE_NAME).get_container_client(CONTAINER_NAME)


@lru_cache(maxsize=1)
def _backup_container() -> ContainerClient:
    settings = get_settings()
    return ContainerClient(
        account_url=f"https://{settings.storage_account_name}.blob.core.windows.net",
        container_name=settings.diary_backup_container_name,
        credential=DefaultAzureCredential(),
    )
