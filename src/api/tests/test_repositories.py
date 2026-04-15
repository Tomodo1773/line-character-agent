"""OAuthStateRepository のテストモジュール。"""

from unittest.mock import MagicMock

import pytest

from chatbot.database.repositories import OAuthStateRepository


class TestOAuthStateRepository:
    """state のワンタイム消費と、ユーザーID/code_verifier の対称性を検証する。"""

    def test_save_state_and_consume_state_returns_saved_values(self):
        """save_state で保存した userid と code_verifier が consume_state で取り出せる。"""
        mock_core = MagicMock()
        repo = OAuthStateRepository(mock_core)

        # 擬似ストレージ
        storage: dict = {}
        mock_core.save.side_effect = lambda data: storage.update({data["id"]: data})
        mock_core.fetch.side_effect = lambda query, params: (
            [storage[params[0]["value"]]] if params[0]["value"] in storage else []
        )
        mock_core.delete.side_effect = lambda item_id, pk: storage.pop(item_id, None)

        repo.save_state("random-state-abc", "U1234", "verifier-xyz")
        result = repo.consume_state("random-state-abc")

        assert result == {"userid": "U1234", "code_verifier": "verifier-xyz"}

    def test_consume_state_is_one_shot(self):
        """consume_state は1回目で値を返し、2回目は None を返す（ワンタイム）。"""
        mock_core = MagicMock()
        repo = OAuthStateRepository(mock_core)

        storage: dict = {}
        mock_core.save.side_effect = lambda data: storage.update({data["id"]: data})
        mock_core.fetch.side_effect = lambda query, params: (
            [storage[params[0]["value"]]] if params[0]["value"] in storage else []
        )
        mock_core.delete.side_effect = lambda item_id, pk: storage.pop(item_id, None)

        repo.save_state("one-shot-state", "U1234", "verifier")
        first = repo.consume_state("one-shot-state")
        second = repo.consume_state("one-shot-state")

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

    def test_save_state_rejects_empty_values(self):
        """state / userid / code_verifier が空なら ValueError を投げる。"""
        mock_core = MagicMock()
        repo = OAuthStateRepository(mock_core)

        with pytest.raises(ValueError):
            repo.save_state("", "U1234", "verifier")
        with pytest.raises(ValueError):
            repo.save_state("state", "", "verifier")
        with pytest.raises(ValueError):
            repo.save_state("state", "U1234", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
