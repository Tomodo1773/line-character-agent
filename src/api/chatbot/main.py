import asyncio
import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import TextMessage
from linebot.v3.webhooks import AudioMessageContent, MessageEvent, TextMessageContent
from psycopg import OperationalError as PsycopgOperationalError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from google.oauth2.credentials import Credentials

from chatbot.agent import ChatbotAgent
from chatbot.agent.diary_workflow import DiaryWorkflowError, get_diary_workflow
from chatbot.database.repositories import OAuthStateRepository, UserRepository
from chatbot.dependencies import (
    create_oauth_state_repository,
    create_user_repository,
    get_oauth_manager,
    get_oauth_state_repository,
)
from chatbot.utils.drive_folder import extract_drive_folder_id
from chatbot.utils.config import create_logger, get_env_variable
from chatbot.utils.google_auth import GoogleDriveOAuthManager
from chatbot.utils.google_drive import GoogleDriveHandler
from chatbot.utils.line import LineMessenger

load_dotenv()

logger = create_logger(__name__)
# FastAPI アプリケーションのイベントループ（AsyncPostgresSaver と共有する）
event_loop = None


def _handle_error(e: Exception, line_messenger: LineMessenger) -> None:
    """例外をユーザー向けメッセージに変換して LINE に返信する。"""
    if isinstance(e, DiaryWorkflowError):
        error_message = str(e)
    elif isinstance(e, PsycopgOperationalError):
        logger.error(f"PostgreSQL connection error: {e}")
        error_message = "データベース接続でエラーが発生しちゃった。少し時間をおいてもう一度試してね。"
    elif isinstance(e, HTTPException):
        error_message = f"Error {e.status_code}: {e.detail}"
    else:
        error_message = "予期しないエラーが発生しちゃった。少し時間をおいてもう一度試してね。"
    line_messenger.reply_message([TextMessage(text=error_message)])
    logger.error(f"Returned error message to the user: {e}")


