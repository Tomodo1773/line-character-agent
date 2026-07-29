"""エージェントに登録するツール群（ADR-0001 §2）。

日記の実体は Cosmos DB にあり、埋め込みの生成は Foundry プロジェクト経由で行う。
日付の指定はすべて YYYY-MM-DD 形式に統一する。

**ツールの中から生成 LLM や別のエージェントを呼び出さない。** 文章を作るのはスキルを読んだ
メインエージェント自身の仕事で、ツールは読み取りと、検証つきの書き込みだけを担う。
ベクトル索引に要る埋め込み生成（`foundry.embed`）だけは機械的な処理として例外とする。
"""

import datetime
import json
from typing import Annotated
from zoneinfo import ZoneInfo

from agent_framework import tool

from character_agent import cosmos, digest, foundry
from character_agent.config import create_logger

logger = create_logger(__name__)

JAPAN = ZoneInfo("Asia/Tokyo")

MAX_SEARCH_RESULTS = 20

# `read_profile` で直近の出来事として見せる日次要約の件数。
RECENT_SUMMARY_COUNT = 30
# 1 か月分の日次要約を取るための件数。日記は 1 日 1 件なので、どの月でもこれで足りる。
DIGEST_SOURCE_LIMIT = 31


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"日付の形式が正しくありません: {value}（YYYY-MM-DD 形式で指定してください）") from error


def _previous_month(today: datetime.date) -> str:
    """前月を YYYY-MM で返す。当月はまだ揃っていないので集約対象にしない。"""
    return (today.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")


def _month_range(month: str) -> tuple[str, str]:
    """YYYY-MM から、その月の初日と末日を YYYY-MM-DD で返す。"""
    try:
        start = datetime.date.fromisoformat(f"{month}-01")
    except ValueError as error:
        raise ValueError(f"月の形式が正しくありません: {month}（YYYY-MM 形式で指定してください）") from error
    # 28日に4日足すと必ず翌月に入る。その月の1日へ戻して1日引けば末日になる。
    end = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _reject_taken_date(target: datetime.date) -> str | None:
    """その日付に既に日記があれば拒否理由を返す。無ければ None。

    1 日 1 件を保つための唯一のガード。新規登録と日付の付け替えの両方から呼ぶ。
    """
    if not cosmos.find_entry(target):
        return None
    return f"{target.isoformat()} には既に日記があるため登録・付け替えできません。内容を変えるなら diary_update を使ってください。"


@tool(approval_mode="never_require", description="現在の日本時間（日付・時刻・曜日）を取得する。")
def get_current_datetime() -> Annotated[str, "yyyy-mm-dd hh:mm:ss (曜日) 形式の日本時間"]:
    """現在の日本時間を返す。

    プロンプトに日時を埋め込むとコンテナの起動時刻で固定されてしまうため、ツールとして都度取得する。
    """
    logger.info("get_current_datetime が呼び出されました")
    return datetime.datetime.now(JAPAN).strftime("%Y-%m-%d %H:%M:%S (%a)")


@tool(approval_mode="never_require", description="ユーザのプロフィールと直近の出来事ダイジェストを読む。")
def read_profile() -> str:
    """プロフィールと月次・年次ダイジェストを `users` から、直近の日次要約を日記から読む。"""
    logger.info("read_profile が呼び出されました")
    user = cosmos.read_user() or {}
    profile = user.get("profile") or "（プロフィールは未登録）"
    rendered = digest.render(digest.normalize(user.get("digest")), cosmos.list_summaries(RECENT_SUMMARY_COUNT))
    return f"## プロフィール\n{profile}\n\n## 直近の出来事\n{rendered}"


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
    summary: Annotated[str, "その日を表す2-5語の要約。日記と一緒に保存し、月次ダイジェストの材料になる"],
) -> str:
    """日記を新規作成する。本文・埋め込み・日次要約は同じドキュメントへ 1 回で書く。"""
    logger.info("diary_create が呼び出されました: date=%s", date)
    target = _parse_date(date)
    taken = _reject_taken_date(target)
    if taken:
        return taken

    cosmos.create_entry(target, content, foundry.embed(content), summary)
    return f"{date} の日記を登録しました。"


