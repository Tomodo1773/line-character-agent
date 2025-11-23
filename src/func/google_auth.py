import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from logger import logger

# Functions 側は Drive の読み取りのみを行うため、Docs API 専用スコープは不要。
# リフレッシュトークン発行時に承認されたスコープと一致させておくことで
# refresh 時の invalid_scope を防ぐ。
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_env_variable(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise ValueError(f"Environment variable {name} is not set")
    return value


def _get_connection_verify():
    verify_setting = os.getenv("COSMOS_DB_CONNECTION_VERIFY")
    if verify_setting is None:
        return True

    lowered = verify_setting.lower()
    if lowered in {"false", "0", "no"}:
        return False
    if lowered in {"true", "1", "yes"}:
        return True
    return verify_setting


def _get_cosmos_client() -> CosmosClient:
    return CosmosClient(
        url=get_env_variable("COSMOS_DB_ACCOUNT_URL"),
        credential=get_env_variable("COSMOS_DB_ACCOUNT_KEY"),
        connection_verify=_get_connection_verify(),
    )


def _get_fernet() -> Fernet:
    key = get_env_variable("GOOGLE_TOKEN_ENC_KEY")
    return Fernet(key.encode("utf-8"))


def encrypt_dict(data: Dict[str, Any]) -> str:
    fernet = _get_fernet()
    payload = json.dumps(data).encode("utf-8")
    return fernet.encrypt(payload).decode("utf-8")


def decrypt_dict(token: str) -> Dict[str, Any]:
    if not token:
        return {}

    fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(token.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError) as error:
        logger.error("Failed to decrypt google token: %s", error)
        return {}


def credentials_to_dict(credentials: Credentials) -> Dict[str, Any]:
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }


def credentials_from_dict(token_data: Dict[str, Any]) -> Optional[Credentials]:
    if not token_data:
        return None

    expiry = token_data.get("expiry")
    expiry_dt = datetime.fromisoformat(expiry) if expiry else None

    return Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=get_env_variable("GOOGLE_CLIENT_ID"),
        client_secret=get_env_variable("GOOGLE_CLIENT_SECRET"),
        scopes=GOOGLE_SCOPES,
        expiry=expiry_dt,
    )


class UserTokenRepository:
    def __init__(self):
        self.client = _get_cosmos_client()
        self.database = self.client.get_database_client("main")
        self.container = self.database.get_container_client("users")

    @staticmethod
    def _sanitize_item(item: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in item.items() if not k.startswith("_") and k != "date"}

    def fetch_all_tokens(self) -> List[Dict[str, Any]]:
        query = "SELECT c.id, c.userid, c.google_tokens_enc FROM c WHERE IS_DEFINED(c.google_tokens_enc)"
        return list(self.container.query_items(query=query, enable_cross_partition_query=True))

    def fetch_user(self, userid: str) -> Dict[str, Any]:
        try:
            item = self.container.read_item(item=userid, partition_key=userid)
            return self._sanitize_item(item)
        except CosmosResourceNotFoundError:
            return {}

    def save_google_tokens(self, userid: str, tokens: Dict[str, Any]) -> None:
        encrypted = encrypt_dict(tokens)
        existing = self.fetch_user(userid)
        sanitized_existing = self._sanitize_item(existing)
        data = {**sanitized_existing, "id": userid, "userid": sanitized_existing.get("userid", userid)}
        data["google_tokens_enc"] = encrypted
        self.container.upsert_item(data)


class GoogleUserTokenManager:
    def __init__(self, repository: Optional[UserTokenRepository] = None):
        self.repository = repository or UserTokenRepository()

    def get_all_user_credentials(self) -> List[Tuple[str, Credentials]]:
        credentials_list: List[Tuple[str, Credentials]] = []
        user_records = self.repository.fetch_all_tokens()

        for record in user_records:
            userid = record.get("userid") or record.get("id")
            if not userid:
                logger.warning("Skipping user record without userid")
                continue

            token_data = decrypt_dict(record.get("google_tokens_enc", ""))
            credentials = credentials_from_dict(token_data)

            if not credentials:
                logger.warning("Skipping user %s due to missing credentials", userid)
                continue

            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    self.repository.save_google_tokens(userid, credentials_to_dict(credentials))
                    logger.info("Refreshed Google token for user: %s", userid)
                except Exception as error:
                    logger.error("Failed to refresh Google token for user %s: %s", userid, error)
                    continue

            credentials_list.append((userid, credentials))

        return credentials_list
