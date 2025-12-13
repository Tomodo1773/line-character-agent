import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

import pytz
from azure.cosmos import CosmosClient, PartitionKey
from fastapi import HTTPException


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
        verify_setting = os.getenv("COSMOS_DB_CONNECTION_VERIFY")

        if verify_setting is None:
            connection_verify = True
        else:
            lowered = verify_setting.lower()
            if lowered in {"false", "0", "no"}:
                connection_verify = False
            elif lowered in {"true", "1", "yes"}:
                connection_verify = True
            else:
                connection_verify = verify_setting

        return CosmosClient(url=url, credential=key, connection_verify=connection_verify)

    def _init_container(self, container_name: str):
        """コンテナの初期化"""
        # mainデータベースを600 RU/sの共有スループットで作成（存在しない場合のみ）
        database = self._client.create_database_if_not_exists(id="main", offer_throughput=600)
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
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to save data")

    def fetch(self, query: str, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """データの取得"""
        try:
            return list(self._container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True))
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to fetch data")
