import os
import json
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

from utils.chat import generate_chat_response
from utils.config import logger

load_dotenv()

# アプリの設定
configuration = Configuration(access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
chatId = os.environ.get("LINE_USER_ID")

app = FastAPI(
    title="LINEBOT-AI-AGENT",
    description="LINEBOT-AI-AGENT by FastAPI.",
)


@app.post("/callback")
async def callback(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature=Header(None),
):
    body = await request.body()
    logger.info(f"受信したリクエストボディ: {body.decode('utf-8')}")  # loggerを使用してログ出力

    try:
        background_tasks.add_task(handler.handle, body.decode("utf-8"), x_line_signature)
        logger.info("バックグラウンドタスクにハンドラを追加しました。")  # loggerを使用してログ出力
    except InvalidSignatureError:
        logger.error("無効な署名が検出されました。")  # loggerを使用してログ出力
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info("リクエスト処理が正常に完了しました。")  # loggerを使用してログ出力
    return "ok"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # ローディングアニメーションを表示
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=chatId, loadingSeconds=60))
        logger.info("ローディングアニメーションを表示しました。")

        # OpenAIでレスポンスメッセージを作成
        response = generate_chat_response(event.message.text)
        logger.info(f"生成されたレスポンス: {response}")

        # メッセージを返信
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=response)])
        )
        logger.info("メッセージをユーザーに返信しました。")


@app.get("/hello")
async def hello():
    return {"message": "hello world!"}


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
