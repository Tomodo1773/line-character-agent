import os
import uuid
from datetime import datetime
from typing import List

from azure.cosmos import CosmosClient
from langchain_core.documents import Document
from openai import OpenAI

from diary_files import extract_date_info_from_source
from logger import logger


class CosmosDBUploader:
    def __init__(self, userid: str):
        if not userid:
            raise ValueError("userid is required")

        self.model: str = "text-embedding-3-small"
        self.database_name = "diary"
        self.container_name = "entries"
        self.userid = userid

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

        # 日記ファイル名からの抽出を優先
        date_info = extract_date_info_from_source(source)
        if date_info:
            return date_info

        # フォールバックとして現在日付を使用
        date_str = datetime.now().strftime("%Y-%m-%d")
        day_of_week = datetime.now().weekday()

        return {
            "date": date_str,
            "year": int(date_str[:4]),
            "month": int(date_str[5:7]),
            "day": int(date_str[8:10]),
            "dayOfWeek": day_of_week,
        }

    def create_entry(self, userid: str, content: str, date_iso: str = None, metadata: dict = None):
        """日記エントリをCosmos DBに新規作成"""
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

            # 埋め込み生成
            content_vector = self._generate_embedding(content)

            # ファイル名（拡張子なし）を取得
            filename_without_ext = ""
            if metadata and "source" in metadata:
                source = metadata["source"]
                filename_without_ext = source.rsplit(".", 1)[0] if "." in source else source

            # contentの先頭にファイル名を追加
            content_with_filename = f"{filename_without_ext}\n\n{content}" if filename_without_ext else content

            # エントリ作成
            entry = {
                "id": str(uuid.uuid4()),
                "userId": userid,  # パーティションキー（infra設定と一致）
                "date": date_str,
                "year": date_info["year"],
                "month": date_info["month"],
                "day": date_info["day"],
                "dayOfWeek": date_info["dayOfWeek"],
                "content": content_with_filename,
                "contentVector": content_vector,
                "tags": [],
                "metadata": metadata or {},
            }

            # CosmosDBに新規作成
            self.container.create_item(entry)
            logger.info(f"日記エントリを新規作成しました: {entry['id']} (日付: {date_str})")

        except Exception as e:
            logger.error(f"CosmosDBへの保存でエラーが発生しました: {str(e)}")
            raise

    def check_entry_exists(self, userid: str, date_str: str) -> bool:
        """指定した日付のエントリが既に存在するかチェック"""
        try:
            query = "SELECT * FROM c WHERE c.userId = @userid AND c.date = @date"
            parameters = [{"name": "@userid", "value": userid}, {"name": "@date", "value": date_str}]
            items = list(self.container.query_items(query=query, parameters=parameters, partition_key=userid))
            return len(items) > 0
        except Exception as e:
            logger.warning(f"既存エントリの検索でエラーが発生しました: {str(e)}")
            return False

    def upload(self, docs: List[Document], skip_existing: bool = True):
        """ドキュメントリストをCosmosDBにアップロード"""
        logger.info(f"{len(docs)}件のドキュメントがロードされました。")

        uploaded_count = 0
        skipped_count = 0

        for doc in docs:
            if skip_existing:
                # メタデータから日付情報を抽出
                date_info = self._extract_date_info(doc.metadata)
                date_str = date_info["date"]

                # 既存エントリをチェック
                if self.check_entry_exists(self.userid, date_str):
                    logger.info(f"日付 {date_str} の日記は既に存在するためスキップします。")
                    skipped_count += 1
                    continue

            # ドキュメントを新規作成（メタデータから日付情報を自動抽出）
            self.create_entry(userid=self.userid, content=doc.page_content, metadata=doc.metadata)
            uploaded_count += 1

        if skip_existing:
            logger.info(
                f"{uploaded_count}件のドキュメントがCosmosDBに追加されました。CosmosDBに保存済みでスキップされたアイテムは{skipped_count}件です。"
            )
        else:
            logger.info(f"{len(docs)}件のドキュメントがCosmosDBに追加されました。")
