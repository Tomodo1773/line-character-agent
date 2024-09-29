import uuid
from datetime import datetime, timedelta

import pytz
from chatbot.utils.config import logger
from langchain_core.messages import BaseMessage, messages_to_dict

from .core import CosmosCore


class AgentCosmosDB:

    def __init__(self):
        self.container = CosmosCore("CHAT")

    def save_messages(self, userid: str, sessionid: str, messages: BaseMessage) -> None:
        messages_dict = messages_to_dict(messages)
        history = [message["data"] for message in messages_dict]
        # 保存するデータを作成
        data = {
            "id": sessionid,
            "userid": userid,
            "messages": history,
        }
        # CosmosDBにデータを保存
        self.container.save(data)

    def fetch_messages(self, limit=1):
        # CosmosDBから最新のチャットメッセージを取得
        # 最新{limit}件のitemを取得するためにここではDESCを指定
        query = "SELECT * FROM c ORDER BY c.date DESC OFFSET 0 LIMIT @limit"
        items = self.container.fetch(query=query, parameters=[{"name": "@limit", "value": limit}])
        # 現在の日時を取得
        now = datetime.now(pytz.timezone("Asia/Tokyo"))
        # 取得したitemの中で最新のものが日本時間の現在時刻と比べて1時間以内かを確認
        recent_items = [item for item in items if datetime.fromisoformat(item["date"]) > now - timedelta(hours=1)]
        # recent_itemsが空の場合は全てのitemを取得
        if not recent_items:
            sessionid = uuid.uuid4().hex
            formatted_items = []
        else:
            sessionid = recent_items[0]["id"]
            formatted_items = recent_items[0]["messages"]
            # 以下のコードはmessagesの中の最新20件のみにフィルタするコード
            # フィルタされたmessageをDBに保存するロジックが未実装のためコメントアウト
            # num_items = 20
            # formatted_items = recent_items[0]["messages"][-num_items:]
            # if formatted_items[0]["type"] == "tool":
            #     num_items += 1
            #     formatted_items = recent_items[0]["messages"][-num_items:]
        logger.info("Successfully retrieved the latest chat messages.")
        return sessionid, formatted_items
