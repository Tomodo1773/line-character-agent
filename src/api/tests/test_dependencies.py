"""依存性注入関数のテストモジュール。"""

from unittest.mock import MagicMock

import pytest
from azure.cosmos import CosmosClient
from fastapi import FastAPI

from chatbot.database.core import CosmosCore
from chatbot.database.repositories import UserRepository
from chatbot.dependencies import get_cosmos_client, get_oauth_manager, get_user_repository
from chatbot.utils.google_auth import GoogleDriveOAuthManager


class TestGetCosmosClient:
    """get_cosmos_client 関数のテスト。"""

    def test_get_cosmos_client_returns_client_from_app_state(self):
        """app.state.cosmos_client から CosmosClient が取得できることを確認。"""
        # Arrange
        mock_client = MagicMock(spec=CosmosClient)
        mock_app = FastAPI()
        mock_app.state.cosmos_client = mock_client

        mock_request = MagicMock()
        mock_request.app = mock_app

        # Act
        result = get_cosmos_client(mock_request)

        # Assert
        assert result is mock_client


class TestGetUserRepository:
    """get_user_repository 関数のテスト。"""

    def test_get_user_repository_creates_repository_with_cosmos_client(self):
        """CosmosClient から UserRepository が生成されることを確認。"""
        # Arrange
        mock_client = MagicMock(spec=CosmosClient)

        # Act
        result = get_user_repository(cosmos_client=mock_client)

        # Assert
        assert isinstance(result, UserRepository)
        assert isinstance(result._core, CosmosCore)


class TestGetOAuthManager:
    """get_oauth_manager 関数のテスト。"""

    def test_get_oauth_manager_creates_manager_with_user_repository(self, monkeypatch):
        """UserRepository から GoogleDriveOAuthManager が生成されることを確認。"""
        # Arrange
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/callback")

        mock_core = MagicMock(spec=CosmosCore)
        user_repository = UserRepository(mock_core)

        # Act
        result = get_oauth_manager(user_repository=user_repository)

        # Assert
        assert isinstance(result, GoogleDriveOAuthManager)
        assert result.user_repository is user_repository


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
