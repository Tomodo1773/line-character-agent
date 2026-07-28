"""ダイジェストの組み立て（純粋な変換処理）を確認する。"""

import pytest

from character_agent import digest


def test_normalize_fills_missing_sections():
    assert digest.normalize(None) == {
        "version": digest.VERSION,
        "lastUpdated": "",
        "daily": [],
        "monthly": [],
        "yearly": [],
    }


def test_upsert_daily_replaces_same_date_and_keeps_order():
    current = digest.normalize({"daily": [{"date": "2026-07-27", "text": "古い"}]})

    updated = digest.upsert_daily(digest.upsert_daily(current, "2026-07-27", "新しい"), "2026-07-26", "前の日")

    assert updated["daily"] == [
        {"date": "2026-07-26", "text": "前の日"},
        {"date": "2026-07-27", "text": "新しい"},
    ]


def test_move_daily_changes_the_date():
    current = digest.normalize({"daily": [{"date": "2026-07-27", "text": "遠出"}]})

    assert digest.move_daily(current, "2026-07-27", "2026-07-26")["daily"] == [{"date": "2026-07-26", "text": "遠出"}]


def test_parse_accepts_code_fenced_json():
    parsed = digest.parse('```json\n{"daily": [{"date": "2026-07-27", "text": "遠出"}]}\n```')

    assert parsed["daily"] == [{"date": "2026-07-27", "text": "遠出"}]
    assert parsed["monthly"] == []


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        digest.parse("再編できませんでした")


def test_render_lists_every_section():
    rendered = digest.render(
        digest.normalize(
            {
                "daily": [{"date": "2026-07-27", "text": "昼にラーメン"}],
                "monthly": [{"month": "2026-06", "summary": "遠出した月", "highlights": ["京都旅行"]}],
                "yearly": [{"year": "2025", "summary": "転職の年", "highlights": ["入社"]}],
            }
        )
    )

    assert "2026-07-27 昼にラーメン" in rendered
    assert "2026-06 遠出した月（京都旅行）" in rendered
    assert "2025 転職の年（入社）" in rendered


def test_render_without_records():
    assert "まだ記録がありません" in digest.render(digest.normalize(None))
