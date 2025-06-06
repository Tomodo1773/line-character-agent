from datetime import datetime, timedelta
import uuid
import pytz
from typing import Dict, Any, List

from langchain_core.messages import BaseMessage, messages_to_dict

from .interfaces import BaseRepository
from .core import CosmosCore
from .models import AgentSession


class UserRepository(BaseRepository):
    def __init__(self):
        self._core = CosmosCore("USERS")

    def save(self, data: Dict[str, Any]) -> None:
        self._core.save(data)

    def fetch(self, query: str, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._core.fetch(query, parameters)

    def save_profile(self, userid: str, profile: dict) -> None:
        data = {"userid": userid, "profile": profile}
        self.save(data)

    def fetch_profile(self, userid: str) -> dict:
        query = "SELECT c.profile FROM c WHERE c.userid = @userid"
        parameters = [{"name": "@userid", "value": userid}]
        return self.fetch(query, parameters)


class AgentRepository(BaseRepository):
    def __init__(self):
        self._core = CosmosCore("CHAT")
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
