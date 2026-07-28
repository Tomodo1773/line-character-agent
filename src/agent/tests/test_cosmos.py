"""検索クエリの組み立てを確認する。

クエリ文字列を直接組み立てている箇所なので、条件とキーワードの埋め込みだけを見る。
Cosmos DB への接続は行わない。
"""

import pytest

from character_agent import cosmos


class FakeContainer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def query_items(self, query, parameters, partition_key):
        self.calls.append({"query": query, "parameters": parameters, "partition_key": partition_key})
        return []


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
