"""Cosmos DB への読み取りが、日記の持ち主のパーティションに閉じていることを確認する。"""

import pytest

from diary_admin import cosmos


class FakeContainer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def query_items(self, query, parameters, partition_key):
        self.calls.append({"operation": "query", "query": query, "parameters": parameters, "partition_key": partition_key})
        return []

    def read_item(self, item, partition_key):
        self.calls.append({"operation": "read", "item": item, "partition_key": partition_key})
        return {"id": item, "userId": partition_key}


@pytest.fixture
def container(monkeypatch: pytest.MonkeyPatch) -> FakeContainer:
    fake = FakeContainer()
    monkeypatch.setattr(cosmos, "_container", lambda: fake)
    return fake


def test_list_entries_queries_owner_partition(container: FakeContainer):
    cosmos.list_entries(None)

    call = container.calls[0]
    assert call["partition_key"] == "U-test"
    assert {"name": "@userId", "value": "U-test"} in call["parameters"]
    assert "c.userId = @userId" in call["query"]


def test_read_entry_reads_owner_partition(container: FakeContainer):
    cosmos.read_entry("entry-1")

    assert container.calls == [{"operation": "read", "item": "entry-1", "partition_key": "U-test"}]
