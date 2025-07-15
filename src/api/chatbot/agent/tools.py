import os
from typing import Optional

from azure.cosmos import CosmosClient
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

load_dotenv()


class DiarySearchInput(BaseModel):
    query_text: str = Field(description="検索したい自然文")
    top_k: Optional[int] = Field(default=5, description="返す件数 (1-20)", ge=1, le=20)
    start_date: Optional[str] = Field(default=None, description="絞り込み開始日 (YYYY-MM-DD形式)")
    end_date: Optional[str] = Field(default=None, description="絞り込み終了日 (YYYY-MM-DD形式)")
    order: Optional[str] = Field(default="asc", description="日付の並べ替え方向")


# Cosmos DB接続用のシングルトン
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


def _build_date_filter(start_date: str = None, end_date: str = None) -> str:
    """日付フィルタ条件を構築"""
    conditions = []
    if start_date:
        conditions.append(f'c.date >= "{start_date}"')
    if end_date:
        conditions.append(f'c.date <= "{end_date}"')

    return " WHERE " + " AND ".join(conditions) if conditions else ""


def hybrid_search(query_text: str, top_k: int = 5, start_date: str = None, end_date: str = None):
    """ハイブリッド検索実装（ベクトル検索 + BM25フルテキスト検索）"""
    try:
        # 埋め込みを作成
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        query_vector = embeddings.embed_query(query_text)

        # コンテナを取得
        container = get_cosmos_container()

        # 検索キーワードをパースして引用符で囲む
        keywords = [f'"{word.strip()}"' for word in query_text.split() if word.strip()]
        keywords_str = ", ".join(keywords)

        # ハイブリッド検索クエリを構築
        date_filter = _build_date_filter(start_date, end_date)

        hybrid_search_query = f"""
        SELECT TOP {top_k} c.id, c.content, c.date, c.metadata, c.userId,
               0.0 AS SimilarityScore
        FROM c
        {date_filter}
        ORDER BY RANK RRF(
            VectorDistance(c.contentVector, {query_vector}),
            FullTextScore(c.content, {keywords_str})
        )
        """

        # クエリを実行
        results = list(container.query_items(query=hybrid_search_query, enable_cross_partition_query=True))
        return results

    except Exception as e:
        print(f"ハイブリッド検索エラー: {str(e)}")
        # フォールバック: ベクトル検索のみ
        return vector_search_fallback(query_text, top_k, start_date, end_date)


def vector_search_fallback(query_text: str, top_k: int = 5, start_date: str = None, end_date: str = None):
    """フォールバック用のベクトル検索実装"""
    try:
        # 埋め込みを作成
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        query_vector = embeddings.embed_query(query_text)

        # コンテナを取得
        container = get_cosmos_container()

        # ベクトル検索クエリを構築
        date_filter = _build_date_filter(start_date, end_date)

        vector_search_query = f"""
        SELECT TOP {top_k} c.id, c.content, c.date, c.metadata, c.userId,
               VectorDistance(c.contentVector, {query_vector}) AS SimilarityScore
        FROM c
        {date_filter}
        """

        # クエリを実行
        results = list(container.query_items(query=vector_search_query, enable_cross_partition_query=True))
        return results

    except Exception as e:
        print(f"ベクトル検索エラー: {str(e)}")
        return []


@tool("diary-search-tool", args_schema=DiarySearchInput)
def diary_search_tool(
    query_text: str,
    top_k: int = 5,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    order: str = "asc",
) -> str:
    """ユーザの日記コレクションをハイブリッド検索し、条件に合うエントリを返す"""
    try:
        # ハイブリッド検索を実行
        results = hybrid_search(query_text=query_text, top_k=top_k, start_date=start_date, end_date=end_date)

        if not results:
            return "日記に関連する情報が見つかりませんでした。"

        # 必要なら日付ソート
        if order == "desc":
            results = sorted(results, key=lambda d: d.get("date", ""), reverse=True)

        # 結果をフォーマット
        diary_entries = []
        for result in results:
            date_info = result.get("date", "日付不明")
            content = result.get("content", "")
            similarity_score = result.get("SimilarityScore", 0)
            diary_entries.append(f"【{date_info}】{content} (類似度: {similarity_score:.3f})")

        return "\n\n".join(diary_entries)

    except Exception as e:
        return f"日記検索中にエラーが発生しました: {str(e)}"
