"""`users` ドキュメントの書き込みが会話 ID だけに閉じていることを確認する。

同じドキュメントの `profile` と `digest` は Agent 側が書くため、Function がドキュメント全体を
upsert すると Agent の書き込みを巻き戻してしまう。Cosmos DB への接続は行わない。
"""

import pytest
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError

import users


class FakeContainer:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.patched: list[dict] = []
        self.created: list[dict] = []
        self.upserted: list[dict] = []
        # 例外クラスを入れておくと、その回の呼び出しだけ失敗させられる。
        self.patch_error: type[Exception] | None = None
        self.create_error: type[Exception] | None = None

    def read_item(self, item, partition_key):
        if item not in self.documents:
            raise CosmosResourceNotFoundError(message="not found", response=None)
        return self.documents[item]

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

    def upsert_item(self, body):
        self.upserted.append(body)


@pytest.fixture
def container(monkeypatch: pytest.MonkeyPatch) -> FakeContainer:
    fake = FakeContainer()
    monkeypatch.setattr(users, "_container", lambda: fake)
    return fake


def test_get_conversation_id_returns_none_without_document(container: FakeContainer):
    assert users.get_conversation_id("U-owner") is None


def test_get_conversation_id_reads_the_stored_value(container: FakeContainer):
    container.documents["U-owner"] = {"id": "U-owner", "conversation_id": "conv-1"}

    assert users.get_conversation_id("U-owner") == "conv-1"


def test_save_conversation_id_patches_only_that_field(container: FakeContainer):
    """profile や digest を巻き戻さないよう、担当フィールドだけを PATCH する。"""
    users.save_conversation_id("U-owner", "conv-1")

    assert container.upserted == []
    assert container.created == []
    assert container.patched == [
        {
            "item": "U-owner",
            "partition_key": "U-owner",
            "operations": [{"op": "set", "path": "/conversation_id", "value": "conv-1"}],
        }
    ]


def test_save_conversation_id_creates_the_document_on_the_first_write(container: FakeContainer):
    container.patch_error = CosmosResourceNotFoundError

    users.save_conversation_id("U-owner", "conv-1")

    assert container.created == [{"id": "U-owner", "userid": "U-owner", "conversation_id": "conv-1"}]
    assert container.patched == []


def test_save_conversation_id_retries_with_patch_when_creation_races(container: FakeContainer):
    """初回作成が Agent の書き込みと競合したら、PATCH でやり直して相手の書き込みを消さない。"""
    container.patch_error = CosmosResourceNotFoundError
    container.create_error = CosmosResourceExistsError

    users.save_conversation_id("U-owner", "conv-1")

    assert container.created == []
    assert container.patched[0]["operations"][0]["path"] == "/conversation_id"
