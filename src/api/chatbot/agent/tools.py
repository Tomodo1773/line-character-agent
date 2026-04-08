import datetime

from azure.cosmos import CosmosClient, PartitionKey
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

from chatbot.utils.config import create_logger
from chatbot.utils.diary_utils import generate_diary_filename
from chatbot.utils.google_drive import GoogleDriveHandler

logger = create_logger(__name__)

_embeddings: OpenAIEmbeddings | None = None


def _get_embeddings() -> OpenAIEmbeddings:
    """OpenAIEmbeddings を遅延初期化して返す（シングルトン）。"""
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    return _embeddings


class DiarySearchInput(BaseModel):
    query_text: str = Field(description="検索したい自然文")
    top_k: int | None = Field(default=5, description="返す件数 (1-20)", ge=1, le=20)
    start_date: str | None = Field(default=None, description="絞り込み開始日 (YYYY-MM-DD形式)")
    end_date: str | None = Field(default=None, description="絞り込み終了日 (YYYY-MM-DD形式)")
    order: str | None = Field(default="asc", description="日付の並べ替え方向")


# Cosmos DB接続用のグローバル変数（FastAPI startup 時に初期化）
_cosmos_client = None
_cosmos_container = None


def initialize_cosmos_client(client: CosmosClient):
    """FastAPI startup 時に呼び出される CosmosClient 初期化関数。

    Args:
        client: 共有する CosmosClient インスタンス
    """
    global _cosmos_client
    _cosmos_client = client
    logger.info("CosmosClient initialized for agent tools")


def get_cosmos_client() -> CosmosClient:
    """初期化済みの CosmosClient を取得。

    Returns:
        CosmosClient: 共有 CosmosClient インスタンス

    Raises:
        RuntimeError: CosmosClient が未初期化の場合
    """
    if _cosmos_client is None:
        raise RuntimeError("CosmosClient not initialized. Call initialize_cosmos_client() first.")
    return _cosmos_client


def _ensure_entries_container(database):
    """entriesコンテナを作成（存在しない場合のみ）"""
    # インデックスポリシー（infra/core/db/indexing-policy.jsonと同じ内容）
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [{"path": '/"_etag"/?'}, {"path": "/contentVector/*"}],
        "vectorIndexes": [{"path": "/contentVector", "type": "diskANN"}],
        "fullTextPolicy": {"defaultLanguage": "ja", "analyzers": [{"path": "/content", "language": "ja"}]},
    }

    # ベクトル埋め込みポリシー（infra/core/db/vector-embedding-policy.jsonと同じ内容）
    vector_embedding_policy = {
        "vectorEmbeddings": [
            {"path": "/contentVector", "dataType": "float32", "dimensions": 1536, "distanceFunction": "cosine"}
        ]
    }

    try:
        # コンテナを作成（存在しない場合のみ）
        database.create_container_if_not_exists(
            id="entries",
            partition_key=PartitionKey(path="/userId"),
            indexing_policy=indexing_policy,
            vector_embedding_policy=vector_embedding_policy,
            offer_throughput=400,  # 400 RU/s
        )
        logger.info("entriesコンテナの準備が完了しました（database: diary）")
    except Exception as e:
        logger.error(f"entriesコンテナの作成/確認でエラーが発生しました: {str(e)}")
        raise


def get_cosmos_container():
    """CosmosDBコンテナを取得"""
    global _cosmos_container
    if _cosmos_container is None:
        client = get_cosmos_client()
        # `get_database_client` は DB が存在しない場合でもハンドルを返すだけで、
        # その後のコンテナ作成が 404 で落ちる。まず DB を確実に作る。
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
    try:
        query_vector = _get_embeddings().embed_query(query_text)

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
        logger.error("ハイブリッド検索エラー: %s", e)
        # フォールバック: ベクトル検索のみ
        return vector_search_fallback(query_text, top_k, start_date, end_date)


def vector_search_fallback(query_text: str, top_k: int = 5, start_date: str = None, end_date: str = None):
    """フォールバック用のベクトル検索実装"""
    logger.info("ベクトル検索フォールバックを実行: query_text=%s, top_k=%d", query_text, top_k)
    try:
        query_vector = _get_embeddings().embed_query(query_text)

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
        logger.error("ベクトル検索エラー: %s", e)
        return []


@tool("diary-search-tool", args_schema=DiarySearchInput)
def diary_search_tool(
    query_text: str,
    top_k: int = 5,
    start_date: str | None = None,
    end_date: str | None = None,
    order: str = "asc",
) -> str:
    """キーワードや話題で日記を検索する。例: 「ラーメン食べた日」「最近の運動」。query_textに自然文を指定し、必要に応じて日付範囲で絞り込む。"""
    logger.info(
        "diary-search-tool実行: query_text=%s, top_k=%d, start_date=%s, end_date=%s", query_text, top_k, start_date, end_date
    )
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


