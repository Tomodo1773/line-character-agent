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


class CosmosCore:

    def __init__(self, container_name: str):
        self.container = self.__prepare_cosmos(container_name)

    def __prepare_cosmos(self, container_name: str) -> ContainerProxy:
        config = {
            "url": os.getenv("COSMOS_DB_ACCOUNT_URL"),
            "key": os.getenv("COSMOS_DB_ACCOUNT_KEY"),
            "database_name": os.getenv("COSMOS_DB_DATABASE_NAME"),
            "container_name": container_name,
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

    def save(self, content: dict) -> None:
        try:
            # 保存するデータを作成
            now = datetime.now(pytz.timezone("Asia/Tokyo"))
            # contentの中にidがなければidを生成して追加
            if 'id' not in content:
                content['id'] = uuid.uuid4().hex
            # id,dataのあとにcontentを接続してdictを作成
            data = {
                "date": now.isoformat(),
                **content,
            }
            # CosmosDBにデータを保存
            self.container.upsert_item(data)
            logger.info("Successfully save the content")
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to save data to CosmosDB: {e}")
            raise HTTPException(status_code=500, detail="Failed to save the message")

    def fetch(self, query: str, parameters: list) -> list:
        try:
            # CosmosDBからコンテントを取得
            items = list(
                self.container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)
            )
            logger.info("Successfully fetch the content")
            return items
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to fetch data from CosmosDB: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch chat messages")
