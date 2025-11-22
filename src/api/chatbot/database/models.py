from datetime import datetime
from typing import Dict, List, Any
from pydantic import BaseModel


class DatabaseRecord(BaseModel):
    """データベースレコードの基本モデル"""

    id: str
    date: datetime


class NameData(DatabaseRecord):
    """名前データモデル"""

    userid: str
    content: Dict[str, Any]


class AgentSession(DatabaseRecord):
    """エージェントセッションモデル"""

    id: str
    date: datetime
    userid: str
    messages: List[Dict[str, Any]]
    full_contents: List[Dict[str, Any]]
    filtered_contents: List[Dict[str, Any]]
