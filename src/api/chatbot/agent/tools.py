import datetime
from typing import Annotated, Any

from azure.cosmos import CosmosClient, PartitionKey
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pydantic import Field

from chatbot.utils.config import create_logger
from chatbot.utils.diary_utils import generate_diary_digest, generate_diary_filename, save_digest_to_drive
from chatbot.utils.google_auth import GoogleDriveOAuthManager
from chatbot.utils.google_drive import GoogleDriveHandler

logger = create_logger(__name__)


def _get_injected_args(config: RunnableConfig) -> tuple[str, Any]:
    """RunnableConfig から userid と user_repository を取り出す。"""
    configurable = config.get("configurable", {})
    userid = configurable["userid"]
    user_repository = configurable["user_repository"]
    return userid, user_repository


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
# Google Drive handler & cache
# ---------------------------------------------------------------------------
_cached: dict = {"profile": {}, "digest": {}}


def _create_drive_handler(userid: str, user_repository) -> GoogleDriveHandler | None:
    """ユーザのOAuth認証情報からGoogleDriveHandlerを生成する。取得できない場合はNoneを返す。"""
    auth_manager = GoogleDriveOAuthManager(user_repository)
    credentials = auth_manager.get_user_credentials(userid)
    if not credentials:
        logger.warning("Google Drive credentials not found for user: %s", userid)
        return None

    folder_id = user_repository.fetch_drive_folder_id(userid)
    if not folder_id:
        logger.warning("Google Drive folder ID not found for user: %s", userid)
        return None

    return GoogleDriveHandler(credentials=credentials, folder_id=folder_id)


def _get_cached_drive_content(userid: str, user_repository, cache_key: str, fetch_fn) -> str:
    """Google Drive からコンテンツを取得しキャッシュする汎用関数。"""
    global _cached
    if userid not in _cached[cache_key]:
        logger.info("Fetching %s from Google Drive as it is not cached: %s", cache_key, userid)
        drive_handler = _create_drive_handler(userid, user_repository)
        if not drive_handler:
            _cached[cache_key][userid] = ""
            return ""

        result = fetch_fn(drive_handler)
        if result and "content" in result:
            _cached[cache_key][userid] = result["content"]
        else:
            logger.error("Failed to get %s content, using empty value", cache_key)
            _cached[cache_key][userid] = ""
    return _cached[cache_key].get(userid, "")


def _get_user_profile(userid: str, user_repository) -> str:
    """キャッシュされたユーザプロフィール情報を取得、なければGoogle Driveから取得"""
    from chatbot.utils.google_drive_utils import get_profile_from_drive

    return _get_cached_drive_content(userid, user_repository, "profile", get_profile_from_drive)


def _get_user_digest(userid: str, user_repository) -> str:
    """キャッシュされたユーザダイジェスト情報を取得、なければGoogle Driveから取得"""
    from chatbot.utils.google_drive_utils import get_digest_from_drive

    return _get_cached_drive_content(userid, user_repository, "digest", get_digest_from_drive)


# ---------------------------------------------------------------------------
# Profile / Digest tools
# ---------------------------------------------------------------------------
@tool
def read_profile(config: RunnableConfig) -> str:
    """ユーザのプロフィール情報をGoogle Driveから取得する。ユーザの基本情報や好みを知りたいときに使う。"""
    userid, user_repository = _get_injected_args(config)
    logger.info("read_profile実行: userid=%s", userid)
    return _get_user_profile(userid, user_repository) or "プロフィール情報が見つかりませんでした。"


@tool
def read_digest(config: RunnableConfig) -> str:
    """ユーザの直近の出来事ダイジェストをGoogle Driveから取得する。最近の話題や文脈を知りたいときに使う。"""
    userid, user_repository = _get_injected_args(config)
    logger.info("read_digest実行: userid=%s", userid)
    return _get_user_digest(userid, user_repository) or "ダイジェスト情報が見つかりませんでした。"


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
def _parse_diary_date(date: str) -> tuple[datetime.date, str, str]:
    """日付文字列をパースし (target_date, filename, year) を返す。ValueError は呼び出し元で処理。"""
    target_date = datetime.date.fromisoformat(date)
    filename = generate_diary_filename(target_date)
    year = str(target_date.year)
    return target_date, filename, year


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


@tool("diary-drive-tool")
def diary_drive_tool(
    date: Annotated[str, Field(description="取得したい日記の日付 (YYYY-MM-DD形式)")],
    config: RunnableConfig,
) -> str:
    """特定の日付の日記をGoogle Driveから取得する。「昨日の日記」「2025年3月1日の日記」のように日付が明確なときに使う。日付はYYYY-MM-DD形式で指定する。"""
    userid, user_repository = _get_injected_args(config)
    logger.info("diary-drive-tool実行: date=%s", date)
    drive_handler = _create_drive_handler(userid, user_repository)
    if not drive_handler:
        return "Google Drive に接続できませんでした。"
    try:
        _, filename, year = _parse_diary_date(date)

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


