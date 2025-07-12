import os
import re
import uuid
from datetime import datetime
from typing import List

from azure.cosmos import CosmosClient
from langchain_core.documents import Document
from openai import OpenAI

from logger import logger


class CosmosDBUploader:
    def __init__(self):
        self.model: str = "text-embedding-3-small"
        self.database_name = "diary"
        self.container_name = "entries"
        self.userid = os.getenv("LINE_USER_ID", "default_user")  # LINE user ID変数名を統一

        # CosmosDB接続設定（src/apiと同じ変数名）
        self.cosmos_url = os.getenv("COSMOS_DB_ACCOUNT_URL")
        self.cosmos_key = os.getenv("COSMOS_DB_ACCOUNT_KEY")

        # OpenAI接続設定
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # CosmosDBクライアント初期化
        self.cosmos_client = CosmosClient(self.cosmos_url, self.cosmos_key)
        self.database = self.cosmos_client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)

        logger.info("CosmosDB Vector Search の設定が完了しました。")

    def _generate_embedding(self, text: str) -> List[float]:
        """OpenAIを使用してテキストの埋め込みを生成"""
        try:
            response = self.openai_client.embeddings.create(input=text, model=self.model)
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"埋め込み生成でエラーが発生しました: {str(e)}")
            raise

    def _extract_date_info(self, metadata: dict) -> dict:
        """メタデータから日付情報を抽出して構造化"""
        source = metadata.get("source", "")

        # 日本語形式：2025年07月11日(金).md
        jp_pattern = r"(\d{4})年(\d{2})月(\d{2})日\(([月火水木金土日])\)"
        jp_match = re.search(jp_pattern, source)

        if jp_match:
            year, month, day, weekday_jp = jp_match.groups()
            date_str = f"{year}-{month}-{day}"
            weekday_map = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}
            day_of_week = weekday_map.get(weekday_jp, 0)
        else:
            # 既存の ISO形式パターンもサポート
            date_pattern = r"(\d{4}-\d{2}-\d{2})"
            match = re.search(date_pattern, source)
            if match:
                date_str = match.group(1)
                day_of_week = datetime.strptime(date_str, "%Y-%m-%d").weekday()
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
                day_of_week = datetime.now().weekday()

        return {
            "date": date_str,
            "year": int(date_str[:4]),
            "month": int(date_str[5:7]),
            "day": int(date_str[8:10]),
            "dayOfWeek": day_of_week,
        }

    def upsert_entry(self, userid: str, content: str, date_iso: str = None, metadata: dict = None):
        """日記エントリをCosmos DBにアップサート"""
        try:
            # メタデータから日付情報を抽出
            if metadata:
                date_info = self._extract_date_info(metadata)
                date_str = date_info["date"]
            else:
                date_str = date_iso or datetime.now().strftime("%Y-%m-%d")
                date_info = {
                    "date": date_str,
                    "year": int(date_str[:4]),
                    "month": int(date_str[5:7]),
                    "day": int(date_str[8:10]),
                    "dayOfWeek": datetime.strptime(date_str, "%Y-%m-%d").weekday(),
                }

            # 同じ日付の既存エントリを検索
            existing_entry = None
            try:
                query = "SELECT * FROM c WHERE c.userId = @userid AND c.date = @date"
                parameters = [{"name": "@userid", "value": userid}, {"name": "@date", "value": date_str}]
                items = list(self.container.query_items(query=query, parameters=parameters, partition_key=userid))
                if items:
                    existing_entry = items[0]  # 同じ日付の最初のエントリを取得
                    logger.info(f"既存の日記エントリを更新します: {existing_entry['id']} (日付: {date_str})")
            except Exception as search_error:
                logger.warning(f"既存エントリの検索でエラーが発生しました: {str(search_error)}")

            # 埋め込み生成
            content_vector = self._generate_embedding(content)

            # エントリ作成（既存IDまたは新規ID）
            entry = {
                "id": existing_entry["id"] if existing_entry else str(uuid.uuid4()),
                "userId": userid,  # パーティションキー（infra設定と一致）
                "date": date_str,
                "year": date_info["year"],
                "month": date_info["month"],
                "day": date_info["day"],
                "dayOfWeek": date_info["dayOfWeek"],
                "content": content,
                "contentVector": content_vector,
                "tags": [],
                "metadata": metadata or {},
            }

            # CosmosDBにアップサート
            self.container.upsert_item(entry)
            action = "更新" if existing_entry else "新規作成"
            logger.info(f"日記エントリを{action}しました: {entry['id']} (日付: {date_str})")

        except Exception as e:
            logger.error(f"CosmosDBへの保存でエラーが発生しました: {str(e)}")
            raise

    def upload(self, docs: List[Document]):
        """ドキュメントリストをCosmosDBにアップロード"""
        logger.info(f"{len(docs)}件のドキュメントがロードされました。")

        for doc in docs:
            # ドキュメントをアップサート（メタデータから日付情報を自動抽出）
            self.upsert_entry(userid=self.userid, content=doc.page_content, metadata=doc.metadata)

        logger.info(f"{len(docs)}件のドキュメントがCosmosDBに追加されました。")
