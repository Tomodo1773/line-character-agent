"""日記ツールの振る舞いを確認する。

Cosmos DB と埋め込みの呼び出しは差し替え、ツールが「どのデータをどう書き換えるか」だけを見る。
"""

import datetime
import json

import pytest

from character_agent import cosmos, foundry, tools


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    """Cosmos DB の代わりに使うメモリ上の保管庫。"""
    state = {
        "entries": [],
        "user": None,
        "digest": None,
        "summaries": [],
        "created": [],
        "updated": [],
        "deleted": [],
        "moved": [],
    }

    def find_entry(date: datetime.date):
        return next((entry for entry in state["entries"] if entry["date"] == date.isoformat()), None)

    def create_entry(date: datetime.date, content: str, content_vector: list[float], summary: str) -> None:
        state["created"].append(
            {"date": date.isoformat(), "content": content, "contentVector": content_vector, "summary": summary}
        )

    def list_summaries(top_k: int, end_date: str | None = None):
        items = [item for item in state["summaries"] if end_date is None or item["date"] <= end_date]
        return items[:top_k]

    monkeypatch.setattr(cosmos, "find_entry", find_entry)
    monkeypatch.setattr(cosmos, "create_entry", create_entry)
    monkeypatch.setattr(
        cosmos, "update_entry", lambda entry, content, vector, summary: state["updated"].append((entry, content, summary))
    )
    monkeypatch.setattr(cosmos, "move_entry", lambda entry, new_date: state["moved"].append((entry, new_date)))
    monkeypatch.setattr(cosmos, "delete_entry", lambda entry: state["deleted"].append(entry))
    monkeypatch.setattr(cosmos, "list_summaries", list_summaries)
    monkeypatch.setattr(cosmos, "read_user", lambda: state["user"])
    monkeypatch.setattr(cosmos, "save_digest", lambda digest: state.update(digest=digest))
    monkeypatch.setattr(foundry, "embed", lambda text: [0.1, 0.2])
    return state


def test_diary_create_saves_content_vector_and_summary_in_one_document(store):
    """本文・埋め込み・日次要約が同じ日記ドキュメントへ 1 回の書き込みで入る。"""
    result = tools.diary_create.func(date="2026-07-27", content="ラーメンを食べた。", summary="昼にラーメン")

    assert store["created"] == [
        {
            "date": "2026-07-27",
            "content": "ラーメンを食べた。",
            "contentVector": [0.1, 0.2],
            "summary": "昼にラーメン",
        }
    ]
    # ユーザドキュメントには何も書かない（二段書き込みをしない）。
    assert store["digest"] is None
    assert "登録しました" in result


def test_diary_create_refuses_when_entry_exists(store):
    store["entries"].append({"id": "1", "date": "2026-07-27", "userId": "U-test"})

    result = tools.diary_create.func(date="2026-07-27", content="本文", summary="要約")

    assert store["created"] == []
    assert "既に日記があるため" in result
    assert "diary_update" in result


def test_diary_update_replaces_content_and_summary(store):
    store["entries"].append({"id": "1", "date": "2026-07-27", "userId": "U-test", "summary": "古い要約"})

    tools.diary_update.func(date="2026-07-27", content="追記後の全文", summary="新しい要約")

    assert store["updated"][0][1] == "追記後の全文"
    assert store["updated"][0][2] == "新しい要約"
    assert store["digest"] is None


def test_diary_update_reports_missing_entry(store):
    result = tools.diary_update.func(date="2026-07-27", content="本文", summary="要約")

    assert store["updated"] == []
    assert "diary_create" in result


def test_diary_delete_removes_the_entry_with_its_summary(store):
    entry = {"id": "1", "date": "2026-07-27", "userId": "U-test", "summary": "要約"}
    store["entries"].append(entry)

    tools.diary_delete.func(date="2026-07-27")

    assert store["deleted"] == [entry]
    assert store["digest"] is None


def test_diary_rename_moves_the_entry(store):
    store["entries"].append({"id": "1", "date": "2026-07-27", "userId": "U-test", "summary": "要約"})

    tools.diary_rename.func(date="2026-07-27", new_date="2026-07-26")

    assert store["moved"][0][1] == datetime.date(2026, 7, 26)
    assert store["digest"] is None


def test_diary_rename_refuses_when_destination_is_taken(store):
    store["entries"] += [
        {"id": "1", "date": "2026-07-27", "userId": "U-test"},
        {"id": "2", "date": "2026-07-26", "userId": "U-test"},
    ]

    result = tools.diary_rename.func(date="2026-07-27", new_date="2026-07-26")

    assert store["moved"] == []
    assert "既に日記があるため" in result


def test_invalid_date_is_rejected(store):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        tools.diary_delete.func(date="2026/07/27")


