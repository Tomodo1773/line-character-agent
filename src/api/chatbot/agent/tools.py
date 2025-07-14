import os
from typing import Optional

from azure.cosmos import CosmosClient
from dotenv import load_dotenv
from langchain_azure_ai.vectorstores import AzureCosmosDBNoSqlVectorSearch
from langchain_community.document_loaders import FireCrawlLoader
from langchain_community.retrievers import AzureAISearchRetriever
from langchain_core.documents.base import Document
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

load_dotenv()


class FirecrawlSearchInput(BaseModel):
    url: str = Field(description="web site url")


@tool("firecrawl-search-tool", args_schema=FirecrawlSearchInput)
def firecrawl_search(url: str) -> Document:
    """A tool for retrieving the content of a web page by specifying a URL. Useful when a user provides a URL."""
    loader = FireCrawlLoader(url=url, mode="scrape")
    docs = loader.load()
    return docs[0]


class DiarySearchInput(BaseModel):
    query_text: str = Field(description="検索したい自然文")
    top_k: Optional[int] = Field(default=5, description="返す件数 (1-20)", ge=1, le=20)
    start_date: Optional[str] = Field(default=None, description="絞り込み開始日 (ISO-8601)")
    end_date: Optional[str] = Field(default=None, description="絞り込み終了日 (ISO-8601)")
    order: Optional[str] = Field(default="asc", description="日付の並べ替え方向")
    search_mode: Optional[str] = Field(default="hybrid", description="検索方式: 'hybrid'=ベクトル+BM25, 'vector'=ベクトルのみ")


# CosmosDB接続用のグローバル変数
_cosmos_vectorstore = None


def get_cosmos_vectorstore():
    """CosmosDBベクトルストアのシングルトンインスタンスを取得"""
    global _cosmos_vectorstore
    if _cosmos_vectorstore is None:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        # CosmosClientを作成
        cosmos_client = CosmosClient(url=os.getenv("COSMOS_DB_ACCOUNT_URL"), credential=os.getenv("COSMOS_DB_ACCOUNT_KEY"))

        # 実際のinfra設定に基づく正確な設定
        vector_embedding_policy = {
            "vectorEmbeddings": [
                {"path": "/contentVector", "dataType": "float32", "dimensions": 1536, "distanceFunction": "cosine"}
            ]
        }

        indexing_policy = {
            "indexingMode": "consistent",
            "automatic": True,
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [{"path": '/"_etag"/?'}, {"path": "/contentVector/*"}],
            "vectorIndexes": [{"path": "/contentVector", "type": "diskANN"}],
            "fullTextPolicy": {"defaultLanguage": "ja", "analyzers": [{"path": "/content", "language": "ja"}]},
        }

        cosmos_container_properties = {"id": "entries", "partition_key": {"paths": ["/userId"], "kind": "Hash"}}

        cosmos_database_properties = {"id": "diary"}

        vector_search_fields = {
            "embedding_field": "contentVector",
            "text_field": "content",  # READMEスキーマ通り
        }

        _cosmos_vectorstore = AzureCosmosDBNoSqlVectorSearch(
            cosmos_client=cosmos_client,
            embedding=embeddings,
            database_name="diary",
            container_name="entries",
            vector_embedding_policy=vector_embedding_policy,
            indexing_policy=indexing_policy,
            cosmos_container_properties=cosmos_container_properties,
            cosmos_database_properties=cosmos_database_properties,
            vector_search_fields=vector_search_fields,
            search_type="vector",
            create_container=False,
            metadata_key="metadata",  # metadataキーを明示的に指定
        )
    return _cosmos_vectorstore


# Cosmos DB直接アクセス用の変数
_cosmos_client = None
_cosmos_container = None


def get_cosmos_client():
    """CosmosDBクライアントを取得"""
    global _cosmos_client
    if _cosmos_client is None:
        _cosmos_client = CosmosClient(url=os.getenv("COSMOS_DB_ACCOUNT_URL"), credential=os.getenv("COSMOS_DB_ACCOUNT_KEY"))
    return _cosmos_client


def get_cosmos_container():
    """CosmosDBコンテナを取得"""
    global _cosmos_container
    if _cosmos_container is None:
        client = get_cosmos_client()
        database = client.get_database_client("diary")
        _cosmos_container = database.get_container_client("entries")
    return _cosmos_container


def create_query_embedding(query_text: str):
    """クエリテキストをベクトル埋め込みに変換"""
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    return embeddings.embed_query(query_text)


def custom_vector_search(query_text: str, top_k: int = 5, start_date: str = None, end_date: str = None):
    """カスタムベクトル検索実装（ライブラリのバグを回避）"""
    try:
        # クエリのベクトル埋め込みを作成
        query_vector = create_query_embedding(query_text)

        # コンテナを取得
        container = get_cosmos_container()

        # ベクトル検索クエリを構築
        vector_search_query = f"""
        SELECT TOP {top_k} c.id, c.content, c.date, c.metadata, c.userId,
               VectorDistance(c.contentVector, {query_vector}) AS SimilarityScore
        FROM c
        """

        # 日付フィルタを追加
        conditions = []
        if start_date:
            conditions.append(f'c.date >= "{start_date}"')
        if end_date:
            conditions.append(f'c.date <= "{end_date}"')

        if conditions:
            vector_search_query += " WHERE " + " AND ".join(conditions)

        # VectorDistanceは自動的に最も類似（最小距離）から並び順になるため、ORDER BY不要

        # クエリを実行
        results = list(container.query_items(query=vector_search_query, enable_cross_partition_query=True))

        return results

    except Exception as e:
        print(f"カスタムベクトル検索エラー: {str(e)}")
        return []


@tool("diary-search-tool", args_schema=DiarySearchInput)
def diary_search_tool(
    query_text: str,
    top_k: int = 5,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    order: str = "asc",
    search_mode: str = "hybrid",
) -> str:
    """ユーザの日記コレクションをベクトル／ハイブリッド検索し、条件に合うエントリを返す"""
    try:
        # カスタムベクトル検索を使用（ライブラリのバグを回避）
        results = custom_vector_search(query_text=query_text, top_k=top_k, start_date=start_date, end_date=end_date)

        if not results:
            return "日記に関連する情報が見つかりませんでした。"

        # 必要なら日付ソート
        if order == "desc":
            results = sorted(results, key=lambda d: d.get("date", ""), reverse=True)

        # Format the diary entries for better readability
        diary_entries = []
        for result in results:
            date_info = result.get("date", "日付不明")
            content = result.get("content", "")
            similarity_score = result.get("SimilarityScore", 0)
            diary_entries.append(f"【{date_info}】{content} (類似度: {similarity_score:.3f})")

        return "\n\n".join(diary_entries)

    except Exception as e:
        return f"日記検索中にエラーが発生しました: {str(e)}"


def azure_ai_search(query: str) -> str:
    """A tool for retrieving relevant entries from the user's personal diary stored in Azure AI Search.
    Useful for answering questions based on the user's past experiences and thoughts."""
    retriever = AzureAISearchRetriever(content_key="content", top_k=3, index_name="diary-vector")
    docs = retriever.invoke(query)
    documents = [{"diary_contents": [doc.page_content for doc in docs]}]
    return documents  # Return formatted diary entries as a string


if __name__ == "__main__":
    # firecrawl_search(url="https://www.example.com")
    docs = azure_ai_search("花火にいったのはいつだっけ？")
    print(docs)
