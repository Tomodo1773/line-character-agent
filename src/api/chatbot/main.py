import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from chatbot.utils.config import logger
from chatbot.utils.cosmos import fetch_recent_chat_messages, save_chat_message
from chatbot.agent import ChatbotAgent

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
    logger.info("Message received.")
    try:
        background_tasks.add_task(handler.handle, body.decode("utf-8"), x_line_signature)
        logger.info("Added handler to background tasks.")  # Logging the addition of handler to background tasks
    except InvalidSignatureError:
        logger.error("Invalid signature detected.")  # Logging the detection of an invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info("Request processing completed successfully.")  # Logging using the logger
    return "ok"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:

        # user_idを取得
        try:
            chatId = event.source.user_id
        except AttributeError:
            logger.error("Failed to get user_id.")  # Logging the failure to get user_id
            raise HTTPException(status_code=400, detail="Failed to get user_id")

        line_bot_api = MessagingApi(api_client)

        logger.info(f"Received message: {event.message.text}")  # Log only the text part of the message

        # ローディングアニメーションを表示
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=chatId, loadingSeconds=60))
        logger.info("Displayed loading animation.")

        # CosmosDBから直近の会話履歴を取得
        history = fetch_recent_chat_messages()
        logger.info("Fetched recent chat history.")

        try:
            # LLMでレスポンスメッセージを作成
            agent_graph = ChatbotAgent()
            response = agent_graph.invoke(user_input=event.message.text, history=history)
            content = response["messages"][-1].content
            logger.info(f"Generated response: {content}")

            # メッセージを返信
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=content)])
            )
            logger.info("Replied message to the user.")

            # 会話履歴をCosmosDBに保存
            save_chat_message("human", event.message.text)
            save_chat_message("ai", content)
            logger.info("Saved conversation history.")

        except Exception as e:
            # メッセージを返信
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=e)])
            )
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
