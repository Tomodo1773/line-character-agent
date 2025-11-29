from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel


class DatabaseRecord(BaseModel):
    """データベースレコードの基本モデル"""

    id: str
    date: datetime


class NameData(DatabaseRecord):
    """名前データモデル"""

    userid: str
    content: Dict[str, Any]


class SessionMetadata(BaseModel):
    """Cosmos DB 上で管理するセッションメタデータ"""

    session_id: str
    last_accessed: datetime
