import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from chatbot.agent import ChatbotAgent
from chatbot.dependencies import create_user_repository
from chatbot.utils.config import create_logger
from chatbot.utils.line import LineMessenger

load_dotenv()

logger = create_logger(__name__)
# FastAPI アプリケーションのイベントループ（webhook ハンドラのタスク投入に使う）
event_loop = None


def _handle_error(e: Exception, line_messenger: LineMessenger) -> None:
    """例外をユーザー向けメッセージに変換して LINE に返信する。"""
    if isinstance(e, HTTPException):
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
    ユーザーデータを使用できる。

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
    """FastAPI アプリのライフサイクルで Cosmos DB クライアントを初期化する。"""
    global event_loop
    event_loop = asyncio.get_running_loop()

    from chatbot.agent.tools import initialize_cosmos_client
    from chatbot.database.core import _create_cosmos_client, init_users_container

    cosmos_client = _create_cosmos_client()
    logger.info("CosmosClient initialized")

    app.state.users_container = init_users_container(cosmos_client)
    logger.info("Users container initialized")

    initialize_cosmos_client(cosmos_client)

    yield


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

        # 会話履歴リセットのキーワードをチェック
        if event.message.text.strip() == "閑話休題":
            logger.info(f"Resetting session for user {userid}")
            session = user_repository.reset_session(userid)
            logger.info(f"Session reset for user {userid}. New session_id: {session.session_id}")
            line_messenger.reply_message([TextMessage(text="会話履歴をリセットしたよ。新しい気持ちで話そうね！")])
            return

        logger.info(f"Ensuring session for user {userid}")
        session = user_repository.ensure_session(userid)
        # ローディングアニメーションを表示
        logger.info("Showing loading animation")
        line_messenger.show_loading_animation()

        logger.info("Initializing ChatbotAgent")
        agent = await ChatbotAgent.create()

        messages = [{"type": "human", "content": event.message.text}]
        logger.info(f"Invoking agent for session_id: {session.session_id}")
        response = await agent.ainvoke(messages=messages, userid=userid, session_id=session.session_id)

        logger.info("Extracting agent response text")
        reply_text = response["messages"][-1].text
        logger.info(f"Generated text response: {reply_text[:20]}…")

        logger.info("Sending reply message")
        line_messenger.reply_message([TextMessage(text=reply_text)])

    except Exception as e:
        _handle_error(e, line_messenger)


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    if event_loop is None:
        logger.error("Event loop is not initialized. Cannot handle text message.")
        return
    _schedule_coroutine(handle_text_async(event), description="handle_text_async")


if __name__ == "__main__":
    app.run()
