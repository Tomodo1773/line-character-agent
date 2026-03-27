"""FastAPI依存性注入の定義モジュール。

アプリケーション全体で共有するコンテナや各種リポジトリ、
OAuth マネージャーのインスタンスを提供します。
"""

from fastapi import Depends, Request

from chatbot.database.core import CosmosCore
from chatbot.database.repositories import UserRepository
from chatbot.utils.google_auth import GoogleDriveOAuthManager

# lifespan で初期化される users コンテナのキャッシュ
# agent ノードなど FastAPI DI が使えないコンテキスト向け
_users_container = None


def initialize_users_container(container) -> None:
    """lifespan から呼ばれ、グローバルキャッシュを初期化する。"""
    global _users_container
    _users_container = container


def get_user_repository(request: Request) -> UserRepository:
    """app.state.users_container から UserRepository を生成。

    Args:
        request: FastAPI の Request オブジェクト

    Returns:
        UserRepository: 新規作成された UserRepository インスタンス
    """
    container = request.app.state.users_container
    return UserRepository(CosmosCore(container))


def get_oauth_manager(user_repository: UserRepository = Depends(get_user_repository)) -> GoogleDriveOAuthManager:
    """UserRepository を使って GoogleDriveOAuthManager を生成。

    Args:
        user_repository: DI により注入される UserRepository

    Returns:
        GoogleDriveOAuthManager: 新規作成された GoogleDriveOAuthManager インスタンス
    """
    return GoogleDriveOAuthManager(user_repository)


def create_user_repository(container=None) -> UserRepository:
    """UserRepository を生成するヘルパー関数。

    webhook ハンドラや agent ノードなど FastAPI DI が使えないコンテキストで使用。

    Args:
        container: 初期化済みの Cosmos DB コンテナ。
                   None の場合は lifespan で初期化されたグローバルキャッシュを使用。

    Returns:
        UserRepository: 新規作成された UserRepository インスタンス
    """
    if container is None:
        if _users_container is None:
            raise RuntimeError("users_container not initialized. Call initialize_users_container() first.")
        container = _users_container
    return UserRepository(CosmosCore(container))
