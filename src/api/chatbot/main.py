import asyncio
import os
import sys
import time
import uuid

# Azure Application Insights imports
from azure.monitor.opentelemetry import configure_azure_monitor
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    FlexBlockStyle,
    FlexBox,
    FlexBubble,
    FlexBubbleStyles,
    FlexButton,
    FlexMessage,
    FlexText,
    TextMessage,
    URIAction,
)
from linebot.v3.webhooks import AudioMessageContent, MessageEvent, TextMessageContent
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from chatbot.agent import ChatbotAgent
from chatbot.database.repositories import AgentRepository, UserRepository
from chatbot.models import (
    ChatCompletionRequest,
    ChatCompletionStreamResponse,
    ChatCompletionStreamResponseChoice,
    ChatCompletionStreamResponseChoiceDelta,
)
from chatbot.utils.auth import verify_api_key
from chatbot.utils.config import check_environment_variables, create_logger
from chatbot.utils.diary_utils import generate_diary_digest, save_diary_to_drive, save_digest_to_drive
from chatbot.utils.google_auth import GoogleDriveOAuthManager
from chatbot.utils.google_drive import GoogleDriveHandler
from chatbot.utils.line import LineMessenger
from chatbot.utils.transcript import DiaryTranscription

load_dotenv()

logger = create_logger(__name__)
# 環境変数のチェック
is_valid, missing_vars = check_environment_variables()
if not is_valid:
    logger.error("Required environment variables are not set. Exiting application.")
    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

# アプリの設定
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