@tool("diary-create-tool")
def diary_create_tool(
    date: Annotated[str, Field(description="日記の対象日付 (YYYY-MM-DD形式)")],
    content: Annotated[str, Field(description="日記の内容 (Markdown形式)")],
    config: RunnableConfig,
) -> str:
    """新しい日記をGoogle Driveに作成する。ユーザとの会話から日記の内容をMarkdown形式で生成し、日付と内容を指定して保存する。日付はYYYY-MM-DD形式で指定する。"""
    userid, user_repository = _get_injected_args(config)
    logger.info("diary-create-tool実行: date=%s", date)
    drive_handler = _create_drive_handler(userid, user_repository)
    if not drive_handler:
        return "Google Drive に接続できませんでした。"
    try:
        _, filename, year = _parse_diary_date(date)

        year_folder_id = drive_handler.find_or_create_folder(year)

        file_id = drive_handler.find_file_id(f"{filename}.md", year_folder_id)
        if file_id:
            return f"{filename}の日記は既に存在します。更新する場合はdiary-update-toolを使ってください。"

        saved_id = drive_handler.save_markdown(content, f"{filename}.md", year_folder_id)
        if saved_id:
            url = f"https://drive.google.com/file/d/{saved_id}/view"
            return f"{filename}の日記をGoogle Driveに保存しました。\n{url}"
        return "日記の保存に失敗しました。"
    except ValueError:
        return f"日付の形式が正しくありません: {date}（YYYY-MM-DD形式で指定してください）"
    except Exception as e:
        return f"日記の作成中にエラーが発生しました: {str(e)}"


@tool("diary-update-tool")
def diary_update_tool(
    date: Annotated[str, Field(description="更新したい日記の対象日付 (YYYY-MM-DD形式)")],
    content: Annotated[str, Field(description="更新後の日記の全文 (Markdown形式)")],
    config: RunnableConfig,
) -> str:
    """既存の日記を更新する。まずdiary-drive-toolで既存内容を取得し、修正・追記した全文をcontentに渡して上書き保存する。日付はYYYY-MM-DD形式で指定する。"""
    userid, user_repository = _get_injected_args(config)
    logger.info("diary-update-tool実行: date=%s", date)
    drive_handler = _create_drive_handler(userid, user_repository)
    if not drive_handler:
        return "Google Drive に接続できませんでした。"
    try:
        _, filename, year = _parse_diary_date(date)

        year_folder_id = drive_handler.find_folder(year)
        if not year_folder_id:
            return f"{filename}の日記が見つかりませんでした。新規作成する場合はdiary-create-toolを使ってください。"

        file_id = drive_handler.find_file_id(f"{filename}.md", year_folder_id)
        if not file_id:
            return f"{filename}の日記が見つかりませんでした。新規作成する場合はdiary-create-toolを使ってください。"

        success = drive_handler.update_markdown(file_id, content)
        if success:
            url = f"https://drive.google.com/file/d/{file_id}/view"
            return f"{filename}の日記を更新しました。\n{url}"
        return "日記の更新に失敗しました。"
    except ValueError:
        return f"日付の形式が正しくありません: {date}（YYYY-MM-DD形式で指定してください）"
    except Exception as e:
        return f"日記の更新中にエラーが発生しました: {str(e)}"


@tool("diary-digest-tool")
def diary_digest_tool(
    date: Annotated[str, Field(description="日記の対象日付 (YYYY-MM-DD形式)")],
    content: Annotated[str, Field(description="日記の本文テキスト")],
    config: RunnableConfig,
) -> str:
    """日記のダイジェスト（2-5語の要約）を生成しGoogle Driveに保存する。日記の作成・更新後に呼び出す。"""
    userid, user_repository = _get_injected_args(config)
    logger.info("diary-digest-tool実行: date=%s", date)
    drive_handler = _create_drive_handler(userid, user_repository)
    if not drive_handler:
        return "Google Drive に接続できませんでした。"
    try:
        _, filename, _ = _parse_diary_date(date)

        digest = generate_diary_digest(content)
        if not digest:
            return "ダイジェストの生成に失敗しました。"

        saved = save_digest_to_drive(digest, filename, drive_handler)
        if saved:
            return f"ダイジェストを保存しました: {digest}"
        return "ダイジェストの保存に失敗しました。"
    except ValueError:
        return f"日付の形式が正しくありません: {date}（YYYY-MM-DD形式で指定してください）"
    except Exception as e:
        return f"ダイジェスト生成中にエラーが発生しました: {str(e)}"
