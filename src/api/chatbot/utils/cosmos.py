import os
import uuid
from datetime import datetime, timedelta

import pytz
from azure.cosmos import ContainerProxy, CosmosClient, PartitionKey, exceptions
from chatbot.utils.config import logger
from dotenv import load_dotenv
from fastapi import HTTPException

# .envファイルを読み込む
load_dotenv()


class SaveComosDB:

    def __init__(self):
        self.container = self.__prepare_cosmos()

    def __prepare_cosmos(self) -> ContainerProxy:
        config = {
            "url": os.getenv("COSMOS_DB_ACCOUNT_URL"),
            "key": os.getenv("COSMOS_DB_ACCOUNT_KEY"),
            "database_name": os.getenv("COSMOS_DB_DATABASE_NAME"),
            "container_name": "CHAT",
        }
        client = CosmosClient(url=config["url"], credential=config["key"])
        try:
            database = client.create_database_if_not_exists(id=config["database_name"])
            container = database.create_container_if_not_exists(
                id=config["container_name"], partition_key=PartitionKey(path="/id")
            )
            logger.info("Successfully initialized the database and container.")
            return container
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to create the database or container: {e}")
            raise HTTPException(status_code=500, detail="Failed to perform database operation")

    def save_messages(self, userid: str, sessionid: str, messages: list[dict]) -> None:
        try:
            # 保存するデータを作成
            now = datetime.now(pytz.timezone("Asia/Tokyo"))
            data = {
                "id": sessionid,
                "userid": userid,
                "date": now.isoformat(),
                "messages": messages,
            }
            # CosmosDBにデータを保存
            self.container.upsert_item(data)
            logger.info("Chat message has been saved successfully.")
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to save data to CosmosDB: {e}")
            raise HTTPException(status_code=500, detail="Failed to save the message")

    def fetch_messages(self, limit=1):
        try:
            # CosmosDBから最新のチャットメッセージを取得
            # 最新{limit}件のitemを取得するためにここではDESCを指定
            query = "SELECT * FROM c ORDER BY c.date DESC OFFSET 0 LIMIT @limit"
            items = list(
                self.container.query_items(
                    query=query, parameters=[{"name": "@limit", "value": limit}], enable_cross_partition_query=True
                )
            )
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

            logger.info("Successfully retrieved the latest chat messages.")
            return sessionid, formatted_items
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to fetch data from CosmosDB: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch chat messages")
