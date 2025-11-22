import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz
from langchain_core.messages import BaseMessage, messages_to_dict

from chatbot.utils.crypto import decrypt_dict, encrypt_dict

from .core import CosmosCore
from .interfaces import BaseRepository
from .models import AgentSession


class UserRepository(BaseRepository):
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

    def save_google_tokens(self, userid: str, tokens: Dict[str, Any]) -> None:
        encrypted = encrypt_dict(tokens)
        self._upsert_user(userid, {"google_tokens_enc": encrypted})

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


class AgentRepository(BaseRepository):
    def __init__(self):
        self._core = CosmosCore("chat")
        self.sessionid = None
        self.history = []
        self.filtered_history = []

    def save(self, data: Dict[str, Any]) -> None:
        self._core.save(data)

    def fetch(self, query: str, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._core.fetch(query, parameters)

    def save_messages(self, userid: str, messages: BaseMessage) -> None:
        messages_dict = messages_to_dict(messages)
        history = [message["data"] for message in messages_dict]
        self.save_list(userid, history)

    def save_list(self, userid: str, messages: list) -> None:
        data = {"id": self.sessionid, "userid": userid, "messages": messages}
        self.save(data)

    def add_messages(self, userid: str, add_messages: list) -> None:
        if self.sessionid is None:
            self.fetch_messages()
        messages = self.history
        messages.extend(add_messages)
        self.save_list(userid, messages)

    def fetch_messages(self, limit=1) -> AgentSession:
        query = "SELECT * FROM c ORDER BY c.date DESC OFFSET 0 LIMIT @limit"
        items = self.fetch(query=query, parameters=[{"name": "@limit", "value": limit}])

        now = datetime.now(pytz.timezone("Asia/Tokyo"))
        recent_items = [item for item in items if datetime.fromisoformat(item["date"]) > now - timedelta(hours=1)]

        if not recent_items:
            sessionid = uuid.uuid4().hex
            messages = []
            userid = ""  # デフォルト値または適切な値を設定
        else:
            sessionid = recent_items[0]["id"]
            messages = recent_items[0].get("messages", [])
            userid = recent_items[0].get("userid", "")

        self.sessionid = sessionid
        self.history = messages

        return AgentSession(
            id=sessionid, date=now, userid=userid, messages=messages, full_contents=messages, filtered_contents=[]
        )