class DiaryDriveInput(BaseModel):
    date: str = Field(description="取得したい日記の日付 (YYYY-MM-DD形式)")


def create_diary_drive_tool(drive_handler: GoogleDriveHandler):
    """GoogleDriveHandler をクロージャでキャプチャした日記取得ツールを生成する。"""

    @tool("diary-drive-tool", args_schema=DiaryDriveInput)
    def diary_drive_tool(date: str) -> str:
        """特定の日付の日記をGoogle Driveから取得する。「昨日の日記」「2025年3月1日の日記」のように日付が明確なときに使う。日付はYYYY-MM-DD形式で指定する。"""
        logger.info("diary-drive-tool実行: date=%s", date)
        try:
            target_date = datetime.date.fromisoformat(date)
            filename = generate_diary_filename(target_date)
            year = str(target_date.year)

            year_folder_id = drive_handler.find_folder(year)
            if not year_folder_id:
                return f"{filename}の日記が見つかりませんでした。"

            file_id = drive_handler.find_file_id(f"{filename}.md", year_folder_id)
            if not file_id:
                return f"{filename}の日記が見つかりませんでした。"

            content = drive_handler.get_file_content(file_id)
            if not content:
                return f"{filename}の日記ファイルは存在しますが、内容が空でした。"

            return f"【{filename}の日記】\n{content}"
        except ValueError:
            return f"日付の形式が正しくありません: {date}（YYYY-MM-DD形式で指定してください）"
        except Exception as e:
            return f"Google Driveからの日記取得中にエラーが発生しました: {str(e)}"

    return diary_drive_tool


class DiaryCreateInput(BaseModel):
    date: str = Field(description="日記の対象日付 (YYYY-MM-DD形式)")
    content: str = Field(description="日記の内容 (Markdown形式)")


def create_diary_create_tool(drive_handler: GoogleDriveHandler):
    """GoogleDriveHandler をクロージャでキャプチャした日記作成ツールを生成する。"""

    @tool("diary-create-tool", args_schema=DiaryCreateInput)
    def diary_create_tool(date: str, content: str) -> str:
        """新しい日記をGoogle Driveに作成する。ユーザとの会話から日記の内容をMarkdown形式で生成し、日付と内容を指定して保存する。日付はYYYY-MM-DD形式で指定する。"""
        logger.info("diary-create-tool実行: date=%s", date)
        try:
            target_date = datetime.date.fromisoformat(date)
            filename = generate_diary_filename(target_date)
            year = str(target_date.year)

            year_folder_id = drive_handler.find_or_create_folder(year)

            # 既存ファイルチェック
            file_id = drive_handler.find_file_id(f"{filename}.md", year_folder_id)
            if file_id:
                return f"{filename}の日記は既に存在します。更新する場合はdiary-update-toolを使ってください。"

            saved_id = drive_handler.save_markdown(content, f"{filename}.md", year_folder_id)
            if saved_id:
                return f"{filename}の日記をGoogle Driveに保存しました。"
            return "日記の保存に失敗しました。"
        except ValueError:
            return f"日付の形式が正しくありません: {date}（YYYY-MM-DD形式で指定してください）"
        except Exception as e:
            return f"日記の作成中にエラーが発生しました: {str(e)}"

    return diary_create_tool


class DiaryUpdateInput(BaseModel):
    date: str = Field(description="更新したい日記の対象日付 (YYYY-MM-DD形式)")
    content: str = Field(description="更新後の日記の全文 (Markdown形式)")


def create_diary_update_tool(drive_handler: GoogleDriveHandler):
    """GoogleDriveHandler をクロージャでキャプチャした日記更新ツールを生成する。"""

    @tool("diary-update-tool", args_schema=DiaryUpdateInput)
    def diary_update_tool(date: str, content: str) -> str:
        """既存の日記を更新する。まずdiary-drive-toolで既存内容を取得し、修正・追記した全文をcontentに渡して上書き保存する。日付はYYYY-MM-DD形式で指定する。"""
        logger.info("diary-update-tool実行: date=%s", date)
        try:
            target_date = datetime.date.fromisoformat(date)
            filename = generate_diary_filename(target_date)
            year = str(target_date.year)

            year_folder_id = drive_handler.find_folder(year)
            if not year_folder_id:
                return f"{filename}の日記が見つかりませんでした。新規作成する場合はdiary-create-toolを使ってください。"

            file_id = drive_handler.find_file_id(f"{filename}.md", year_folder_id)
            if not file_id:
                return f"{filename}の日記が見つかりませんでした。新規作成する場合はdiary-create-toolを使ってください。"

            success = drive_handler.update_markdown(file_id, content)
            if success:
                return f"{filename}の日記を更新しました。"
            return "日記の更新に失敗しました。"
        except ValueError:
            return f"日付の形式が正しくありません: {date}（YYYY-MM-DD形式で指定してください）"
        except Exception as e:
            return f"日記の更新中にエラーが発生しました: {str(e)}"

    return diary_update_tool
