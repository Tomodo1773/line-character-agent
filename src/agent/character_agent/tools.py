"""エージェントに登録するツール群（ADR-0001 §2）。

日記の実体は Cosmos DB にあり、埋め込みと再編用のモデル呼び出しは Foundry プロジェクト経由で行う。
日付の指定はすべて YYYY-MM-DD 形式に統一する。
"""

import datetime
import json
from typing import Annotated, Any, Callable
from zoneinfo import ZoneInfo

from agent_framework import tool

from character_agent import cosmos, digest, foundry
from character_agent.config import create_logger, get_settings
from character_agent.prompts import DIGEST_REORGANIZE_PROMPT

logger = create_logger(__name__)

JAPAN = ZoneInfo("Asia/Tokyo")

MAX_SEARCH_RESULTS = 20


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"日付の形式が正しくありません: {value}（YYYY-MM-DD 形式で指定してください）") from error


def _update_digest(change: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """ユーザドキュメントのダイジェストだけを書き換える。他のフィールドはそのまま残す。"""
    user_id = get_settings().diary_user_id
    user = cosmos.read_user() or {"id": user_id, "userid": user_id}
    user["digest"] = change(digest.normalize(user.get("digest")))
    cosmos.save_user(user)


@tool(approval_mode="never_require", description="現在の日本時間（日付・時刻・曜日）を取得する。")
def get_current_datetime() -> Annotated[str, "yyyy-mm-dd hh:mm:ss (曜日) 形式の日本時間"]:
    """現在の日本時間を返す。

    プロンプトに日時を埋め込むとコンテナの起動時刻で固定されてしまうため、ツールとして都度取得する。
    """
    logger.info("get_current_datetime が呼び出されました")
    return datetime.datetime.now(JAPAN).strftime("%Y-%m-%d %H:%M:%S (%a)")


@tool(approval_mode="never_require", description="ユーザのプロフィールと直近の出来事ダイジェストを読む。")
def read_profile() -> str:
    """Cosmos DB の `users` ドキュメントからプロフィールとダイジェストを読む。"""
    logger.info("read_profile が呼び出されました")
    user = cosmos.read_user() or {}
    profile = user.get("profile") or "（プロフィールは未登録）"
    return f"## プロフィール\n{profile}\n\n## 直近の出来事\n{digest.render(digest.normalize(user.get('digest')))}"


@tool(
    approval_mode="never_require",
    description=(
        "過去の日記を検索する。話題やキーワードで探すときは query_text を指定し、"
        "特定の日や期間の日記を読みたいときは start_date / end_date だけを指定する。"
    ),
)
def diary_search(
    query_text: Annotated[str | None, "検索したい話題を自然文で。日付だけで絞り込むときは省略する"] = None,
    top_k: Annotated[int, "返す件数 (1-20)"] = 5,
    start_date: Annotated[str | None, "絞り込み開始日 (YYYY-MM-DD)"] = None,
    end_date: Annotated[str | None, "絞り込み終了日 (YYYY-MM-DD)"] = None,
) -> str:
    """ベクトル検索と全文検索を組み合わせて日記を探す。query_text が無ければ新しい順に返す。"""
    logger.info(
        "diary_search が呼び出されました: query_text=%s, top_k=%s, start_date=%s, end_date=%s",
        query_text,
        top_k,
        start_date,
        end_date,
    )
    keywords = query_text.split() if query_text else []
    entries = cosmos.search_entries(
        content_vector=foundry.embed(query_text) if keywords else None,
        keywords=keywords,
        top_k=min(max(top_k, 1), MAX_SEARCH_RESULTS),
        start_date=start_date,
        end_date=end_date,
    )
    if not entries:
        return "該当する日記は見つかりませんでした。"
    return "\n\n".join(f"【{entry['date']}】\n{entry['content']}" for entry in entries)


@tool(
    approval_mode="never_require",
    description="新しい日記を登録する。同じ日付の日記が既にあるときは diary_update を使う。",
)
def diary_create(
    date: Annotated[str, "日記の対象日 (YYYY-MM-DD)"],
    content: Annotated[str, "日記の本文。ユーザが送ってきた文章をそのまま渡す"],
    summary: Annotated[str, "その日を表す2-5語の要約。ダイジェストに記録する"],
) -> str:
    """日記を新規作成し、ダイジェストにその日の記録を追加する。"""
    logger.info("diary_create が呼び出されました: date=%s", date)
    target = _parse_date(date)
    if cosmos.find_entry(target):
        return f"{date} の日記は既に登録されています。更新するなら diary_update を使ってください。"

    cosmos.create_entry(target, content, foundry.embed(content))
    _update_digest(lambda current: digest.upsert_daily(current, date, summary))
    return f"{date} の日記を登録しました。"


@tool(
    approval_mode="never_require",
    description="既存の日記を更新する。追記する場合も、既存本文と合わせた全文を content に渡す。",
)
def diary_update(
    date: Annotated[str, "更新する日記の対象日 (YYYY-MM-DD)"],
    content: Annotated[str, "更新後の日記の全文"],
    summary: Annotated[str, "その日を表す2-5語の要約。ダイジェストに記録する"],
) -> str:
    """日記の本文を差し替え、埋め込みベクトルとダイジェストを更新する。"""
    logger.info("diary_update が呼び出されました: date=%s", date)
    target = _parse_date(date)
    entry = cosmos.find_entry(target)
    if not entry:
        return f"{date} の日記は見つかりませんでした。新規作成するなら diary_create を使ってください。"

    cosmos.update_entry(entry, content, foundry.embed(content))
    _update_digest(lambda current: digest.upsert_daily(current, date, summary))
    return f"{date} の日記を更新しました。"


@tool(approval_mode="never_require", description="指定した日付の日記を削除する。")
def diary_delete(date: Annotated[str, "削除する日記の対象日 (YYYY-MM-DD)"]) -> str:
    """日記とダイジェストの記録を削除する。"""
    logger.info("diary_delete が呼び出されました: date=%s", date)
    target = _parse_date(date)
    entry = cosmos.find_entry(target)
    if not entry:
        return f"{date} の日記は見つかりませんでした。"

    cosmos.delete_entry(entry)
    _update_digest(lambda current: digest.remove_daily(current, date))
    return f"{date} の日記を削除しました。"


@tool(
    approval_mode="never_require",
    description="日記の日付を付け替える。日付を間違えて登録したときに使う。",
)
def diary_rename(
    date: Annotated[str, "現在の日付 (YYYY-MM-DD)"],
    new_date: Annotated[str, "付け替え後の日付 (YYYY-MM-DD)"],
) -> str:
    """日記の日付を変更する。移動先に既に日記がある場合は何もしない。"""
    logger.info("diary_rename が呼び出されました: date=%s, new_date=%s", date, new_date)
    target = _parse_date(date)
    new_target = _parse_date(new_date)
    entry = cosmos.find_entry(target)
    if not entry:
        return f"{date} の日記は見つかりませんでした。"
    if cosmos.find_entry(new_target):
        return f"{new_date} には既に日記があるため付け替えできません。"

    cosmos.move_entry(entry, new_target)
    _update_digest(lambda current: digest.move_daily(current, date, new_date))
    return f"{date} の日記を {new_date} に付け替えました。"


@tool(
    approval_mode="never_require",
    description="ダイジェストの日ごとの記録を月ごと・年ごとにまとめ直す。",
)
def digest_regenerate() -> str:
    """ダイジェストを再編する（旧 digest_reorganizer の役割）。"""
    logger.info("digest_regenerate が呼び出されました")
    today = datetime.datetime.now(JAPAN).date().isoformat()
    user_id = get_settings().diary_user_id
    user = cosmos.read_user() or {"id": user_id, "userid": user_id}
    current = digest.normalize(user.get("digest"))

    answer = foundry.complete(
        DIGEST_REORGANIZE_PROMPT,
        f"日本時間での今日の日付は {today} です。次のダイジェストを再編してください。\n"
        f"{json.dumps(current, ensure_ascii=False)}",
    )
    user["digest"] = {**digest.parse(answer), "lastUpdated": today}
    cosmos.save_user(user)
    return "ダイジェストを再編しました。"


TOOLS = [
    get_current_datetime,
    read_profile,
    diary_search,
    diary_create,
    diary_update,
    diary_delete,
    diary_rename,
    digest_regenerate,
]
