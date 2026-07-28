"""依存性注入関数のテストモジュール。"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from chatbot.database.core import CosmosCore
from chatbot.database.repositories import UserRepository
from chatbot.dependencies import create_user_repository, get_user_repository


class TestGetUserRepository:
    """get_user_repository 関数のテスト。"""

    def test_get_user_repository_creates_repository_from_container(self):
        """app.state.users_container から UserRepository が生成されることを確認。"""
        # Arrange
        mock_container = MagicMock()
        mock_app = FastAPI()
        mock_app.state.users_container = mock_container

        mock_request = MagicMock()
        mock_request.app = mock_app

        # Act
        result = get_user_repository(mock_request)

        # Assert
        assert isinstance(result, UserRepository)
        assert isinstance(result._core, CosmosCore)


class TestCreateUserRepository:
    """create_user_repository 関数のテスト。"""

    def test_create_user_repository_with_container(self):
        """コンテナを渡すと UserRepository が生成されることを確認。"""
        # Arrange
        mock_container = MagicMock()

        # Act
        result = create_user_repository(container=mock_container)

        # Assert
        assert isinstance(result, UserRepository)
        assert isinstance(result._core, CosmosCore)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
