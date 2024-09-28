import os

from chatbot.agent import ChatbotAgent
from chatbot.utils.config import logger
from chatbot.utils.cosmos import SaveComosDB
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, AudioMessageContent
from chatbot.audio import DiaryTranscription
from utils.line import LineMessenger

load_dotenv()

# アプリの設定
configuration = Configuration(access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
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

    # ローディングアニメーションを表示
    line_messennger.show_loading_animation()

    # CosmosDBから直近の会話履歴を取得
    cosmos = SaveComosDB()
    sessionid, messages = cosmos.fetch_messages()
    logger.info("Fetched recent chat history.")

    messages.append({"type": "human", "content": event.message.text})

    try:
        # LLMでレスポンスメッセージを作成
        agent_graph = ChatbotAgent()
        response = agent_graph.invoke(messages=messages)
        content = response["messages"][-1].content
        logger.info(f"Generated response: {content}")

        # メッセージを返信
        line_messennger.reply_message(content)

        cosmos.save_messages(event.source.user_id, sessionid, response["messages"])
        logger.info("Saved conversation history.")

    except Exception as e:
        # メッセージを返信
        error_message = f"Error {e.status_code}: {e.detail}"
        line_messennger.reply_message(error_message)
        logger.error(f"Returned error message to the user: {e}")


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    logger.info(f"Start handling audio message: {event.message.id}")
    line_messennger = LineMessenger(event)

    # ローディングアニメーションを表示
    line_messennger.show_loading_animation()

    # 音声データを取得
    audio = line_messennger.get_content()

    try:
        # audioから日記を取得
        content = DiaryTranscription().invoke(audio)
        # メッセージを返信
        line_messennger.reply_message(content)

    except Exception as e:
        # メッセージを返信
        error_message = f"Error {e.status_code}: {e.detail}"
        line_messennger.reply_message(error_message)
        logger.error(f"Returned error message to the user: {e}")

# @app.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     while True:
#         data = await websocket.receive_text()
#         logger.info(f"[Websocket]メッセージを受信しました: {data}")

#         # 受信したデータをJSONとしてパース
#         data_dict = json.loads(data)
#         logger.info(f"[Websocket]user_prompt: {data_dict['content']}")
#         # 'content'の値をgenerate_chat_responseに渡す
#         response = generate_chat_response(data_dict["content"])
#         logger.info(f"[Websocket]生成されたレスポンス: {response}")
#         response_json = {
#             "text": response,
#             "role": "assistant",
#             "emotion": "neutral"
#         }
#         await websocket.send_json(response_json)
#         logger.info(f"[Websocket]メッセージを送信しました")


if __name__ == "__main__":
    app.run()
