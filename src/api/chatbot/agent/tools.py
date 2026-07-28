from typing import Annotated

from azure.cosmos import CosmosClient, PartitionKey
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pydantic import Field

from chatbot.utils.config import create_logger

logger = create_logger(__name__)


# ---------------------------------------------------------------------------
# Embeddings (singleton)
# ---------------------------------------------------------------------------
_embeddings: OpenAIEmbeddings | None = None


def _get_embeddings() -> OpenAIEmbeddings:
    """OpenAIEmbeddings を遅延初期化して返す（シングルトン）。"""
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    return _embeddings


# ---------------------------------------------------------------------------
# Cosmos DB (diary search)
# ---------------------------------------------------------------------------
_cosmos_client = None
_cosmos_container = None


def initialize_cosmos_client(client: CosmosClient):
    """FastAPI startup 時に呼び出される CosmosClient 初期化関数。"""
    global _cosmos_client
    _cosmos_client = client
    logger.info("CosmosClient initialized for agent tools")


def get_cosmos_client() -> CosmosClient:
    """初期化済みの CosmosClient を取得。"""
    if _cosmos_client is None:
        raise RuntimeError("CosmosClient not initialized. Call initialize_cosmos_client() first.")
    return _cosmos_client


def _ensure_entries_container(database):
    """entriesコンテナを作成（存在しない場合のみ）"""
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [{"path": '/"_etag"/?'}, {"path": "/contentVector/*"}],
        "vectorIndexes": [{"path": "/contentVector", "type": "diskANN"}],
        "fullTextPolicy": {"defaultLanguage": "ja", "analyzers": [{"path": "/content", "language": "ja"}]},
    }
    vector_embedding_policy = {
        "vectorEmbeddings": [
            {"path": "/contentVector", "dataType": "float32", "dimensions": 1536, "distanceFunction": "cosine"}
        ]
    }
    try:
        database.create_container_if_not_exists(
            id="entries",
            partition_key=PartitionKey(path="/userId"),
            indexing_policy=indexing_policy,
            vector_embedding_policy=vector_embedding_policy,
            offer_throughput=400,
        )
        logger.info("entriesコンテナの準備が完了しました（database: diary）")
    except Exception as e:
        logger.error("entriesコンテナの作成/確認でエラーが発生しました: %s", e)
        raise


def get_cosmos_container():
    """CosmosDBコンテナを取得"""
    global _cosmos_container
    if _cosmos_container is None:
        client = get_cosmos_client()
        database = client.create_database_if_not_exists(id="diary")
        _ensure_entries_container(database)
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
    logger.info("ハイブリッド検索を実行: query_text=%s, top_k=%d", query_text, top_k)
    query_vector = _get_embeddings().embed_query(query_text)
    try:
        container = get_cosmos_container()
        keywords = [f'"{word.strip()}"' for word in query_text.split() if word.strip()]
        keywords_str = ", ".join(keywords)
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
        results = list(container.query_items(query=hybrid_search_query, enable_cross_partition_query=True))
        return results
    except Exception as e:
        logger.error("ハイブリッド検索エラー: %s", e)
        return _vector_search_with_embedding(query_vector, top_k, start_date, end_date)


def _vector_search_with_embedding(query_vector: list, top_k: int = 5, start_date: str = None, end_date: str = None):
    """既に計算済みのembeddingを使ったベクトル検索フォールバック"""
    logger.info("ベクトル検索フォールバックを実行: top_k=%d", top_k)
    try:
        container = get_cosmos_container()
        date_filter = _build_date_filter(start_date, end_date)

        vector_search_query = f"""
        SELECT TOP {top_k} c.id, c.content, c.date, c.metadata, c.userId,
               VectorDistance(c.contentVector, {query_vector}) AS SimilarityScore
        FROM c
        {date_filter}
        """
        results = list(container.query_items(query=vector_search_query, enable_cross_partition_query=True))
        return results
    except Exception as e:
        logger.error("ベクトル検索エラー: %s", e)
        return []


# ---------------------------------------------------------------------------
# Diary tools
# ---------------------------------------------------------------------------
@tool("diary-search-tool")
def diary_search_tool(
    query_text: Annotated[str, Field(description="検索したい自然文")],
    top_k: Annotated[int, Field(description="返す件数 (1-20)", ge=1, le=20)] = 5,
    start_date: Annotated[str | None, Field(description="絞り込み開始日 (YYYY-MM-DD形式)")] = None,
    end_date: Annotated[str | None, Field(description="絞り込み終了日 (YYYY-MM-DD形式)")] = None,
    order: Annotated[str, Field(description="日付の並べ替え方向")] = "asc",
) -> str:
    """キーワードや話題で日記を検索する。例: 「ラーメン食べた日」「最近の運動」。query_textに自然文を指定し、必要に応じて日付範囲で絞り込む。"""
    logger.info(
        "diary-search-tool実行: query_text=%s, top_k=%d, start_date=%s, end_date=%s", query_text, top_k, start_date, end_date
    )
    try:
        results = hybrid_search(query_text=query_text, top_k=top_k, start_date=start_date, end_date=end_date)
        if not results:
            return "日記に関連する情報が見つかりませんでした。"

        if order == "desc":
            results = sorted(results, key=lambda d: d.get("date", ""), reverse=True)

        diary_entries = []
        for result in results:
            date_info = result.get("date", "日付不明")
            content = result.get("content", "")
            similarity_score = result.get("SimilarityScore", 0)
            diary_entries.append(f"【{date_info}】{content} (類似度: {similarity_score:.3f})")

        return "\n\n".join(diary_entries)
    except Exception as e:
        return f"日記検索中にエラーが発生しました: {str(e)}"