def test_diary_search_embeds_only_when_query_text_is_given(monkeypatch: pytest.MonkeyPatch, store):
    calls = []
    monkeypatch.setattr(
        cosmos,
        "search_entries",
        lambda **kwargs: calls.append(kwargs) or [{"date": "2026-07-27", "content": "ラーメンを食べた。"}],
    )

    assert "ラーメン" in tools.diary_search.func(query_text="ラーメン 昼食", top_k=3)
    assert calls[0]["keywords"] == ["ラーメン", "昼食"]
    assert calls[0]["content_vector"] == [0.1, 0.2]

    tools.diary_search.func(start_date="2026-07-27", end_date="2026-07-27")
    assert calls[1]["keywords"] == []
    assert calls[1]["content_vector"] is None


def test_diary_search_clamps_top_k(monkeypatch: pytest.MonkeyPatch, store):
    calls = []
    monkeypatch.setattr(cosmos, "search_entries", lambda **kwargs: calls.append(kwargs) or [])

    tools.diary_search.func(query_text="散歩", top_k=100)

    assert calls[0]["top_k"] == tools.MAX_SEARCH_RESULTS


def test_read_profile_reads_daily_summaries_from_diary_entries(store):
    """日次要約は users ではなく日記ドキュメントから取る。"""
    store["user"] = {
        "id": "U-test",
        "profile": "エンジニア。",
        "digest": {"monthly": [{"month": "2026-06", "summary": "遠出した月", "highlights": ["京都旅行"]}]},
    }
    store["summaries"] = [{"date": "2026-07-27", "summary": "昼にラーメン"}]

    result = tools.read_profile.func()

    assert "エンジニア。" in result
    assert "2026-07-27 昼にラーメン" in result
    assert "2026-06 遠出した月（京都旅行）" in result


def test_read_profile_without_user_document(store):
    assert "未登録" in tools.read_profile.func()


def test_digest_read_returns_the_previous_month_as_material(store):
    """既定の対象月は前月。当月はまだ日が残っているので集約対象にしない。"""
    store["user"] = {"id": "U-test", "digest": {"monthly": [{"month": "2026-05", "summary": "五月"}]}}
    store["summaries"] = [{"date": "2026-06-01", "summary": "遠出"}]

    material = json.loads(tools.digest_read.func())

    today = datetime.datetime.now(tools.JAPAN).date()
    assert material["targetMonth"] == (today.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    assert material["today"] == today.isoformat()
    assert material["digest"]["monthly"] == [{"month": "2026-05", "summary": "五月"}]


def test_digest_read_keeps_only_the_target_month(monkeypatch: pytest.MonkeyPatch, store):
    """対象月の外へはみ出した日次要約は落とす。読むのは日次要約だけで、日記本文は読み直さない。"""
    store["summaries"] = [
        {"date": "2026-05-31", "summary": "前の月"},
        {"date": "2026-06-01", "summary": "遠出"},
        {"date": "2026-06-30", "summary": "月末"},
    ]
    ends = []
    monkeypatch.setattr(
        cosmos,
        "list_summaries",
        lambda top_k, end_date=None: (
            ends.append(end_date) or [item for item in store["summaries"] if item["date"] <= end_date][:top_k]
        ),
    )

    material = json.loads(tools.digest_read.func(month="2026-06"))

    assert ends == ["2026-06-30"]
    assert [item["date"] for item in material["dailySummaries"]] == ["2026-06-01", "2026-06-30"]


def test_digest_read_rejects_a_malformed_month(store):
    with pytest.raises(ValueError, match="YYYY-MM"):
        tools.digest_read.func(month="2026/06")


def test_digest_save_stores_what_the_agent_built(store):
    """ツールは検証と保存だけを担う。要約の文面はエージェントが組み立てて渡す。"""
    tools.digest_save.func(
        digest_json='```json\n{"monthly": [{"month": "2026-06", "summary": "遠出した月", "highlights": ["京都"]}], '
        '"yearly": []}\n```'
    )

    saved = store["digest"]
    assert saved["monthly"] == [{"month": "2026-06", "summary": "遠出した月", "highlights": ["京都"]}]
    assert "daily" not in saved
    assert saved["lastUpdated"] == datetime.datetime.now(tools.JAPAN).date().isoformat()


def test_digest_save_rejects_a_broken_structure(store):
    """崩れた形は Cosmos DB へ書く前に弾く。例外の文言はそのままモデルへ返る。"""
    with pytest.raises(ValueError, match="YYYY-MM"):
        tools.digest_save.func(digest_json='{"monthly": [{"month": "2026年6月", "summary": "遠出"}], "yearly": []}')

    assert store["digest"] is None


def test_digest_tools_never_call_a_generative_model(store):
    """ダイジェスト集約でツールの内側からモデルを呼ばない（`foundry.complete` は廃止済み）。"""
    assert not hasattr(foundry, "complete")
