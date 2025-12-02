from datetime import datetime
from typing import Dict, Optional, Tuple

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from chatbot.database.repositories import UserRepository
from chatbot.utils.config import create_logger, get_env_variable
from chatbot.utils.google_drive import GoogleDriveHandler

logger = create_logger(__name__)


class GoogleDriveOAuthManager:
    """Google DriveのOAuth認可と資格情報管理を行うクラス"""

    def __init__(self, user_repository: Optional[UserRepository] = None):
        self.user_repository = user_repository or UserRepository()
        self.client_id = get_env_variable("GOOGLE_CLIENT_ID")
        self.client_secret = get_env_variable("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = get_env_variable("GOOGLE_OAUTH_REDIRECT_URI")

    def _client_config(self) -> Dict:
        return {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.redirect_uri],
            }
        }

    def generate_authorization_url(self, state: str) -> Tuple[str, str]:
        flow = Flow.from_client_config(self._client_config(), scopes=GoogleDriveHandler.SCOPES, redirect_uri=self.redirect_uri)
        auth_url, flow_state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent", state=state
        )
        logger.info("Generated Google OAuth authorization URL")
        return auth_url, flow_state

    def exchange_code_for_credentials(self, code: str) -> Credentials:
        flow = Flow.from_client_config(self._client_config(), scopes=GoogleDriveHandler.SCOPES, redirect_uri=self.redirect_uri)
        flow.fetch_token(code=code)
        logger.info("Exchanged authorization code for credentials")
        return flow.credentials

    @staticmethod
    def credentials_to_dict(credentials: Credentials) -> Dict:
        return {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }

    @staticmethod
    def credentials_from_dict(token_data: Dict) -> Optional[Credentials]:
        if not token_data:
            return None

        expiry = token_data.get("expiry")
        expiry_dt = datetime.fromisoformat(expiry) if expiry else None

        client_id = get_env_variable("GOOGLE_CLIENT_ID")
        client_secret = get_env_variable("GOOGLE_CLIENT_SECRET")

        return Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=client_id,
            client_secret=client_secret,
            scopes=GoogleDriveHandler.SCOPES,
            expiry=expiry_dt,
        )

    def save_user_credentials(self, userid: str, credentials: Credentials) -> None:
        self.user_repository.save_google_tokens(userid, self.credentials_to_dict(credentials))
        logger.info("Saved Google Drive credentials for user: %s", userid)

    def get_user_credentials(self, userid: str) -> Optional[Credentials]:
        """
        ユーザーの資格情報を取得する。

        - 有効な資格情報が無い場合は None を返す。
        - アクセストークン期限切れかつリフレッシュトークンがある場合は refresh を行う。
        - リフレッシュトークンが期限切れ・無効（RefreshError）の場合はトークンを削除し、None を返す。
        """
        token_data = self.user_repository.fetch_google_tokens(userid)
        credentials = self.credentials_from_dict(token_data)
        if not credentials:
            return None

        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self.save_user_credentials(userid, credentials)
            except RefreshError as error:
                logger.warning(
                    "Google token refresh failed for user %s due to RefreshError (likely expired or revoked). "
                    "Clearing stored tokens. error=%s",
                    userid,
                    error,
                )
                # リフレッシュトークン失効とみなしてトークンをクリアし、再認可を促す
                self.user_repository.clear_google_tokens(userid)
                return None
            except Exception as error:  # ネットワークエラー等
                logger.error("Unexpected error while refreshing Google token for user %s: %s", userid, error)
                return None

        return credentials
