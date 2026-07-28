"""評価中だけ Cosmos DB と埋め込みをメモリ上の固定データに差し替える。

評価で見たいのは「依頼に対してどのツールをどう呼ぶか」と「どう返すか」であり、Cosmos DB の
挙動ではない。実データに向けて走らせると日記の削除や日付の付け替えがそのまま反映されてしまうため、
ツールの実体（`character_agent.cosmos` / `character_agent.foundry`）だけを差し替える。
エージェント定義・プロンプト・スキル・ツールのシグネチャは本番と同一のものを評価する。

固定データにすることで、モデルを入れ替えてもツールが返す内容が変わらず、差分をモデルに帰属できる。
"""

import datetime
import json
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator
from unittest.mock import patch

from character_agent import cosmos, foundry
from character_agent.config import create_logger

logger = create_logger(__name__)

EVAL_USER_ID = "eval-user"

# データセットが日付を名指しするケース（修正・削除・付け替え）で参照する日記。
FIXTURE_ENTRIES: list[dict[str, Any]] = [
    {
        "id": "entry-0720",
        "userId": EVAL_USER_ID,
        "date": "2026-07-20",
        "content": "家族と江ノ島に行った。朝から混んでいたけれど、島の上まで登ったら風が気持ちよかった。帰りに生しらす丼を食べた。",
    },
    {
        "id": "entry-0721",
        "userId": EVAL_USER_ID,
        "date": "2026-07-21",
        "content": "会社で健康診断。朝食を抜いていたので午前中はずっと空腹だった。午後は溜まっていたレビューを片付けた。",
    },
    {
        "id": "entry-0722",
        "userId": EVAL_USER_ID,
        "date": "2026-07-22",
        "content": "友人とラーメンを食べに行った。並んだ甲斐はあった。帰り道で来月の旅行の話をした。",
    },
]

FIXTURE_USER: dict[str, Any] = {
    "id": EVAL_USER_ID,
    "userid": EVAL_USER_ID,
    "profile": "ソフトウェアエンジニア。個人開発で LINE のエージェントを作っている。家族は妻と子ども1人。",
    "digest": {
        "version": "2.0",
        "lastUpdated": "2026-07-22",
        "daily": [
            {"date": "2026-07-20", "text": "家族と江ノ島"},
            {"date": "2026-07-21", "text": "会社で健康診断"},
            {"date": "2026-07-22", "text": "友人とラーメン"},
        ],
        "monthly": [],
        "yearly": [],
    },
}

# `digest_regenerate` が呼ぶモデルの応答。再編の中身は評価対象ではないので固定値を返す。
_REORGANIZED_DIGEST = json.dumps(
    {
        "version": "2.0",
        "lastUpdated": "2026-07-22",
        "daily": [],
        "monthly": [{"month": "2026-07", "summary": "夏の始まり", "highlights": ["家族と江ノ島", "会社で健康診断"]}],
        "yearly": [],
    },
    ensure_ascii=False,
)


class _Store:
    """日記とユーザドキュメントをメモリに持つ、`character_agent.cosmos` の代役。"""

    def __init__(self) -> None:
        self.entries = [dict(entry) for entry in FIXTURE_ENTRIES]
        self.user = json.loads(json.dumps(FIXTURE_USER))

    def read_user(self) -> dict[str, Any] | None:
        return self.user

    def save_user(self, user: dict[str, Any]) -> None:
        self.user = user

    def find_entry(self, date: datetime.date) -> dict[str, Any] | None:
        return next((entry for entry in self.entries if entry["date"] == date.isoformat()), None)

    def create_entry(self, date: datetime.date, content: str, content_vector: list[float]) -> None:
        self.entries.append(
            {"id": f"entry-{date.isoformat()}", "userId": EVAL_USER_ID, "date": date.isoformat(), "content": content}
        )

    def update_entry(self, entry: dict[str, Any], content: str, content_vector: list[float]) -> None:
        entry["content"] = content

    def move_entry(self, entry: dict[str, Any], new_date: datetime.date) -> None:
        entry["date"] = new_date.isoformat()

    def delete_entry(self, entry: dict[str, Any]) -> None:
        self.entries = [item for item in self.entries if item["id"] != entry["id"]]

    def search_entries(
        self,
        content_vector: list[float] | None,
        keywords: list[str],
        top_k: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """本番はベクトル + 全文のハイブリッド検索だが、ここでは日付とキーワードの一致だけで代用する。"""
        found = [
            entry
            for entry in self.entries
            if (start_date is None or entry["date"] >= start_date) and (end_date is None or entry["date"] <= end_date)
        ]
        if keywords:
            hits = [(sum(keyword in entry["content"] for keyword in keywords), entry) for entry in found]
            found = [entry for score, entry in sorted(hits, key=lambda hit: -hit[0]) if score > 0]
        else:
            found = sorted(found, key=lambda entry: entry["date"], reverse=True)
        return [{"id": entry["id"], "date": entry["date"], "content": entry["content"]} for entry in found[:top_k]]


@contextmanager
def fake_backend() -> Iterator[_Store]:
    """Cosmos DB とモデル補助呼び出しを差し替える。ケースごとに呼び、状態を持ち越さない。"""
    logger.info("fake_backend が呼び出されました")
    store = _Store()
    replacements = {
        "read_user": store.read_user,
        "save_user": store.save_user,
        "find_entry": store.find_entry,
        "create_entry": store.create_entry,
        "update_entry": store.update_entry,
        "move_entry": store.move_entry,
        "delete_entry": store.delete_entry,
        "search_entries": store.search_entries,
    }
    with ExitStack() as stack:
        for name, replacement in replacements.items():
            stack.enter_context(patch.object(cosmos, name, replacement))
        stack.enter_context(patch.object(foundry, "embed", lambda text: [0.0]))
        stack.enter_context(patch.object(foundry, "complete", lambda instructions, text: _REORGANIZED_DIGEST))
        yield store
