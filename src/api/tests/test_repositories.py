"""OAuthStateRepository のテストモジュール。"""

from unittest.mock import MagicMock

import pytest

from chatbot.database.repositories import OAuthStateRepository


@pytest.fixture
def repo_with_fake_storage():
    """擬似ストレージに差し替えた OAuthStateRepository を返す。"""
    mock_core = MagicMock()
    storage: dict = {}
    mock_core.save.side_effect = lambda data: storage.update({data["id"]: data})
    mock_core.fetch.side_effect = lambda query, params: [storage[params[0]["value"]]] if params[0]["value"] in storage else []
    mock_core.delete.side_effect = lambda item_id, pk: storage.pop(item_id, None)
    return OAuthStateRepository(mock_core)


class TestOAuthStateRepository:
    """state のワンタイム消費と、ユーザーID/code_verifier の対称性を検証する。"""

    def test_save_state_and_consume_state_returns_saved_values(self, repo_with_fake_storage):
        """save_state で保存した userid と code_verifier が consume_state で取り出せる。"""
        repo_with_fake_storage.save_state("random-state-abc", "U1234", "verifier-xyz")
        result = repo_with_fake_storage.consume_state("random-state-abc")

        assert result == {"userid": "U1234", "code_verifier": "verifier-xyz"}

    def test_consume_state_is_one_shot(self, repo_with_fake_storage):
        """consume_state は1回目で値を返し、2回目は None を返す（ワンタイム）。"""
        repo_with_fake_storage.save_state("one-shot-state", "U1234", "verifier")
        first = repo_with_fake_storage.consume_state("one-shot-state")
        second = repo_with_fake_storage.consume_state("one-shot-state")

        assert first == {"userid": "U1234", "code_verifier": "verifier"}
        assert second is None

    def test_consume_unknown_state_returns_none(self):
        """未知の state を渡すと None が返る。"""
        mock_core = MagicMock()
        mock_core.fetch.return_value = []
        repo = OAuthStateRepository(mock_core)

        result = repo.consume_state("unknown-state")

        assert result is None
        mock_core.delete.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
