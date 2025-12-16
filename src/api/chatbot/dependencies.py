"""FastAPI依存性注入の定義モジュール。

アプリケーション全体で共有する CosmosClient や各種リポジトリ、
OAuth マネージャーのインスタンスを提供します。
"""

from fastapi import Depends, Request

from chatbot.database.core import CosmosCore
from chatbot.database.repositories import UserRepository
from chatbot.utils.google_auth import GoogleDriveOAuthManager


def get_cosmos_client(request: Request):
    """アプリケーションスコープの CosmosClient を取得。

    app.state.cosmos_client から共有インスタンスを取得します。
    lifespan 関数で初期化済みであることが前提です。

    Args:
        request: FastAPI の Request オブジェクト

    Returns:
        CosmosClient: 共有 CosmosClient インスタンス

    Raises:
        AttributeError: cosmos_client が初期化されていない場合
    """
    return request.app.state.cosmos_client


def get_user_repository(cosmos_client=Depends(get_cosmos_client)) -> UserRepository:
    """CosmosClient を使って UserRepository を生成。

    CosmosClient は DI により注入され、リクエストごとに新しい
    UserRepository インスタンスが作成されます。

    Args:
        cosmos_client: DI により注入される CosmosClient

    Returns:
        UserRepository: 新規作成された UserRepository インスタンス
    """
    cosmos_core = CosmosCore(cosmos_client, "users")
    return UserRepository(cosmos_core)


def get_oauth_manager(user_repository: UserRepository = Depends(get_user_repository)) -> GoogleDriveOAuthManager:
    """UserRepository を使って GoogleDriveOAuthManager を生成。

    UserRepository は DI により注入され、リクエストごとに新しい
    GoogleDriveOAuthManager インスタンスが作成されます。

    Args:
        user_repository: DI により注入される UserRepository

    Returns:
        GoogleDriveOAuthManager: 新規作成された GoogleDriveOAuthManager インスタンス
    """
    return GoogleDriveOAuthManager(user_repository)
