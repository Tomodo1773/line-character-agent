import os
import uuid
from datetime import datetime
from typing import List

from azure.cosmos import CosmosClient, PartitionKey
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
        self.openai_client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # CosmosDBクライアント初期化
        self.cosmos_client = CosmosClient(self.cosmos_url, self.cosmos_key)
        self.database = self.cosmos_client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)
        
        logger.info("CosmosDB Vector Search の設定が完了しました。")

    def _generate_embedding(self, text: str) -> List[float]:
        """OpenAIを使用してテキストの埋め込みを生成"""
        try:
            response = self.openai_client.embeddings.create(
                input=text,
                model=self.model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"埋め込み生成でエラーが発生しました: {str(e)}")
            raise

    def _extract_date_from_metadata(self, metadata: dict) -> str:
        """メタデータから日付を抽出"""
        # ファイル名から日付を抽出する処理を実装
        source = metadata.get('source', '')
        
        # 日付パターンを探す（例：2024-01-01のような形式）
        import re
        date_pattern = r'(\d{4}-\d{2}-\d{2})'
        match = re.search(date_pattern, source)
        
        if match:
            return match.group(1)
        else:
            # 日付が見つからない場合は今日の日付を使用
            return datetime.now().strftime('%Y-%m-%d')

    def upsert_entry(self, userid: str, content: str, date_iso: str = None, metadata: dict = None):
        """日記エントリをCosmos DBにアップサート"""
        try:
            # 埋め込み生成
            content_vector = self._generate_embedding(content)
            
            # エントリ作成
            entry = {
                "id": str(uuid.uuid4()),
                "userId": userid,  # パーティションキー（infra設定と一致）
                "date": date_iso or datetime.now().strftime('%Y-%m-%d'),
                "content": content,
                "contentVector": content_vector,
                "tags": [],
                "metadata": metadata or {}
            }
            
            # CosmosDBにアップサート
            self.container.upsert_item(entry)
            logger.info(f"日記エントリをCosmosDBに保存しました: {entry['id']}")
            
        except Exception as e:
            logger.error(f"CosmosDBへの保存でエラーが発生しました: {str(e)}")
            raise

    def upload(self, docs: List[Document]):
        """ドキュメントリストをCosmosDBにアップロード"""
        logger.info(f"{len(docs)}件のドキュメントがロードされました。")
        
        for doc in docs:
            # メタデータから日付を抽出
            date_iso = self._extract_date_from_metadata(doc.metadata)
            
            # ドキュメントをアップサート
            self.upsert_entry(
                userid=self.userid,
                content=doc.page_content,
                date_iso=date_iso,
                metadata=doc.metadata
            )
        
        logger.info(f"{len(docs)}件のドキュメントがCosmosDBに追加されました。")


if __name__ == "__main__":
    uploader = CosmosDBUploader()
    document = Document(page_content="テストドキュメント", metadata={"source": "test-2024-01-01.txt"})
    uploader.upload([document])