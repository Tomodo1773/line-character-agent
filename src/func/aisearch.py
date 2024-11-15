import logging
import os

from azure.search.documents.indexes.models import (
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SimpleField,
)
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ストリームハンドラを追加
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


class AISearchUploader:

    def __init__(self):
        self.model: str = "text-embedding-3-large"
        self.index_name = "diary-vector"
        self.embeddings = self._set_embeddings()
        self.fields = self._set_index_fields()
        self.vector_store = self._create_instance()

        logger.info("ベクトル化の設定が完了しました。")

    def _set_index_fields(self):
        self.fields = [
            SimpleField(
                name="id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SearchableField(
                name="content", type=SearchFieldDataType.String, searchable=True, analyzer_name="ja.microsoft"
            ),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=len(self.embeddings.embed_query("Text")),
                vector_search_profile_name="myHnswProfile",
            ),
            SearchableField(
                name="metadata", type=SearchFieldDataType.String, searchable=True, analyzer_name="ja.microsoft"
            ),
        ]

    def _set_embeddings(self):
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key, openai_api_version="2024-06-01", model=self.model)
        return embeddings

    def _create_instance(self):
        # AzureSearchのインスタンスを初期化
        vector_store_address = os.environ.get("AZURE_SEARCH_ENDPOINT")
        vector_store_password = os.environ.get("AZURE_SEARCH_ADMIN_KEY")

        vector_store = AzureSearch(
            azure_search_endpoint=vector_store_address,
            azure_search_key=vector_store_password,
            index_name=self.index_name,
            embedding_function=self.embeddings.embed_query,
            fields=self.fields,
        )
        return vector_store

    def upload(self, docs: list[Document]):
        logger.info(f"{len(docs)}件のドキュメントがロードされました。")
        # ドキュメントをAzureSearchに追加
        self.vector_store.add_documents(documents=docs)
        logger.info(f"{len(docs)}件のドキュメントがAzureSearchインデックスに追加されました。")


if __name__ == "__main__":
    uploader = AISearchUploader()
    document = Document(page_content="Hello, world!", metadata={"source": "https://example.com"})
    uploader.upload(document)