@tool(
    approval_mode="never_require",
    description="既存の日記を更新する。追記する場合も、既存本文と合わせた全文を content に渡す。",
)
def diary_update(
    date: Annotated[str, "更新する日記の対象日 (YYYY-MM-DD)"],
    content: Annotated[str, "更新後の日記の全文"],
    summary: Annotated[str, "その日を表す2-5語の要約。日記と一緒に保存し、月次ダイジェストの材料になる"],
) -> str:
    """日記の本文・埋め込みベクトル・日次要約を同じドキュメントで差し替える。"""
    logger.info("diary_update が呼び出されました: date=%s", date)
    target = _parse_date(date)
    entry = cosmos.find_entry(target)
    if not entry:
        return f"{date} の日記は見つかりませんでした。新規作成するなら diary_create を使ってください。"

    cosmos.update_entry(entry, content, foundry.embed(content), summary)
    return f"{date} の日記を更新しました。"


@tool(approval_mode="never_require", description="指定した日付の日記を削除する。")
def diary_delete(date: Annotated[str, "削除する日記の対象日 (YYYY-MM-DD)"]) -> str:
    """日記を削除する。日次要約も同じドキュメントにあるので一緒に消える。"""
    logger.info("diary_delete が呼び出されました: date=%s", date)
    target = _parse_date(date)
    entry = cosmos.find_entry(target)
    if not entry:
        return f"{date} の日記は見つかりませんでした。"

    cosmos.delete_entry(entry)
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
    taken = _reject_taken_date(new_target)
    if taken:
        return taken

    cosmos.move_entry(entry, new_target)
    return f"{date} の日記を {new_date} に付け替えました。"


@tool(
    approval_mode="never_require",
    description="ダイジェストをまとめ直すための材料（対象月の日次要約と、今の月次・年次ダイジェスト）を読む。",
)
def digest_read(
    month: Annotated[str | None, "集約する対象月 (YYYY-MM)。省略すると前月"] = None,
) -> str:
    """集約の材料を読むだけのツール。要約そのものはここでは作らない。

    材料は日記ドキュメントの `summary`（日次要約）と `users.digest`（月次・年次）だけで、
    日記本文は読み直さない。まとめ方は `digest-rollup` スキルに書いてある。
    """
    logger.info("digest_read が呼び出されました: month=%s", month)
    today = datetime.datetime.now(JAPAN).date()
    target = month or _previous_month(today)
    start, end = _month_range(target)
    # 末日までを新しい順に 1 か月分ぶん取り、初日より前へはみ出した分を落とす。
    summaries = [item for item in cosmos.list_summaries(DIGEST_SOURCE_LIMIT, end_date=end) if item.get("date", "") >= start]
    current = digest.normalize((cosmos.read_user() or {}).get("digest"))
    return json.dumps(
        {"today": today.isoformat(), "targetMonth": target, "dailySummaries": summaries, "digest": current},
        ensure_ascii=False,
    )


@tool(
    approval_mode="never_require",
    description="まとめ直した月次・年次ダイジェストを保存する。要約の文面は自分で組み立てて渡す。",
)
def digest_save(
    digest_json: Annotated[
        str,
        '{"monthly": [{"month": "YYYY-MM", "summary": "...", "highlights": ["..."]}], '
        '"yearly": [{"year": "YYYY", "summary": "...", "highlights": ["..."]}]} 形式の JSON 全文',
    ],
) -> str:
    """受け取ったダイジェストを検証して Cosmos DB へ書く。

    このツールがするのは構造の検証と保存だけで、内容の生成には関わらない。
    形が崩れていれば例外の文言がそのままモデルへ返り、直して呼び直せる。
    """
    logger.info("digest_save が呼び出されました")
    parsed = digest.parse(digest_json)
    digest.validate(parsed)

    today = datetime.datetime.now(JAPAN).date()
    cosmos.save_digest({**parsed, "lastUpdated": today.isoformat()})
    return f"ダイジェストを保存しました（月次 {len(parsed['monthly'])} 件・年次 {len(parsed['yearly'])} 件）。"


TOOLS = [
    get_current_datetime,
    read_profile,
    diary_search,
    diary_create,
    diary_update,
    diary_delete,
    diary_rename,
    digest_read,
    digest_save,
]
