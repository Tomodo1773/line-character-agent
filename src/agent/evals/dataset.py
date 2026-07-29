"""評価データセット（`dataset.jsonl`）の読み込み。

1行が1ケース。`turns` は利用者の発話を順に並べたもので、2件あれば「宣言してから本文を送る」
ような複数ターンの会話を表す。`expected_tools` はその会話全体で呼ばれてほしいツールで、
空リストは「ツールを使わずに答えるべきケース」を意味する。
"""

import json
from dataclasses import dataclass
from pathlib import Path

from agent_framework import ExpectedToolCall

DATASET_PATH = Path(__file__).parent / "dataset.jsonl"


@dataclass(frozen=True)
class Case:
    """評価する発話1件。"""

    id: str
    description: str
    turns: list[str]
    expected_tools: list[ExpectedToolCall]


def load_cases(path: Path = DATASET_PATH) -> list[Case]:
    """データセットを読み込む。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_parse(json.loads(line)) for line in lines if line.strip()]


def _parse(raw: dict) -> Case:
    return Case(
        id=raw["id"],
        description=raw["description"],
        turns=raw["turns"],
        expected_tools=[
            ExpectedToolCall(name=tool["name"], arguments=tool.get("arguments")) for tool in raw["expected_tools"]
        ],
    )
