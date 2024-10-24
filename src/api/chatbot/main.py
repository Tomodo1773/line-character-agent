import os

from chatbot.agent import ChatbotAgent
from chatbot.audio import DiaryReaction, DiaryTranscription

# from chatbot.utils.cosmos import SaveComosDB
from chatbot.database import AgentCosmosDB
from chatbot.utils.config import logger
from chatbot.utils.line import LineMessenger
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import AudioMessageContent, MessageEvent, TextMessageContent

load_dotenv()

# アプリの設定
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

app = FastAPI(
    title="LINEBOT-AI-AGENT",
    description="LINEBOT-AI-AGENT by FastAPI.",
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

    logger.info(f"Message received. event: {body.decode('utf-8')}")  # Logging the received message
    try:
        background_tasks.add_task(handler.handle, body.decode("utf-8"), x_line_signature)
        logger.info("Added handler to background tasks.")  # Logging the addition of handler to background tasks
    except InvalidSignatureError:
        logger.error("Invalid signature detected.")  # Logging the detection of an invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info("Request processing completed successfully.")  # Logging using the logger
    return "ok"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    logger.info(f"Start handling text message: {event.message.text}")
    line_messennger = LineMessenger(event)
    cosmos = AgentCosmosDB()
    userid = event.source.user_id
    agent = ChatbotAgent(userid)

    # ローディングアニメーションを表示
    line_messennger.show_loading_animation()

    # CosmosDBから直近の会話履歴を取得
    session = cosmos.fetch_messages()
    messages = session.full_contents
    messages.append({"type": "human", "content": event.message.text})

    logger.info("Fetched recent chat history.")

    try:
        # LLMでレスポンスメッセージを作成

        response = agent.invoke(messages=messages)
        content = response["messages"][-1].content
        logger.info(f"Generated response: {content}")

        # メッセージを返信
        line_messennger.reply_message([content])

        # 会話履歴を保存
        add_messages = [{"type": "human", "content": event.message.text}, {"type": "ai", "content": content}]
        cosmos.add_messages(userid, add_messages)

    except Exception as e:
        # メッセージを返信
        error_message = f"Error {e.status_code}: {e.detail}"
        line_messennger.reply_message([error_message])
        logger.error(f"Returned error message to the user: {e}")


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    logger.info(f"Start handling audio message: {event.message.id}")
    line_messennger = LineMessenger(event)
    cosmos = AgentCosmosDB()
    userid = event.source.user_id

    # ローディングアニメーションを表示
    line_messennger.show_loading_animation()

    # 音声データを取得
    audio = line_messennger.get_content()

    try:
        # audioから日記を取得
        diary_content = DiaryTranscription().invoke(audio)
        logger.info(f"Generated diary transcription")

        # キャラクターのコメントを追加
        reaction = DiaryReaction(userid).invoke(diary_content)
        logger.info(f"Generated character response: {reaction}")

        # メッセージを返信
        messages = [diary_content]
        if reaction:
            messages.append(reaction)
        line_messennger.reply_message(messages)

        # メッセージを保存
        add_messages = [{"type": "human", "content": diary_content}, {"type": "ai", "content": reaction}]
        cosmos.add_messages(userid, add_messages)

    except Exception as e:
        # メッセージを返信
        error_message = f"Error: {e}"
        line_messennger.reply_message([error_message])
        logger.error(f"Returned error message to the user: {e}")


if __name__ == "__main__":
    app.run()
