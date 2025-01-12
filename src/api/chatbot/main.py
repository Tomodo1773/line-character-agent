import os
import sys

from chatbot.agent import ChatbotAgent
from chatbot.database import AgentCosmosDB
from chatbot.utils.config import logger, check_environment_variables
from chatbot.utils.line import LineMessenger
from chatbot.utils.nijivoice import NijiVoiceClient
from chatbot.utils.transcript import DiaryTranscription
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import AudioMessage, TextMessage
from linebot.v3.webhooks import AudioMessageContent, MessageEvent, TextMessageContent

load_dotenv()

# 環境変数のチェック
is_valid, missing_vars = check_environment_variables()
if not is_valid:
    logger.error("必要な環境変数が設定されていません。アプリケーションを終了します。")
    logger.error(f"未設定の環境変数: {', '.join(missing_vars)}")
    sys.exit(1)

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
    agent = ChatbotAgent()
    nijivoice = NijiVoiceClient()

    # ローディングアニメーションを表示
    line_messennger.show_loading_animation()

    # CosmosDBから直近の会話履歴を取得
    session = cosmos.fetch_messages()
    messages = session.full_contents
    messages.append({"type": "human", "content": event.message.text})

    logger.info("Fetched recent chat history.")

    try:
        # LLMでレスポンスメッセージを作成
        response = agent.invoke(messages=messages, userid=userid)
        content = response["messages"][-1].content
        logger.info(f"Generated text response: {content}")

        # 音声を生成
        voice_response = nijivoice.generate(content)
        audio_url = voice_response["generatedVoice"]["audioFileUrl"]
        duration = voice_response["generatedVoice"]["duration"]
        logger.info(f"Generated voice response: {audio_url}")

        # メッセージを返信
        reply_messages = [
            TextMessage(text=content),
            AudioMessage(
                original_content_url=audio_url,
                duration=duration
            ),
        ]
        line_messennger.reply_message(reply_messages)

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
    messages = []
    agent = ChatbotAgent()
    nijivoice = NijiVoiceClient()

    # ローディングアニメーションを表示
    line_messennger.show_loading_animation()

    # 音声データを取得
    audio = line_messennger.get_content()

    try:
        # audioから日記を取得
        diary_content = DiaryTranscription().invoke(audio)
        reaction_prompt = f"""以下の日記に対して一言だけ感想を言って。
内容全部に対してコメントしなくていいから、一番印象に残った部分についてコメントして。
{diary_content}
"""
        messages.append({"type": "human", "content": reaction_prompt})
        logger.info(f"Generated diary transcription")

        # キャラクターのコメントを追加
        response = agent.invoke(messages=messages, userid=userid)
        reaction = response["messages"][-1].content
        logger.info(f"Generated character response: {reaction}")

        # 音声を生成
        voice_response = nijivoice.generate(reaction)
        audio_url = voice_response["generatedVoice"]["audioFileUrl"]
        duration = voice_response["generatedVoice"]["duration"]
        logger.info(f"Generated voice response: {audio_url}")

        # メッセージを返信
        reply_messages = [
            TextMessage(text=diary_content)  # 日記の内容は常に送信
        ]
        if reaction:
            reply_messages.extend([
                TextMessage(text=reaction),
                AudioMessage(
                    original_content_url=audio_url,
                    duration=duration
                )
            ])
        line_messennger.reply_message(reply_messages)

        # メッセージを保存
        messages.append({"type": "ai", "content": reaction})
        print(messages)
        add_messages = messages
        cosmos.add_messages(userid, add_messages)

    except Exception as e:
        # メッセージを返信
        error_message = f"Error: {e}"
        line_messennger.reply_message([error_message])
        logger.error(f"Returned error message to the user: {e}")


if __name__ == "__main__":
    app.run()
