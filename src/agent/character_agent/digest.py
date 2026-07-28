"""日記ダイジェスト（直近の出来事）の組み立て。

`users` ドキュメントの `digest` フィールドに次の形で保存する。日ごとの記録が溜まったら
`digest_regenerate` ツールが月ごと・年ごとへ圧縮する（旧 `digest_reorganizer` の役割）。

```json
{
  "version": "2.0",
  "lastUpdated": "2026-07-28",
  "daily":   [{"date": "2026-07-27", "text": "家族と映画"}],
  "monthly": [{"month": "2026-06", "summary": "...", "highlights": ["..."]}],
  "yearly":  [{"year": "2025", "summary": "...", "highlights": ["..."]}]
}
```
"""

import json
from typing import Any

VERSION = "2.0"


def normalize(raw: Any) -> dict[str, Any]:
    """保存されている値を既定の形に整える。未登録・壊れている場合は空のダイジェストを返す。"""
    digest = raw if isinstance(raw, dict) else {}
    return {
        "version": digest.get("version", VERSION),
        "lastUpdated": digest.get("lastUpdated", ""),
        "daily": digest.get("daily", []),
        "monthly": digest.get("monthly", []),
        "yearly": digest.get("yearly", []),
    }


def _sorted_daily(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(daily, key=lambda item: item.get("date", ""))


def upsert_daily(digest: dict[str, Any], date: str, text: str) -> dict[str, Any]:
    """指定日の記録を差し替える（無ければ追加する）。"""
    daily = [item for item in digest["daily"] if item.get("date") != date]
    daily.append({"date": date, "text": text})
    return {**digest, "daily": _sorted_daily(daily)}


def remove_daily(digest: dict[str, Any], date: str) -> dict[str, Any]:
    """指定日の記録を取り除く。"""
    return {**digest, "daily": [item for item in digest["daily"] if item.get("date") != date]}


def move_daily(digest: dict[str, Any], date: str, new_date: str) -> dict[str, Any]:
    """指定日の記録を別の日付へ付け替える。"""
    daily = [{**item, "date": new_date} if item.get("date") == date else item for item in digest["daily"]]
    return {**digest, "daily": _sorted_daily(daily)}


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


def render(digest: dict[str, Any]) -> str:
    """モデルが読みやすい形にダイジェストを整形する。"""
    lines = [f"- {item.get('date', '')} {item.get('text', '')}" for item in digest["daily"]]
    lines += [_render_summary(item.get("month", ""), item) for item in digest["monthly"]]
    lines += [_render_summary(item.get("year", ""), item) for item in digest["yearly"]]
    return "\n".join(lines) if lines else "（まだ記録がありません）"


def _render_summary(period: str, item: dict[str, Any]) -> str:
    highlights = "／".join(item.get("highlights", []))
    return f"- {period} {item.get('summary', '')}（{highlights}）"
