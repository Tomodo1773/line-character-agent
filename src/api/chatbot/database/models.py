from datetime import datetime
from typing import Dict, List, Any, Optional
from pydantic import BaseModel


class DatabaseRecord(BaseModel):
    """データベースレコードの基本モデル"""

    id: str
    date: datetime


class UserProfile(DatabaseRecord):
    """ユーザープロファイルモデル"""

    userid: str
    profile: Dict[str, Any]


class NameData(DatabaseRecord):
    """名前データモデル"""

    userid: str
    content: Dict[str, Any]


class AgentSession(DatabaseRecord):
    """エージェントセッションモデル"""

    userid: str
    messages: List[Dict[str, Any]]