app = FastAPI(
    title="LINEBOT-AI-AGENT",
    description="LINEBOT-AI-AGENT by FastAPI.",
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
    user_repository.ensure_user(state)
    oauth_manager = GoogleDriveOAuthManager(user_repository)
    credentials = oauth_manager.exchange_code_for_credentials(code)
    oauth_manager.save_user_credentials(state, credentials)

    completion_message = "GoogleDriveの許可設定が完了したわ。最初のメッセージをもう一度送ってね。"
    line_messenger = LineMessenger(user_id=state)
    line_messenger.push_message([TextMessage(text=completion_message)])

    return {"message": "Authorization completed. Please resend your first message on LINE."}


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


def create_google_drive_auth_flex_message(auth_url: str) -> FlexMessage:
    """Google Drive OAuth認証を促すFlex Messageを作成する

    Args:
        auth_url: Google OAuth認証ページのURL

    Returns:
        FlexMessage: Google Drive連携を促すフレックスメッセージ
    """
    header = FlexBox(
        layout="vertical",
        contents=[
            FlexText(text="Google Drive 連携", weight="bold", color="#1f1f1f", size="xl"),
        ],
    )
    body = FlexBox(
        layout="vertical",
        contents=[
            FlexText(
                text="Botの機能を利用するには、Google Driveへのアクセス権限が必要よ。まずは以下から許可設定して。",
                wrap=True,
                color="#666666",
                size="sm",
            )
        ],
        spacing="md",
    )
    footer = FlexBox(
        layout="vertical",
        spacing="sm",
        contents=[
            FlexButton(
                style="primary",
                height="sm",
                action=URIAction(label="認証ページへ進む", uri=auth_url),
                color="#0F9D58",
            )
        ],
        flex=0,
    )

    bubble = FlexBubble(
        size="kilo",
        header=header,
        body=body,
        footer=footer,
        styles=FlexBubbleStyles(header=FlexBlockStyle(separator=False)),
    )

    return FlexMessage(alt_text="Google Drive連携の設定", contents=bubble)


def get_user_credentials_or_prompt(userid: str, line_messenger: LineMessenger, user_repository: UserRepository):
    """ユーザーのGoogle認可情報を取得し、未認可なら認可URLを返信して処理を終了する"""
    user_repository.ensure_user(userid)
    oauth_manager = GoogleDriveOAuthManager(user_repository)
    credentials = oauth_manager.get_user_credentials(userid)

    if not credentials:
        auth_url, _ = oauth_manager.generate_authorization_url(userid)
        flex_message = create_google_drive_auth_flex_message(auth_url)
        line_messenger.reply_message([flex_message])
        return None

    return credentials


async def handle_text_async(event):
    logger.info(f"Start handling text message: {event.message.text}")
    line_messenger = LineMessenger(event)
    cosmos = AgentRepository()
    user_repository = UserRepository()
    userid = event.source.user_id
    credentials = get_user_credentials_or_prompt(userid, line_messenger, user_repository)
    if not credentials:
        return

    agent = ChatbotAgent()

    # ローディングアニメーションを表示
    line_messenger.show_loading_animation()

    # CosmosDBから直近の会話履歴を取得
    session = cosmos.fetch_messages()
    messages = session.full_contents
    messages.append({"type": "human", "content": event.message.text})

    logger.info("Fetched recent chat history.")

    try:
        # LLMでレスポンスメッセージを作成
        response = await agent.ainvoke(messages=messages, userid=userid)
        content = response["messages"][-1].content
        logger.info(f"Generated text response: {content}")

        # メッセージを返信
        reply_messages = [TextMessage(text=content)]
        line_messenger.reply_message(reply_messages)

        # 会話履歴を保存
        add_messages = [{"type": "human", "content": event.message.text}, {"type": "ai", "content": content}]
        cosmos.add_messages(userid, add_messages)

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
    asyncio.run(handle_text_async(event))


async def handle_audio_async(event):
    logger.info(f"Start handling audio message: {event.message.id}")
    line_messenger = LineMessenger(event)
    cosmos = AgentRepository()
    user_repository = UserRepository()
    userid = event.source.user_id
    credentials = get_user_credentials_or_prompt(userid, line_messenger, user_repository)
    if not credentials:
        return

    drive_handler = GoogleDriveHandler(credentials=credentials)
    messages = []
    agent = ChatbotAgent()

    # ローディングアニメーションを表示
    line_messenger.show_loading_animation()

    # 音声データを取得
    audio = line_messenger.get_content()

    try:
        # audioから日記を取得
        diary_content = DiaryTranscription(drive_handler).invoke(audio)
        reaction_prompt = f"""以下の日記に対して一言だけ感想を言って。
内容全部に対してコメントしなくていいから、一番印象に残った部分についてコメントして。
{diary_content}
"""
        messages.append({"type": "human", "content": reaction_prompt})
        logger.info("Generated diary transcription")

        saved_filename = save_diary_to_drive(diary_content, drive_handler)
        if saved_filename:
            logger.info(f"Saved diary to Google Drive: {saved_filename}")

        # キャラクターのコメントを追加（非同期化）
        response = await agent.ainvoke(messages=messages, userid=userid)
        reaction = response["messages"][-1].content
        logger.info(f"Generated character response: {reaction}")

        # メッセージを返信
        reply_messages = [TextMessage(text=diary_content)]  # 日記の内容は常に送信

        if saved_filename:
            save_message = f"日記を'{saved_filename}'に保存したわよ。"
            reply_messages.append(TextMessage(text=save_message))

        if reaction:
            reply_messages.append(TextMessage(text=reaction))
        line_messenger.reply_message(reply_messages)

        # メッセージを保存
        messages.append({"type": "ai", "content": reaction})
        add_messages = messages
        cosmos.add_messages(userid, add_messages)

        try:
            if saved_filename:
                digest = generate_diary_digest(diary_content)
                if digest:
                    success = save_digest_to_drive(digest, saved_filename, drive_handler)
                    if success:
                        logger.info("Saved digest successfully")
                    else:
                        logger.error("Failed to save digest")
        except Exception as e:
            logger.error(f"Error occurred during digest processing: {e}")

    except Exception as e:
        # メッセージを返信
        error_message = f"Error: {e}"
        line_messenger.reply_message([TextMessage(text=error_message)])
        logger.error(f"Returned error message to the user: {e}")


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    asyncio.run(handle_audio_async(event))


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

    # CosmosDBから直近の会話履歴を取得
    cosmos = AgentRepository()
    session = cosmos.fetch_messages()
    db_history = session.full_contents.copy() if session.full_contents else []

    # request.messagesをdict形式に変換
    req_msgs = [{"type": msg.role.value, "content": msg.content} for msg in request.messages]

    # 履歴に新規分をappend
    messages = db_history + req_msgs

    userid = "openai-compatible-api-user"
    agent = ChatbotAgent()

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

        ai_response_content = ""
        try:
            async for msg, metadata in agent.astream(messages=messages, userid=userid):
                if msg.content and metadata["langgraph_node"] == "chatbot":
                    ai_response_content += msg.content[0]["text"]
                    chunk_response = ChatCompletionStreamResponse(
                        id=stream_id,
                        created=created,
                        choices=[
                            ChatCompletionStreamResponseChoice(
                                index=0,
                                delta=ChatCompletionStreamResponseChoiceDelta(content=msg.content[0]["text"]),
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

        # 新規分+AIレスポンスだけを保存
        save_msgs = req_msgs.copy()
        if ai_response_content:
            save_msgs.append({"type": "ai", "content": ai_response_content})
        if save_msgs:
            cosmos.add_messages(userid, save_msgs)

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
