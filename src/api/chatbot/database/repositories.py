import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz

from chatbot.utils.config import create_logger

from .core import CosmosCore
from .interfaces import BaseRepository
from .models import SessionMetadata

logger = create_logger(__name__)


class UserRepository(BaseRepository):
    SESSION_TTL = timedelta(hours=1)
    TIMEZONE = pytz.timezone("Asia/Tokyo")

    def __init__(self, cosmos_core: CosmosCore):
        """
        Args:
            cosmos_core: CosmosCore インスタンス
        """
        self._core = cosmos_core

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

        Args:
            userid: ユーザーID

        Returns:
            SessionMetadata: 新しいセッション情報

        Raises:
            ValueError: ユーザーが存在しない場合
        """
        # ユーザーの存在を確認
        existing = self.fetch_user(userid)
        if not existing:
            raise ValueError(f"User {userid} does not exist")

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
