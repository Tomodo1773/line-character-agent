"""FastAPI依存性注入の定義モジュール。

アプリケーション全体で共有するコンテナやリポジトリのインスタンスを提供します。
"""

from azure.cosmos import ContainerProxy
from fastapi import Request

from chatbot.database.core import CosmosCore
from chatbot.database.repositories import UserRepository


def get_user_repository(request: Request) -> UserRepository:
    """app.state.users_container から UserRepository を生成。

    Args:
        request: FastAPI の Request オブジェクト

    Returns:
        UserRepository: 新規作成された UserRepository インスタンス
    """
    container = request.app.state.users_container
    return UserRepository(CosmosCore(container))


def create_user_repository(container: ContainerProxy) -> UserRepository:
    """UserRepository を生成するヘルパー関数。

    webhook ハンドラなど FastAPI DI が使えないコンテキストで使用。

    Args:
        container: 初期化済みの Cosmos DB コンテナ。

    Returns:
        UserRepository: 新規作成された UserRepository インスタンス
    """
    return UserRepository(CosmosCore(container))
