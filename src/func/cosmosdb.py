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
        self.openai_client = self._setup_openai_client()
        self.cosmos_client = self._setup_cosmos_client()
        self.database = self.cosmos_client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)

        logger.info("Cosmos DB Uploaderの設定が完了しました。")

    def _setup_openai_client(self) -> OpenAI:
        """OpenAI クライアントを設定"""
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        return OpenAI(api_key=openai_api_key)

    def _setup_cosmos_client(self) -> CosmosClient:
        """Cosmos DB クライアントを設定"""
        endpoint = os.environ.get("COSMOS_ENDPOINT")
        key = os.environ.get("COSMOS_KEY")
        
        if not endpoint or not key:
            raise ValueError("COSMOS_ENDPOINT and COSMOS_KEY environment variables are required")
        
        return CosmosClient(endpoint, key)

    def _generate_embedding(self, text: str) -> List[float]:
        """テキストからベクトル埋め込みを生成"""
        try:
            response = self.openai_client.embeddings.create(
                input=text,
                model=self.model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"ベクトル埋め込み生成中にエラーが発生しました: {e}")
            raise

    def upsert_entry(self, user_id: str, content: str, date_iso: str = None, source: str = None) -> dict:
        """日記エントリをCosmos DBにupsert"""
        try:
            # ベクトル埋め込みを生成
            content_vector = self._generate_embedding(content)
            
            # エントリを作成
            entry = {
                "id": str(uuid.uuid4()),
                "userId": user_id,
                "date": date_iso or datetime.now().isoformat(),
                "content": content,
                "contentVector": content_vector,
                "tags": [],
                "metadata": {
                    "source": source or "unknown",
                    "created_at": datetime.now().isoformat()
                }
            }
            
            # Cosmos DBにupsert
            result = self.container.upsert_item(entry)
            logger.info(f"エントリ {entry['id']} をCosmos DBにupsertしました")
            return result
            
        except Exception as e:
            logger.error(f"エントリのupsert中にエラーが発生しました: {e}")
            raise

    def upload(self, docs: List[Document], user_id: str = "default_user"):
        """複数のドキュメントをCosmos DBにアップロード"""
        logger.info(f"{len(docs)}件のドキュメントをCosmos DBにアップロード開始")
        
        uploaded_count = 0
        for doc in docs:
            try:
                # メタデータから日付とソース情報を取得
                source = doc.metadata.get("source", "unknown")
                date_iso = doc.metadata.get("date")
                
                # エントリをupsert
                self.upsert_entry(
                    user_id=user_id,
                    content=doc.page_content,
                    date_iso=date_iso,
                    source=source
                )
                uploaded_count += 1
                
            except Exception as e:
                logger.error(f"ドキュメント {doc.metadata.get('source', 'unknown')} のアップロード中にエラー: {e}")
                continue
        
        logger.info(f"{uploaded_count}件のドキュメントをCosmos DBにアップロードしました")
        return uploaded_count


if __name__ == "__main__":
    uploader = CosmosDBUploader()
    document = Document(page_content="Hello, world!", metadata={"source": "test.txt"})
    uploader.upload([document])