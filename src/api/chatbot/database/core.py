import os
from typing import List, Dict, Any
from azure.cosmos import CosmosClient, PartitionKey
from fastapi import HTTPException
from datetime import datetime
import pytz
import uuid


class CosmosCore:
    """CosmosDBの基本操作を提供するクラス"""

    def __init__(self, container_name: str):
        """
        Args:
            container_name: コンテナ名
        """
        self._client = self._get_client()
        self._container = self._init_container(container_name)

    def _get_client(self):
        """CosmosDBクライアントの初期化"""
        url = os.getenv("COSMOS_DB_ACCOUNT_URL")
        key = os.getenv("COSMOS_DB_ACCOUNT_KEY")
        return CosmosClient(url=url, credential=key)

    def _init_container(self, container_name: str):
        """コンテナの初期化"""
        database = self._client.create_database_if_not_exists(id=os.getenv("COSMOS_DB_DATABASE_NAME"))
        return database.create_container_if_not_exists(id=container_name, partition_key=PartitionKey(path="/id"))

    def save(self, data: Dict[str, Any]) -> None:
        """データの保存"""
        try:
            # 保存するデータを作成
            now = datetime.now(pytz.timezone("Asia/Tokyo"))
            # contentの中にidがなければidを生成して追加
            if "id" not in data:
                data["id"] = uuid.uuid4().hex
            # id,dataのあとにcontentを接続してdictを作成
            data = {
                "date": now.isoformat(),
                **data,
            }
            self._container.upsert_item(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to save data")

    def fetch(self, query: str, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """データの取得"""
        try:
            return list(
                self._container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to fetch data")