def _get_effective_userid(original_userid: str) -> str:
    """
    ローカル開発時にユーザーIDを上書きする。

    環境変数 LOCAL_USER_ID が設定されている場合、LINE webhookから取得した
    user_idをその値で上書きする。これによりローカル環境では本番とは別の
    Google DriveフォルダやOAuth認証情報を使用できる。

    Args:
        original_userid: LINE webhookから取得したuser_id

    Returns:
        str: 有効なuser_id（LOCAL_USER_IDが設定されていればその値、なければ元の値）
    """
    local_user_id = os.getenv("LOCAL_USER_ID")
    if local_user_id:
        return local_user_id
    return original_userid


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI アプリのライフサイクルで AsyncPostgresSaver を管理する

    AsyncConnectionPool を使用して、長時間アイドル後の接続タイムアウトエラーを防ぐ。
    プールが接続の再確立を自動的に行うため、PaaS 環境でも安定して動作する。
    """
    global event_loop
    event_loop = asyncio.get_running_loop()

    # LangChain トレーシング設定（既存値があれば上書きしない）
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "LINE-AI-BOT")

    conn_string = get_env_variable("POSTGRES_CHECKPOINT_URL")

    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }

    # 接続プールを初期化
    # 個人利用かつトラフィックが少ない前提のため max_size は 3 に抑える。
    # Azure App Service / Neon Postgres では長時間アイドルした接続がサーバ側で切断されやすく、
    # 切断済みのコネクションを再利用しようとすると「長時間放置後の最初の1リクエストだけ SSL 接続エラー」
    # が発生することがある。そのため、min_size=0 / max_idle=60 としてアイドル接続を積極的にクローズし、
    # アイドル後のリクエストでは新規接続が張られやすくなるようにしている。
    pool = AsyncConnectionPool(
        conninfo=conn_string,
        min_size=0,
        max_size=3,
        max_idle=60,
        open=False,
        kwargs=connection_kwargs,
    )

    try:
        # プールを開く
        await pool.open()
        logger.info("PostgreSQL connection pool opened successfully")

        # プールを使って AsyncPostgresSaver を初期化
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver initialized with connection pool")

        app.state.checkpointer = checkpointer
        app.state.pool = pool

        # CosmosClient を初期化
        from chatbot.database.core import _create_cosmos_client, init_oauth_states_container, init_users_container

        cosmos_client = _create_cosmos_client()
        logger.info("CosmosClient initialized")

        # users コンテナを初期化
        users_container = init_users_container(cosmos_client)
        app.state.users_container = users_container
        logger.info("Users container initialized")

        # oauth_states コンテナを初期化（TTL 600 秒）
        oauth_states_container = init_oauth_states_container(cosmos_client)
        app.state.oauth_states_container = oauth_states_container
        logger.info("OAuth states container initialized")

        # agent tools の CosmosClient も初期化
        from chatbot.agent.tools import initialize_cosmos_client

        initialize_cosmos_client(cosmos_client)

        yield

    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL connection pool: {e}")
        raise
    finally:
        # アプリシャットダウン時にプールをクローズ
        await pool.close()
        logger.info("PostgreSQL connection pool closed")


# デコレータでハンドラ登録するためモジュールレベルで初期化が必要。
# テスト時に環境変数が未設定でもインポートできるようデフォルト値を空文字にしている。
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET", ""))

app = FastAPI(
    title="LINEBOT-AI-AGENT",
    description="LINEBOT-AI-AGENT by FastAPI.",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {"message": "The server is up and running."}


@app.get("/auth/google/callback")
async def google_drive_oauth_callback(
    code: str,
    state: str,
    oauth_state_repository: OAuthStateRepository = Depends(get_oauth_state_repository),
    oauth_manager: GoogleDriveOAuthManager = Depends(get_oauth_manager),
):
    # ランダムな state をキーに userid と code_verifier を引き当てて即削除（ワンタイム消費）
    consumed = oauth_state_repository.consume_state(state)
    if not consumed:
        logger.warning("OAuth callback received with unknown or expired state.")
        return {"message": "認可リンクの有効期限が切れたか、無効なstateだよ。もう一度LINEからOAuthをやり直してね。"}

    userid = consumed["userid"]
    code_verifier = consumed["code_verifier"]

    # ローカル開発時は LOCAL_LINE_USER_ID を使用（LINE APIに送信するため正式なLINE user IDが必要）
    line_user_id = os.getenv("LOCAL_LINE_USER_ID") or userid
    line_messenger = LineMessenger(user_id=line_user_id)

    try:
        credentials = oauth_manager.exchange_code_for_credentials(code, code_verifier)
        oauth_manager.save_user_credentials(userid, credentials)

        line_messenger.push_message([TextMessage(text="Google Driveの認証が完了したよ。メッセージを送ってね。")])
        return {"message": "Authorization completed."}

    except Exception as e:
        logger.exception(f"Unexpected error in OAuth callback: {e}")
        fallback_message = "OAuth認証でエラーが発生しました。もう一度試してね。"
        line_messenger.push_message([TextMessage(text=fallback_message)])
        return {"message": "Authorization failed."}


@app.post("/callback")
async def callback(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature=Header(None),
):
    body = await request.body()

    logger.info("Message received.")
    try:
        background_tasks.add_task(handler.handle, body.decode("utf-8"), x_line_signature)
        logger.info("Added handler to background tasks.")
    except InvalidSignatureError:
        logger.error("Invalid signature detected.")
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info("Request processing completed successfully.")
    return "ok"


def _check_oauth(
    user_repository: UserRepository,
    oauth_state_repository: OAuthStateRepository,
    userid: str,
    line_messenger: LineMessenger,
) -> Credentials | None:
    """OAuth 認証情報を検証し、未設定なら認証URLを返信して None を返す。"""
    oauth_manager = GoogleDriveOAuthManager(user_repository)
    credentials = oauth_manager.get_user_credentials(userid)
    if not credentials:
        # CSRF 対策のランダム state を発行し、oauth_states コンテナに userid と code_verifier を紐付けて保存する。
        state = secrets.token_urlsafe(32)
        auth_url, code_verifier = oauth_manager.generate_authorization_url(state)
        oauth_state_repository.save_state(state, userid, code_verifier)
        line_messenger.reply_message(
            [
                TextMessage(text="Google Drive へのアクセス許可がまだ設定されていないみたい。\n以下のURLから認可してね。"),
                TextMessage(text=auth_url),
            ]
        )
    return credentials


def _check_folder_id(user_repository: UserRepository, userid: str, line_messenger: LineMessenger) -> str | None:
    """フォルダID を検証し、未設定なら入力を促すメッセージを返信して None を返す。"""
    folder_id = user_repository.fetch_drive_folder_id(userid)
    if not folder_id:
        message = (
            "Google Driveで使う日記フォルダのIDを教えて。\ndrive.google.comのフォルダURLを貼るか、フォルダIDだけを送ってね。"
        )
        line_messenger.reply_message([TextMessage(text=message)])
    return folder_id


def _schedule_coroutine(coro, *, description: str) -> None:
    future = asyncio.run_coroutine_threadsafe(coro, event_loop)

    def _done_callback(f):
        try:
            f.result()
        except Exception:
            logger.exception(f"Unhandled exception in scheduled task: {description}")

    future.add_done_callback(_done_callback)


async def handle_text_async(event):
    logger.info(f"Start handling text message: {event.message.text[:20]}…")
    try:
        logger.info("Initializing LineMessenger and UserRepository")
        line_messenger = LineMessenger(event)
        userid = _get_effective_userid(event.source.user_id)
        user_repository = create_user_repository(app.state.users_container)
        oauth_state_repository = create_oauth_state_repository(app.state.oauth_states_container)

        # 会話履歴リセットのキーワードをチェック
        if event.message.text.strip() == "閑話休題":
            logger.info(f"Resetting session for user {userid}")
            session = user_repository.reset_session(userid)
            logger.info(f"Session reset for user {userid}. New session_id: {session.session_id}")
            line_messenger.reply_message([TextMessage(text="会話履歴をリセットしたよ。新しい気持ちで話そうね！")])
            return

        # OAuth / フォルダ ID の事前チェック
        if not _check_oauth(user_repository, oauth_state_repository, userid, line_messenger):
            return

        folder_id = user_repository.fetch_drive_folder_id(userid)
        if not folder_id:
            # テキストが Drive URL/ID として解釈できれば登録
            extracted_id = extract_drive_folder_id(event.message.text.strip())
            if extracted_id:
                user_repository.save_drive_folder_id(userid, extracted_id)
                line_messenger.reply_message([TextMessage(text="フォルダIDを設定したよ。これで準備完了！")])
            else:
                message = "Google Driveで使う日記フォルダのIDを教えて。\ndrive.google.comのフォルダURLを貼るか、フォルダIDだけを送ってね。"
                line_messenger.reply_message([TextMessage(text=message)])
            return

        logger.info(f"Ensuring session for user {userid}")
        session = user_repository.ensure_session(userid)
        # ローディングアニメーションを表示
        logger.info("Showing loading animation")
        line_messenger.show_loading_animation()

        logger.info("Initializing ChatbotAgent with checkpointer")
        agent = await ChatbotAgent.create(checkpointer=app.state.checkpointer)

        messages = [{"type": "human", "content": event.message.text}]
        logger.info(f"Invoking agent for session_id: {session.session_id}")
        response = await agent.ainvoke(
            messages=messages, userid=userid, session_id=session.session_id, user_repository=user_repository
        )

        logger.info("Extracting agent response text")
        reply_text = response["messages"][-1].text
        logger.info(f"Generated text response: {reply_text[:20]}…")

        logger.info("Sending reply message")
        reply_messages = [TextMessage(text=reply_text)]
        line_messenger.reply_message(reply_messages)

    except Exception as e:
        _handle_error(e, line_messenger)


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    if event_loop is None:
        logger.error("Event loop is not initialized. Cannot handle text message.")
        return
    _schedule_coroutine(handle_text_async(event), description="handle_text_async")


async def handle_audio_async(event):
    logger.info(f"Start handling audio message: {event.message.id}")
    try:
        logger.info("Initializing LineMessenger and UserRepository")
        line_messenger = LineMessenger(event)
        userid = _get_effective_userid(event.source.user_id)
        user_repository = create_user_repository(app.state.users_container)
        oauth_state_repository = create_oauth_state_repository(app.state.oauth_states_container)

        # ローディングアニメーションを表示
        logger.info("Showing loading animation")
        line_messenger.show_loading_animation()

        # OAuth / フォルダ ID の事前チェック
        credentials = _check_oauth(user_repository, oauth_state_repository, userid, line_messenger)
        if not credentials:
            return

        folder_id = _check_folder_id(user_repository, userid, line_messenger)
        if not folder_id:
            return

        drive_handler = GoogleDriveHandler(credentials=credentials, folder_id=folder_id)

        logger.info(f"Ensuring session for user {userid}")
        session = user_repository.ensure_session(userid)

        # 音声データを取得
        logger.info("Getting audio content from LINE")
        audio = line_messenger.get_content()
        logger.info("Audio content retrieved successfully")

        logger.info("Getting diary workflow")
        workflow = get_diary_workflow(agent_checkpointer=app.state.checkpointer)
        logger.info("Invoking diary workflow")

        result = await workflow.ainvoke(
            {
                "messages": [],
                "userid": userid,
                "session_id": session.session_id,
                "audio": audio,
            },
            {
                "configurable": {
                    "thread_id": session.session_id,
                    "user_repository": user_repository,
                    "drive_handler": drive_handler,
                }
            },
        )

        logger.info("Processing workflow results")
        diary_text = result.get("diary_text")
        saved_filename = result.get("saved_filename")
        message_updates = result.get("messages") or []

        reply_texts: list[str] = []
        if diary_text:
            reply_texts.append(diary_text)

        for message in message_updates:
            content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
            if content:
                reply_texts.append(str(content))

        if not reply_texts:
            fallback = result["messages"][-1].text
            reply_texts.append(fallback)

        logger.info("Sending reply messages")
        reply_messages = [TextMessage(text=text) for text in reply_texts]
        line_messenger.reply_message(reply_messages)

        if saved_filename:
            logger.info(f"Saved diary to Google Drive: {saved_filename}")

    except Exception as e:
        _handle_error(e, line_messenger)


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    if event_loop is None:
        logger.error("Event loop is not initialized. Cannot handle audio message.")
        return
    _schedule_coroutine(handle_audio_async(event), description="handle_audio_async")


if __name__ == "__main__":
    app.run()
