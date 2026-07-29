"""ダイジェストの組み立て（純粋な変換処理）を確認する。"""

import pytest

from character_agent import digest


def test_normalize_fills_missing_sections():
    assert digest.normalize(None) == {
        "version": digest.VERSION,
        "lastUpdated": "",
        "monthly": [],
        "yearly": [],
    }


def test_normalize_drops_daily_from_the_old_schema():
    """日次要約は日記ドキュメントへ移したので、旧スキーマの daily は読み捨てる。"""
    normalized = digest.normalize({"version": "2.0", "daily": [{"date": "2026-07-27", "text": "遠出"}]})

    assert "daily" not in normalized
    assert normalized["version"] == digest.VERSION


def test_parse_accepts_code_fenced_json():
    parsed = digest.parse('```json\n{"monthly": [{"month": "2026-06", "summary": "遠出した月"}]}\n```')

    assert parsed["monthly"] == [{"month": "2026-06", "summary": "遠出した月"}]
    assert parsed["yearly"] == []


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        digest.parse("再編できませんでした")


def test_validate_accepts_a_well_formed_digest():
    digest.validate(
        digest.normalize(
            {
                "monthly": [{"month": "2026-06", "summary": "遠出した月", "highlights": ["京都旅行"]}],
                "yearly": [{"year": "2025", "summary": "転職の年", "highlights": ["入社"]}],
            }
        )
    )


def test_validate_allows_missing_highlights():
    """highlights は無くてもよい。件数の指針は digest-rollup スキル側にある。"""
    digest.validate(digest.normalize({"monthly": [{"month": "2026-06", "summary": "遠出した月"}]}))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"monthly": [{"month": "2026年6月", "summary": "遠出"}]}, "YYYY-MM"),
        ({"monthly": [{"month": "2026-13", "summary": "遠出"}]}, "YYYY-MM"),
        ({"yearly": [{"year": "25", "summary": "転職"}]}, "YYYY"),
        ({"monthly": [{"month": "2026-06", "summary": "  "}]}, "summary"),
        ({"monthly": [{"month": "2026-06", "summary": "遠出", "highlights": "京都"}]}, "highlights"),
        ({"monthly": ["2026-06"]}, "オブジェクトではありません"),
        (
            {"monthly": [{"month": "2026-06", "summary": "遠出"}, {"month": "2026-06", "summary": "遠出"}]},
            "重複",
        ),
    ],
)
def test_validate_rejects_broken_entries(raw, message):
    with pytest.raises(ValueError, match=message):
        digest.validate(digest.normalize(raw))


def test_validate_rejects_a_month_already_rolled_up_into_a_year():
    """同じ期間を月次と年次の両方に持たない。年次へまとめた年の月次は消してから保存する。"""
    raw = {
        "monthly": [{"month": "2025-12", "summary": "師走"}],
        "yearly": [{"year": "2025", "summary": "転職の年"}],
    }

    with pytest.raises(ValueError, match="2025-12"):
        digest.validate(digest.normalize(raw))


def test_render_lists_daily_summaries_and_every_section():
    rendered = digest.render(
        digest.normalize(
            {
                "monthly": [{"month": "2026-06", "summary": "遠出した月", "highlights": ["京都旅行"]}],
                "yearly": [{"year": "2025", "summary": "転職の年", "highlights": ["入社"]}],
            }
        ),
        [{"date": "2026-07-27", "summary": "昼にラーメン"}],
    )

    assert "2026-07-27 昼にラーメン" in rendered
    assert "2026-06 遠出した月（京都旅行）" in rendered
    assert "2025 転職の年（入社）" in rendered


def test_render_without_records():
    assert "まだ記録がありません" in digest.render(digest.normalize(None), [])
