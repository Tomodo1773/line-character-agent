"""agent tools モジュールのテスト。"""

from unittest.mock import MagicMock

import pytest
from azure.cosmos import CosmosClient

import chatbot.agent.tools as agent_tools
from chatbot.agent.tools import get_cosmos_client, initialize_cosmos_client


class TestInitializeCosmosClient:
    """initialize_cosmos_client 関数のテスト。"""

    def test_initialize_cosmos_client_sets_global_client(self):
        """initialize_cosmos_client が グローバル変数を設定することを確認。"""
        # Arrange
        mock_client = MagicMock(spec=CosmosClient)

        # Act
        initialize_cosmos_client(mock_client)

        # Assert - get_cosmos_client() で取得できることを確認
        result = get_cosmos_client()
        assert result is mock_client


class TestGetCosmosClient:
    """get_cosmos_client 関数のテスト。"""

    def test_get_cosmos_client_returns_initialized_client(self):
        """初期化済みの CosmosClient を返すことを確認。"""
        # Arrange
        mock_client = MagicMock(spec=CosmosClient)
        initialize_cosmos_client(mock_client)

        # Act
        result = get_cosmos_client()

        # Assert
        assert result is mock_client

    def test_get_cosmos_client_raises_runtime_error_when_not_initialized(self):
        """未初期化時に RuntimeError を発生させることを確認。"""
        # Arrange - グローバル変数をリセット
        agent_tools._cosmos_client = None

        # Act & Assert
        with pytest.raises(RuntimeError) as exc_info:
            get_cosmos_client()

        assert "CosmosClient not initialized" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
