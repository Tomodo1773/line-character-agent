import asyncio
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager

# Azure Application Insights imports
from azure.monitor.opentelemetry import configure_azure_monitor
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import TextMessage
from linebot.v3.webhooks import AudioMessageContent, MessageEvent, TextMessageContent
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from psycopg import OperationalError as PsycopgOperationalError
from psycopg_pool import AsyncConnectionPool

from chatbot.agent import ChatbotAgent
from chatbot.agent.diary_workflow import DiaryWorkflowError, get_diary_workflow
from chatbot.database.repositories import UserRepository
from chatbot.models import (
    ChatCompletionRequest,
    ChatCompletionStreamResponse,
    ChatCompletionStreamResponseChoice,
    ChatCompletionStreamResponseChoiceDelta,
)
from chatbot.utils.agent_response import extract_agent_text
from chatbot.utils.auth import verify_api_key
from chatbot.utils.config import check_environment_variables, create_logger, get_env_variable
from chatbot.utils.google_auth import GoogleDriveOAuthManager
from chatbot.utils.line import LineMessenger

load_dotenv()

logger = create_logger(__name__)
# FastAPI アプリケーションのイベントループ（AsyncPostgresSaver と共有する）
event_loop = None
# 環境変数のチェック
is_valid, missing_vars = check_environment_variables()
if not is_valid:
    logger.error("Required environment variables are not set. Exiting application.")
    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI アプリのライフサイクルで AsyncPostgresSaver を管理する

    AsyncConnectionPool を使用して、長時間アイドル後の接続タイムアウトエラーを防ぐ。
    プールが接続の再確立を自動的に行うため、PaaS 環境でも安定して動作する。
    """
    global event_loop
    event_loop = asyncio.get_running_loop()
    conn_string = get_env_variable("POSTGRES_CHECKPOINT_URL")

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

        yield

    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL connection pool: {e}")
        raise
    finally:
        # アプリシャットダウン時にプールをクローズ
        await pool.close()
        logger.info("PostgreSQL connection pool closed")


# アプリの設定
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

app = FastAPI(
    title="LINEBOT-AI-AGENT",
    description="LINEBOT-AI-AGENT by FastAPI.",
    lifespan=lifespan,
)

# Azure Application Insightsの初期化
APPLICATIONINSIGHTS_CONNECTION_STRING = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if APPLICATIONINSIGHTS_CONNECTION_STRING:
    configure_azure_monitor(connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING)
    FastAPIInstrumentor.instrument_app(app)


@app.get("/")
async def root():
    return {"message": "The server is up and running."}


@app.get("/auth/google/callback")
async def google_drive_oauth_callback(code: str, state: str):
    user_repository = UserRepository()
    # state には userid を渡している前提
    userid = state
    user_data = user_repository.fetch_user(userid)
    if not user_data:
        logger.warning("No user found for the provided state; prompting user to restart OAuth.")
        return {"message": "ユーザー情報が見つからなかったよ。もう一度LINEからOAuthをやり直してね。"}

    # セッションIDが既に保存されていればそれを使い、なければ新規に発行する
    session_id = user_data.get("session_id")
    if not session_id:
        session = user_repository.ensure_session(userid)
        session_id = session.session_id

    oauth_manager = GoogleDriveOAuthManager(user_repository)
    line_messenger = LineMessenger(user_id=userid)

    try:
        credentials = oauth_manager.exchange_code_for_credentials(code)
        oauth_manager.save_user_credentials(userid, credentials)

        agent = ChatbotAgent(checkpointer=app.state.checkpointer)
        resume_messages = [{"type": "human", "content": "Google DriveのOAuth設定が完了しました"}]
        response = await agent.ainvoke(messages=resume_messages, userid=userid, session_id=session_id)
        reply_text, is_interrupt = extract_agent_text(response)
        line_messenger.push_message([TextMessage(text=reply_text)])

        return {
            "message": "Authorization completed and conversation resumed."
            if not is_interrupt
            else "Authorization completed and awaiting additional input."
        }

    except (ValueError, HTTPException) as e:
        logger.error(f"Failed to handle OAuth callback: {e}")
        fallback_message = (
            "Google DriveのOAuth設定は完了したけど、会話の再開に失敗しちゃった。続きが必要ならメッセージを送ってね。"
        )
        line_messenger.push_message([TextMessage(text=fallback_message)])
        return {"message": "Authorization completed but resume failed."}
    except Exception as e:
        logger.exception(f"Unexpected error in OAuth callback: {e}")
        fallback_message = "予期しないエラーが発生しました。もう一度試してね。"
        line_messenger.push_message([TextMessage(text=fallback_message)])
        return {"message": "Authorization completed but resume failed."}


@app.post("/callback")
async def callback(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature=Header(None),
):
    body = await request.body()

    logger.info(f"Message received. event: {body.decode('utf-8')}")  # Logging the received message
    try:
        background_tasks.add_task(handler.handle, body.decode("utf-8"), x_line_signature)
        logger.info("Added handler to background tasks.")  # Logging the addition of handler to background tasks
    except InvalidSignatureError:
        logger.error("Invalid signature detected.")  # Logging the detection of an invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info("Request processing completed successfully.")  # Logging using the logger
    return "ok"


def get_user_credentials(userid: str, user_repository: UserRepository):
    """ユーザーのGoogle認可情報を取得する"""
    user_repository.ensure_user(userid)
    oauth_manager = GoogleDriveOAuthManager(user_repository)
    return oauth_manager.get_user_credentials(userid)


async def handle_text_async(event):
    logger.info(f"Start handling text message: {event.message.text}")
    line_messenger = LineMessenger(event)
    user_repository = UserRepository()
    userid = event.source.user_id
    session = user_repository.ensure_session(userid)
    agent = ChatbotAgent(checkpointer=app.state.checkpointer)

    # ローディングアニメーションを表示
    line_messenger.show_loading_animation()

    try:
        messages = [{"type": "human", "content": event.message.text}]
        if await agent.has_pending_interrupt(session.session_id):
            response = await agent.aresume(session.session_id, event.message.text)
        else:
            response = await agent.ainvoke(messages=messages, userid=userid, session_id=session.session_id)

        reply_text, _ = extract_agent_text(response)
        logger.info(f"Generated text response: {reply_text}")

        reply_messages = [TextMessage(text=reply_text)]
        line_messenger.reply_message(reply_messages)

    except PsycopgOperationalError as e:
        # PostgreSQL接続エラー（タイムアウト等）の場合
        logger.error(f"PostgreSQL connection error: {e}")
        error_message = "データベース接続でエラーが発生しちゃった。少し時間をおいてもう一度試してね。"
        line_messenger.reply_message([TextMessage(text=error_message)])

    except Exception as e:
        # メッセージを返信
        if hasattr(e, "status_code") and hasattr(e, "detail"):
            error_message = f"Error {e.status_code}: {e.detail}"
        else:
            error_message = f"Error: {str(e)}"
        line_messenger.reply_message([TextMessage(text=error_message)])
        logger.error(f"Returned error message to the user: {e}")


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    if event_loop is None:
        logger.error("Event loop is not initialized. Cannot handle text message.")
        return
    asyncio.run_coroutine_threadsafe(handle_text_async(event), event_loop)


async def handle_audio_async(event):
    logger.info(f"Start handling audio message: {event.message.id}")
    line_messenger = LineMessenger(event)
    user_repository = UserRepository()
    userid = event.source.user_id
    session = user_repository.ensure_session(userid)

    # ローディングアニメーションを表示
    line_messenger.show_loading_animation()

    # 音声データを取得
    audio = line_messenger.get_content()

    workflow = get_diary_workflow(agent_checkpointer=app.state.checkpointer)
    try:
        result = await workflow.ainvoke(
            {"messages": [], "userid": userid, "session_id": session.session_id, "audio": audio},
            {"configurable": {"thread_id": session.session_id}},
        )

        if result.get("__interrupt__"):
            interrupt_message, _ = extract_agent_text(result)
            line_messenger.reply_message([TextMessage(text=interrupt_message)])
            return

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
            fallback, _ = extract_agent_text(result)
            reply_texts.append(fallback)

        reply_messages = [TextMessage(text=text) for text in reply_texts]
        line_messenger.reply_message(reply_messages)

        if saved_filename:
            logger.info(f"Saved diary to Google Drive: {saved_filename}")

    except DiaryWorkflowError as e:
        # ワークフロー内でのドメインエラーはメッセージとしてそのままユーザーに返す
        error_message = str(e)
        line_messenger.reply_message([TextMessage(text=error_message)])
        logger.error(f"Diary workflow error: {e}")
    except PsycopgOperationalError as e:
        logger.error(f"PostgreSQL connection error during audio processing: {e}")
        error_message = "データベース接続でエラーが発生しちゃった。少し時間をおいてもう一度試してね。"
        line_messenger.reply_message([TextMessage(text=error_message)])

    except Exception as e:
        error_message = f"Error: {e}"
        line_messenger.reply_message([TextMessage(text=error_message)])
        logger.error(f"Returned error message to the user: {e}")


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    if event_loop is None:
        logger.error("Event loop is not initialized. Cannot handle audio message.")
        return
    asyncio.run_coroutine_threadsafe(handle_audio_async(event), event_loop)


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header or not api_key_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )

    api_key = api_key_header.replace("Bearer ", "")
    if not verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return api_key


@app.post("/v1/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    api_key: str = Depends(get_api_key),
):
    """OpenAI互換のチャット補完APIエンドポイント"""
    user_repository = UserRepository()
    userid = "openai-compatible-api-user"
    session = user_repository.ensure_session(userid)

    # request.messagesをdict形式に変換
    messages = [{"type": msg.role.value, "content": msg.content} for msg in request.messages]

    agent = ChatbotAgent(checkpointer=app.state.checkpointer)

    async def generate_stream():
        stream_id = f"chatcmpl-{str(uuid.uuid4())}"
        created = int(time.time())

        start_response = ChatCompletionStreamResponse(
            id=stream_id,
            created=created,
            choices=[
                ChatCompletionStreamResponseChoice(
                    index=0,
                    delta=ChatCompletionStreamResponseChoiceDelta(role="assistant"),
                    finish_reason=None,
                )
            ],
        )
        yield f"data: {start_response.model_dump_json()}\n\n"

        try:
            if await agent.has_pending_interrupt(session.session_id):
                response = await agent.aresume(session.session_id, messages[-1]["content"])
            else:
                response = await agent.ainvoke(messages=messages, userid=userid, session_id=session.session_id)

            reply_text, _ = extract_agent_text(response)
            chunk_response = ChatCompletionStreamResponse(
                id=stream_id,
                created=created,
                choices=[
                    ChatCompletionStreamResponseChoice(
                        index=0,
                        delta=ChatCompletionStreamResponseChoiceDelta(content=reply_text),
                        finish_reason=None,
                    )
                ],
            )
            yield f"data: {chunk_response.model_dump_json()}\n\n"

            end_response = ChatCompletionStreamResponse(
                id=stream_id,
                created=created,
                choices=[
                    ChatCompletionStreamResponseChoice(
                        index=0,
                        delta=ChatCompletionStreamResponseChoiceDelta(),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {end_response.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        },
    )


if __name__ == "__main__":
    app.run()
