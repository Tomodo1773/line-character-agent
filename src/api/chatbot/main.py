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
from chatbot.audio import get_diary_from_audio
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
    print(body)
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
def handle_text(event):
    with ApiClient(configuration) as api_client:

        # user_idを取得
        userid = event.source.user_id

        line_bot_api = MessagingApi(api_client)

        logger.info(f"Received message: {event.message.text}")  # Log only the text part of the message

        # ローディングアニメーションを表示
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=userid, loadingSeconds=60))
        logger.info("Displayed loading animation.")

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
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=content)])
            )
            logger.info("Replied message to the user.")

            cosmos.save_messages(userid, sessionid, response["messages"])
            logger.info("Saved conversation history.")

        except Exception as e:
            # メッセージを返信
            error_message = f"Error {e.status_code}: {e.detail}"
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=error_message)])
            )
            logger.error(f"Returned error message to the user: {e}")


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    with ApiClient(configuration) as api_client:
        logger.info("start handle_audio")

        # user_idを取得
        userid = event.source.user_id
        line_bot_api = MessagingApi(api_client)
        line_bot_api_blob = MessagingApiBlob(api_client)

        # ローディングアニメーションを表示
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=userid, loadingSeconds=60))
        logger.info("Displayed loading animation.")

        audio = line_bot_api_blob.get_message_content(event.message.id)

        try:
            # audioから日記を取得
            content = get_diary_from_audio(audio)

            # メッセージを返信
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=content)])
            )
            logger.info("Replied message to the user.")

        except Exception as e:
            # メッセージを返信
            error_message = f"Error {e.status_code}: {e.detail}"
            line_bot_api_blob.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=error_message)])
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
