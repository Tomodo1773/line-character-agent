"""日記ツールの振る舞いを確認する。

Cosmos DB と埋め込みの呼び出しは差し替え、ツールが「どのデータをどう書き換えるか」だけを見る。
"""

import datetime

import pytest

from character_agent import cosmos, foundry, tools


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    """Cosmos DB の代わりに使うメモリ上の保管庫。"""
    state = {"entries": [], "user": None, "created": [], "updated": [], "deleted": [], "moved": []}

    def find_entry(date: datetime.date):
        return next((entry for entry in state["entries"] if entry["date"] == date.isoformat()), None)

    def create_entry(date: datetime.date, content: str, content_vector: list[float]) -> None:
        state["created"].append({"date": date.isoformat(), "content": content, "contentVector": content_vector})

    monkeypatch.setattr(cosmos, "find_entry", find_entry)
    monkeypatch.setattr(cosmos, "create_entry", create_entry)
    monkeypatch.setattr(cosmos, "update_entry", lambda entry, content, vector: state["updated"].append((entry, content)))
    monkeypatch.setattr(cosmos, "move_entry", lambda entry, new_date: state["moved"].append((entry, new_date)))
    monkeypatch.setattr(cosmos, "delete_entry", lambda entry: state["deleted"].append(entry))
    monkeypatch.setattr(cosmos, "read_user", lambda: state["user"])
    monkeypatch.setattr(cosmos, "save_user", lambda user: state.update(user=user))
    monkeypatch.setattr(foundry, "embed", lambda text: [0.1, 0.2])
    return state


def test_diary_create_saves_entry_and_digest(store):
    result = tools.diary_create.func(date="2026-07-27", content="ラーメンを食べた。", summary="昼にラーメン")

    assert store["created"] == [{"date": "2026-07-27", "content": "ラーメンを食べた。", "contentVector": [0.1, 0.2]}]
    assert store["user"]["digest"]["daily"] == [{"date": "2026-07-27", "text": "昼にラーメン"}]
    # ユーザドキュメントの ID は Worker が書くものと揃える（LINE ユーザ ID）。
    assert store["user"]["id"] == "U-test"
    assert "登録しました" in result


def test_diary_create_refuses_when_entry_exists(store):
    store["entries"].append({"id": "1", "date": "2026-07-27", "userId": "U-test"})

    result = tools.diary_create.func(date="2026-07-27", content="本文", summary="要約")

    assert store["created"] == []
    assert "diary_update" in result


def test_diary_update_replaces_content_and_digest(store):
    store["entries"].append({"id": "1", "date": "2026-07-27", "userId": "U-test"})
    store["user"] = {"id": "U-test", "digest": {"daily": [{"date": "2026-07-27", "text": "古い要約"}]}}

    tools.diary_update.func(date="2026-07-27", content="追記後の全文", summary="新しい要約")

    assert store["updated"][0][1] == "追記後の全文"
    assert store["user"]["digest"]["daily"] == [{"date": "2026-07-27", "text": "新しい要約"}]


def test_diary_update_reports_missing_entry(store):
    result = tools.diary_update.func(date="2026-07-27", content="本文", summary="要約")

    assert store["updated"] == []
    assert "diary_create" in result


def test_diary_delete_removes_entry_and_digest(store):
    entry = {"id": "1", "date": "2026-07-27", "userId": "U-test"}
    store["entries"].append(entry)
    store["user"] = {"id": "U-test", "digest": {"daily": [{"date": "2026-07-27", "text": "要約"}]}}

    tools.diary_delete.func(date="2026-07-27")

    assert store["deleted"] == [entry]
    assert store["user"]["digest"]["daily"] == []


def test_diary_rename_moves_entry_and_digest(store):
    store["entries"].append({"id": "1", "date": "2026-07-27", "userId": "U-test"})
    store["user"] = {"id": "U-test", "digest": {"daily": [{"date": "2026-07-27", "text": "要約"}]}}

    tools.diary_rename.func(date="2026-07-27", new_date="2026-07-26")

    assert store["moved"][0][1] == datetime.date(2026, 7, 26)
    assert store["user"]["digest"]["daily"] == [{"date": "2026-07-26", "text": "要約"}]


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


def test_read_profile_returns_profile_and_digest(store):
    store["user"] = {
        "id": "U-test",
        "profile": "エンジニア。",
        "digest": {"daily": [{"date": "2026-07-27", "text": "昼にラーメン"}]},
    }

    result = tools.read_profile.func()

    assert "エンジニア。" in result
    assert "2026-07-27 昼にラーメン" in result


def test_read_profile_without_user_document(store):
    assert "未登録" in tools.read_profile.func()


def test_digest_regenerate_saves_model_output(monkeypatch: pytest.MonkeyPatch, store):
    store["user"] = {"id": "U-test", "digest": {"daily": [{"date": "2026-06-01", "text": "遠出"}]}}
    monkeypatch.setattr(
        foundry,
        "complete",
        lambda instructions, text: '```json\n{"monthly": [{"month": "2026-06", "summary": "遠出した月"}]}\n```',
    )

    tools.digest_regenerate.func()

    saved = store["user"]["digest"]
    assert saved["monthly"][0]["month"] == "2026-06"
    assert saved["daily"] == []
    assert saved["lastUpdated"] == datetime.datetime.now(tools.JAPAN).date().isoformat()
