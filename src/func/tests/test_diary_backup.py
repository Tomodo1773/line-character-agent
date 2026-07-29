"""日記バックアップの Markdown 生成と、失敗時だけ通知する分岐のテスト。"""

import datetime

import pytest

import diary_backup
import line_client
from tests.conftest import DIARY_USER_ID

RUN_DATE = datetime.date(2026, 7, 28)

ENTRIES = [
    {"userId": "U-a", "date": "2026-07-26", "content": "  古い日記  "},
    {"userId": "U-b", "date": "2026-07-27", "content": "別の人の日記"},
    {"userId": "U-a", "date": "2026-07-27", "content": "新しい日記"},
]


@pytest.fixture
def uploads(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Cosmos DB と Blob Storage を差し替え、書き出された内容を集める。"""
    written: dict[str, str] = {}
    monkeypatch.setattr(diary_backup, "_fetch_entries", lambda: ENTRIES)
    monkeypatch.setattr(diary_backup, "_upload", written.__setitem__)
    return written


def test_writes_one_markdown_file_per_user(uploads):
    diary_backup.export(RUN_DATE)

    assert sorted(uploads) == ["2026-07-28/U-a.md", "2026-07-28/U-b.md"]


def test_markdown_lists_entries_newest_first():
    markdown = diary_backup.render_markdown("U-a", RUN_DATE, [ENTRIES[0], ENTRIES[2]])

    assert markdown == (
        "# 日記バックアップ (U-a)\n"
        "\n"
        "- 出力日: 2026-07-28（JST）\n"
        "- 件数: 2\n"
        "\n"
        "## 2026-07-27\n"
        "\n"
        "新しい日記\n"
        "\n"
        "## 2026-07-26\n"
        "\n"
        "古い日記\n"
    )


def test_does_not_notify_on_success(uploads, monkeypatch: pytest.MonkeyPatch):
    pushed = []
    monkeypatch.setattr(line_client, "push", lambda *args: pushed.append(args))

    diary_backup.diary_backup(timer=None)

    assert pushed == []


def test_notifies_the_owner_when_the_export_fails(monkeypatch: pytest.MonkeyPatch):
    def boom() -> list[dict]:
        raise RuntimeError("cosmos is down")

    pushed = []
    monkeypatch.setattr(diary_backup, "_fetch_entries", boom)
    monkeypatch.setattr(line_client, "push", lambda *args: pushed.append(args))

    with pytest.raises(RuntimeError):
        diary_backup.diary_backup(timer=None)

    assert pushed == [(DIARY_USER_ID, diary_backup.FAILURE_NOTICE)]
