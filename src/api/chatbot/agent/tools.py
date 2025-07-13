import os
from typing import Optional
from datetime import date

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
        _cosmos_vectorstore = AzureCosmosDBNoSqlVectorSearch(
            embedding=embeddings,
            endpoint=os.getenv("COSMOS_DB_ACCOUNT_URL"),
            key=os.getenv("COSMOS_DB_ACCOUNT_KEY"),
            database_name="diary",
            container_name="entries",
            vector_path="/contentVector",
            search_type="hybrid",
        )
    return _cosmos_vectorstore


@tool("diary-search-tool", args_schema=DiarySearchInput)
def diary_search_tool(
    query_text: str,
    top_k: int = 5,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    order: str = "asc",
    search_mode: str = "hybrid"
) -> str:
    """ユーザの日記コレクションをベクトル／ハイブリッド検索し、条件に合うエントリを返す"""
    try:
        vstore = get_cosmos_vectorstore()
        
        # メタデータフィルタを組む
        filters = []
        if start_date:
            filters.append(f'c.date >= "{start_date}"')
        if end_date:
            filters.append(f'c.date <= "{end_date}"')
        search_filter = " AND ".join(filters) if filters else None
        
        # ストア検索
        docs = vstore.search(
            query=query_text,
            k=top_k,
            search_type=search_mode,
            search_filter=search_filter
        )
        
        if not docs:
            return "日記に関連する情報が見つかりませんでした。"
        
        # 必要なら日付ソート
        if order == "desc":
            docs = sorted(docs, key=lambda d: d.metadata.get("date", ""), reverse=True)
        
        # Format the diary entries for better readability
        diary_entries = []
        for doc in docs:
            date_info = doc.metadata.get("date", "日付不明")
            diary_entries.append(f"【{date_info}】{doc.page_content}")
        
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
