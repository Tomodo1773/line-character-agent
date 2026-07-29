"""日記ダイジェスト（直近の出来事）の組み立て。

ダイジェストは「日記本文 → 日次要約 → 月次要約 → 年次要約」の段階集約で作る。
日次要約は日記ドキュメントの `summary` にあり、`users` ドキュメントには持たない。
`users` ドキュメントの `digest` フィールドには、集約済みの月次・年次だけを次の形で保存する。

```json
{
  "version": "3.0",
  "lastUpdated": "2026-07-28",
  "monthly": [{"month": "2026-06", "summary": "...", "highlights": ["..."]}],
  "yearly":  [{"year": "2025", "summary": "...", "highlights": ["..."]}]
}
```
"""

import json
import re
from typing import Any

VERSION = "3.0"

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_YEAR = re.compile(r"^\d{4}$")


def normalize(raw: Any) -> dict[str, Any]:
    """保存されている値を既定の形に整える。未登録・壊れている場合は空のダイジェストを返す。

    日次要約は日記ドキュメント側へ移したため、旧スキーマの `daily` は読み捨てる。
    """
    digest = raw if isinstance(raw, dict) else {}
    return {
        "version": VERSION,
        "lastUpdated": digest.get("lastUpdated", ""),
        "monthly": digest.get("monthly", []),
        "yearly": digest.get("yearly", []),
    }


def parse(text: str) -> dict[str, Any]:
    """モデルが返した JSON を読む。コードフェンスで囲まれていても受け付ける。

    Raises:
        ValueError: JSON として読めない場合。
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.split("```")[1].removeprefix("json").strip()
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("ダイジェストがオブジェクトではありません")
    return normalize(parsed)


def validate(digest: dict[str, Any]) -> None:
    """保存前に月次・年次の構造を検証する。

    ダイジェストの中身（どう要約するか）を作るのはスキルを読んだエージェント自身で、ここは
    「保存してよい形か」だけを見る。エージェントが崩した形で渡してきたときに、Cosmos DB へ
    書く前に気づけるようにするのがこの関数の役割。例外の文言はそのままモデルへ返るため
    （`include_detailed_errors`）、どこを直せばよいか分かる文にする。

    Raises:
        ValueError: 期間の形式・必須項目・重複・月次と年次の重なりに問題がある場合。
    """
    months = [_validate_period(item, "monthly", "month", _MONTH, "YYYY-MM") for item in digest["monthly"]]
    years = [_validate_period(item, "yearly", "year", _YEAR, "YYYY") for item in digest["yearly"]]
    _reject_duplicates(months, "monthly の month")
    _reject_duplicates(years, "yearly の year")

    # 同じ期間を月次と年次で二重に持たない。年次へまとめた年の月次は消してから保存する。
    rolled_up = sorted({month for month in months if month[:4] in set(years)})
    if rolled_up:
        raise ValueError(f"年次へまとめ済みの年の月次が残っています: {rolled_up}（monthly から取り除いてください）")


def _validate_period(item: Any, section: str, key: str, pattern: re.Pattern[str], form: str) -> str:
    if not isinstance(item, dict):
        raise ValueError(f"{section} の要素がオブジェクトではありません: {item!r}")
    period = item.get(key)
    if not isinstance(period, str) or not pattern.fullmatch(period):
        raise ValueError(f"{section} の {key} が {form} 形式ではありません: {period!r}")
    if not isinstance(item.get("summary"), str) or not item["summary"].strip():
        raise ValueError(f"{section} の {period} に summary がありません")
    highlights = item.get("highlights", [])
    if not isinstance(highlights, list) or any(not isinstance(text, str) for text in highlights):
        raise ValueError(f"{section} の {period} の highlights が文字列の配列ではありません")
    return period


def _reject_duplicates(periods: list[str], label: str) -> None:
    duplicated = sorted({period for period in periods if periods.count(period) > 1})
    if duplicated:
        raise ValueError(f"{label} が重複しています: {duplicated}")


def render(digest: dict[str, Any], summaries: list[dict[str, Any]]) -> str:
    """モデルが読みやすい形に、日次要約と月次・年次ダイジェストを並べて整形する。"""
    lines = [f"- {item.get('date', '')} {item.get('summary', '')}" for item in summaries]
    lines += [_render_summary(item.get("month", ""), item) for item in digest["monthly"]]
    lines += [_render_summary(item.get("year", ""), item) for item in digest["yearly"]]
    return "\n".join(lines) if lines else "（まだ記録がありません）"


def _render_summary(period: str, item: dict[str, Any]) -> str:
    highlights = "／".join(item.get("highlights", []))
    return f"- {period} {item.get('summary', '')}（{highlights}）"
