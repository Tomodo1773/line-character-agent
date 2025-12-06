import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz

from chatbot.utils.crypto import decrypt_dict, encrypt_dict

from .core import CosmosCore
from .interfaces import BaseRepository
from .models import SessionMetadata


class UserRepository(BaseRepository):
    SESSION_TTL = timedelta(hours=1)
    TIMEZONE = pytz.timezone("Asia/Tokyo")

    def __init__(self):
        self._core = CosmosCore("users")

    @staticmethod
    def _sanitize_item(item: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(item)
        sanitized.pop("date", None)
        sanitized.pop("_rid", None)
        sanitized.pop("_self", None)
        sanitized.pop("_etag", None)
        sanitized.pop("_attachments", None)
        sanitized.pop("_ts", None)
        return sanitized

    def save(self, data: Dict[str, Any]) -> None:
        self._core.save(data)

    def fetch(self, query: str, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._core.fetch(query, parameters)

    def fetch_user(self, userid: str) -> Dict[str, Any]:
        query = "SELECT TOP 1 * FROM c WHERE c.id = @userid ORDER BY c.date DESC"
        parameters = [{"name": "@userid", "value": userid}]
        result = self.fetch(query, parameters)
        return result[0] if result else {}

    def _upsert_user(self, userid: str, extra_fields: Dict[str, Any]) -> None:
        if not userid:
            raise ValueError("userid must be a non-empty string")

        existing = self._sanitize_item(self.fetch_user(userid))
        data = {**existing, **extra_fields, "id": userid, "userid": userid}
        self.save(data)

    def ensure_user(self, userid: str) -> None:
        if not self.fetch_user(userid):
            self._upsert_user(userid, {})

    def ensure_session(self, userid: str) -> SessionMetadata:
        now = datetime.now(self.TIMEZONE)
        existing = self._sanitize_item(self.fetch_user(userid))
        last_accessed_raw = existing.get("last_accessed")
        last_accessed = datetime.fromisoformat(last_accessed_raw) if last_accessed_raw else None
        has_valid_session = bool(last_accessed and (now - last_accessed) <= self.SESSION_TTL)

        session_id = existing.get("session_id") if has_valid_session else None
        if not session_id:
            session_id = uuid.uuid4().hex

        metadata = SessionMetadata(session_id=session_id, last_accessed=now)
        self._upsert_user(
            userid,
            {
                "session_id": metadata.session_id,
                "last_accessed": metadata.last_accessed.isoformat(),
            },
        )
        return metadata

    def reset_session(self, userid: str) -> SessionMetadata:
        """
        指定ユーザーのセッションIDを強制的にリセットする。

        新しいセッションIDを生成し、会話履歴をリセットする際に使用する。
        """
        now = datetime.now(self.TIMEZONE)
        session_id = uuid.uuid4().hex

        metadata = SessionMetadata(session_id=session_id, last_accessed=now)
        self._upsert_user(
            userid,
            {
                "session_id": metadata.session_id,
                "last_accessed": metadata.last_accessed.isoformat(),
            },
        )
        return metadata

    def save_google_tokens(self, userid: str, tokens: Dict[str, Any]) -> None:
        encrypted = encrypt_dict(tokens)
        self._upsert_user(userid, {"google_tokens_enc": encrypted})

    def clear_google_tokens(self, userid: str) -> None:
        """
        指定ユーザーの Google 認可トークン情報を削除する。

        リフレッシュトークン失効などで再認可が必要になった場合に使用する。
        """
        existing = self._sanitize_item(self.fetch_user(userid))
        if not existing:
            return

        existing.pop("google_tokens_enc", None)
        self.save({**existing, "id": userid, "userid": userid})

    def fetch_google_tokens(self, userid: str) -> Dict[str, Any]:
        query = (
            "SELECT TOP 1 c.google_tokens_enc "
            "FROM c WHERE c.userid = @userid "
            "AND IS_DEFINED(c.google_tokens_enc) "
            "ORDER BY c.date DESC"
        )
        parameters = [{"name": "@userid", "value": userid}]
        result = self.fetch(query, parameters)
        if not result:
            return {}

        record = result[0]
        decrypted = decrypt_dict(record.get("google_tokens_enc", ""))
        return decrypted

    def save_drive_folder_id(self, userid: str, folder_id: str) -> None:
        if not folder_id:
            raise ValueError("folder_id must be a non-empty string")

        sanitized_id = folder_id.strip()
        if not sanitized_id:
            raise ValueError("folder_id must not be blank")

        self._upsert_user(userid, {"drive_folder_id": sanitized_id})

    def fetch_drive_folder_id(self, userid: str) -> str:
        query = (
            "SELECT TOP 1 c.drive_folder_id "
            "FROM c WHERE c.userid = @userid "
            "AND IS_DEFINED(c.drive_folder_id) "
            "ORDER BY c.date DESC"
        )
        parameters = [{"name": "@userid", "value": userid}]
        result = self.fetch(query, parameters)
        if not result:
            return ""

        record = result[0]
        return str(record.get("drive_folder_id", ""))
