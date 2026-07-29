"""Cosmos DB へのクエリと書き込みの組み立てを確認する。

クエリ文字列を直接組み立てている箇所と、書き込みを PATCH に閉じている箇所だけを見る。
Cosmos DB への接続は行わない。
"""

import pytest
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError

from character_agent import cosmos


class FakeContainer:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.items: list[dict] = []
        self.patched: list[dict] = []
        self.created: list[dict] = []
        # 例外クラスを入れておくと、その回の呼び出しだけ失敗させられる。
        self.patch_error: type[Exception] | None = None
        self.create_error: type[Exception] | None = None

    def query_items(self, query, parameters, partition_key):
        self.calls.append({"query": query, "parameters": parameters, "partition_key": partition_key})
        return self.items

    def patch_item(self, item, partition_key, patch_operations):
        if self.patch_error:
            error, self.patch_error = self.patch_error, None
            raise error(message="patch failed", response=None)
        self.patched.append({"item": item, "partition_key": partition_key, "operations": patch_operations})

    def create_item(self, body):
        if self.create_error:
            error, self.create_error = self.create_error, None
            raise error(message="create failed", response=None)
        self.created.append(body)


@pytest.fixture
def container(monkeypatch: pytest.MonkeyPatch) -> FakeContainer:
    fake = FakeContainer()
    monkeypatch.setattr(cosmos, "_container", lambda database, container: fake)
    return fake


def _parameter(call: dict, name: str):
    return next((item["value"] for item in call["parameters"] if item["name"] == name), None)


def test_hybrid_search_uses_rrf_with_keywords_and_date_filter(container: FakeContainer):
    cosmos.search_entries([0.1, 0.2], ["ラーメン", "昼食"], top_k=5, start_date="2026-07-01", end_date="2026-07-31")

    call = container.calls[0]
    assert "RANK RRF" in call["query"]
    assert 'FullTextScore(c.content, "ラーメン", "昼食")' in call["query"]
    assert "c.date >= @startDate" in call["query"] and "c.date <= @endDate" in call["query"]
    assert _parameter(call, "@vector") == [0.1, 0.2]
    # 検索は必ず持ち主のパーティションに閉じる。
    assert call["partition_key"] == "U-test"
    assert _parameter(call, "@userId") == "U-test"


def test_search_without_keywords_lists_newest_first(container: FakeContainer):
    cosmos.search_entries(None, [], top_k=3, start_date="2026-07-27", end_date="2026-07-27")

    call = container.calls[0]
    assert "ORDER BY c.date DESC" in call["query"]
    assert "SELECT TOP 3" in call["query"]
    assert _parameter(call, "@vector") is None


def test_keywords_cannot_break_out_of_the_query(container: FakeContainer):
    cosmos.search_entries([0.1], ['ラー"メン'], top_k=1)

    assert 'FullTextScore(c.content, "ラーメン")' in container.calls[0]["query"]


def test_list_summaries_reads_only_the_summary_field(container: FakeContainer):
    """日次要約は日記ドキュメントから読む。本文と埋め込みベクトルは取り出さない。"""
    container.items = [{"date": "2026-07-27", "summary": "昼にラーメン"}, {"date": "2026-07-26", "summary": "散歩"}]

    result = cosmos.list_summaries(30, end_date="2026-07-31")

    call = container.calls[0]
    assert "SELECT TOP 30 c.date, c.summary" in call["query"]
    assert "IS_DEFINED(c.summary)" in call["query"]
    assert "c.date <= @endDate" in call["query"]
    assert _parameter(call, "@endDate") == "2026-07-31"
    assert call["partition_key"] == "U-test"
    # 新しい順に取ってから、読みやすいように古い順へ並べ替えて返す。
    assert [item["date"] for item in result] == ["2026-07-26", "2026-07-27"]


def test_save_digest_patches_only_the_digest_field(container: FakeContainer):
    """conversation_id を書く Function と衝突しないよう、担当フィールドだけを PATCH する。"""
    cosmos.save_digest({"version": "3.0", "monthly": []})

    assert container.created == []
    assert container.patched == [
        {
            "item": "U-test",
            "partition_key": "U-test",
            "operations": [{"op": "set", "path": "/digest", "value": {"version": "3.0", "monthly": []}}],
        }
    ]


def test_save_digest_creates_the_document_on_the_first_write(container: FakeContainer):
    container.patch_error = CosmosResourceNotFoundError

    cosmos.save_digest({"version": "3.0"})

    assert container.created == [{"id": "U-test", "userid": "U-test", "digest": {"version": "3.0"}}]
    assert container.patched == []


def test_save_digest_retries_with_patch_when_creation_races(container: FakeContainer):
    """初回作成が別の書き込みと競合したら、PATCH でやり直して相手の書き込みを消さない。"""
    container.patch_error = CosmosResourceNotFoundError
    container.create_error = CosmosResourceExistsError

    cosmos.save_digest({"version": "3.0"})

    assert container.created == []
    assert container.patched[0]["operations"][0]["path"] == "/digest"
