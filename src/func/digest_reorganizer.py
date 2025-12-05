"""digest.json を Deep Agent で再編成するヘルパー。"""

from __future__ import annotations

import json
import tempfile
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_openai import ChatOpenAI

from logger import logger

JST = ZoneInfo("Asia/Tokyo")

DEFAULT_DIGEST = {
    "version": "2.0",
    "lastUpdated": "",
    "daily": [],
    "monthly": [],
    "yearly": [],
}

SYSTEM_PROMPT = """
あなたは日記ダイジェスト整理担当のエージェントです。
対象ファイル: /digest.json

スキーマ（version 2.0）:
- lastUpdated: YYYY-MM-DD（最終更新日）
- daily: [{"date": "YYYY-MM-DD", "text": "..."}] 当月の出来事のみを保持
- monthly: [{"month": "YYYY-MM", "summary": "月の要約", "highlights": [{"date": "YYYY-MM-DD", "text": "印象的な出来事"}]}]
- yearly: [{"year": "YYYY", "summary": "年の要約", "highlights": [{"month": "YYYY-MM", "text": "印象的な出来事"}]}]

編集ルール:
- digest.json を読み、ツールを使って直接編集する（Read/Write/Edit を活用）。
- 今日と同じ月の daily は残し、過去月の daily は月単位にまとめて monthly に移す。
- monthly を作成・更新する際は印象的な出来事を 3-7 件に圧縮し、summary を簡潔に書く。
- 過去年の monthly は年単位にまとめて yearly を更新する（highlights は月を参照、3-7 件）。
- 既存の monthly/yearly がある場合は同じ月/年を統合して最新情報を先頭に置く。
- スキーマ外のフィールドを増やさず、JSON を壊さないこと。
"""


class AgentRunner(Protocol):
    """Deep Agent の最小インターフェース."""

    @abstractmethod
    def invoke(self, input: dict, /, stream_mode: str | None = None) -> object:  # pragma: no cover - interface only
        """LangGraph Deep Agent の実装側が提供する実行メソッド."""



def _render_user_prompt(today: str) -> str:
    return (
        "日本時間での今日の日付は {today} です。"
        " /digest.json を読み込み、ルールに従って日次→月次→年次へ再編してください。"
        " lastUpdated も {today} に更新し、保存するファイルが有効な JSON になるようにしてください。"
    ).format(today=today)


def _initialize_digest(raw_text: str, today: str) -> dict:
    if not raw_text.strip():
        digest = {**DEFAULT_DIGEST, "lastUpdated": today}
        return digest

    try:
        digest = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("digest.json が壊れているため初期化します")
        digest = {**DEFAULT_DIGEST}

    digest.setdefault("version", "2.0")
    digest.setdefault("daily", [])
    digest.setdefault("monthly", [])
    digest.setdefault("yearly", [])
    digest["lastUpdated"] = today
    return digest


def _update_last_updated(content: str, today: str) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Deep Agent 実行後の digest.json が JSON ではありませんでした")
        return content

    data["lastUpdated"] = today
    return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass
class DeepAgentFactory:
    model_name: str = "gpt-5.1"

    def __call__(self, workspace: Path) -> AgentRunner:
        backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
        llm = ChatOpenAI(model=self.model_name, temperature=0)
        return create_deep_agent(model=llm, system_prompt=SYSTEM_PROMPT, backend=backend)


class DigestReorganizer:
    """digest.json の再編処理を Deep Agent で実行する。"""

    def __init__(self, *, agent_factory: Callable[[Path], AgentRunner] | None = None, model_name: str = "gpt-5.1") -> None:
        self.agent_factory = agent_factory or DeepAgentFactory(model_name)

    def reorganize(self, raw_digest: str, *, today_override: str | None = None) -> str:
        today = today_override or datetime.now(JST).strftime("%Y-%m-%d")
        base_digest = _initialize_digest(raw_digest, today)

        with tempfile.TemporaryDirectory() as workspace:
            digest_path = Path(workspace) / "digest.json"
            digest_path.write_text(json.dumps(base_digest, ensure_ascii=False, indent=2), encoding="utf-8")

            agent = self.agent_factory(Path(workspace))
            user_prompt = _render_user_prompt(today)
            agent.invoke({"messages": [("user", user_prompt)]})

            updated_content = digest_path.read_text(encoding="utf-8")

        return _update_last_updated(updated_content, today)
