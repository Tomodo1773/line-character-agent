import json
import os
import sys

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from langchain import hub
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import AudioMessage, TextMessage
from linebot.v3.webhooks import AudioMessageContent, MessageEvent, TextMessageContent

from chatbot.agent import ChatbotAgent, get_user_profile
from chatbot.database.repositories import AgentRepository
from chatbot.utils.auth import verify_token_ws
from chatbot.utils.config import check_environment_variables, create_logger
from chatbot.utils.diary_utils import generate_diary_digest, save_diary_to_drive, save_digest_to_drive
from chatbot.utils.line import LineMessenger
from chatbot.utils.nijivoice import NijiVoiceClient
from chatbot.utils.transcript import DiaryTranscription
from chatbot.websocket import ConnectionManager

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
    cosmos = AgentRepository()
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
            AudioMessage(original_content_url=audio_url, duration=duration),
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
    cosmos = AgentRepository()
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
        logger.info("Generated diary transcription")

        saved_filename = save_diary_to_drive(diary_content)
        if saved_filename:
            logger.info(f"Saved diary to Google Drive: {saved_filename}")

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
        reply_messages = [TextMessage(text=diary_content)]  # 日記の内容は常に送信

        if saved_filename:
            save_message = f"日記を'{saved_filename}'に保存したわよ。"
            reply_messages.append(TextMessage(text=save_message))

        if reaction:
            reply_messages.extend(
                [TextMessage(text=reaction), AudioMessage(original_content_url=audio_url, duration=duration)]
            )
        line_messennger.reply_message(reply_messages)

        # メッセージを保存
        messages.append({"type": "ai", "content": reaction})
        add_messages = messages
        cosmos.add_messages(userid, add_messages)

        try:
            if saved_filename:
                digest = generate_diary_digest(diary_content)
                if digest:
                    success = save_digest_to_drive(digest, saved_filename)
                    if success:
                        logger.info("Saved digest successfully")
                    else:
                        logger.error("Failed to save digest")
        except Exception as e:
            logger.error(f"Error occurred during digest processing: {e}")

    except Exception as e:
        # メッセージを返信
        error_message = f"Error: {e}"
        line_messennger.reply_message([error_message])
        logger.error(f"Returned error message to the user: {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # JWT認証を実行
    is_valid, token, userid = await verify_token_ws(websocket)
    if not is_valid:
        return

    # 事前にキャッシュ
    cached = {
        "prompts": {
            "tomodo1773/character-agent-router": hub.pull("tomodo1773/character-agent-router"),
            "tomodo1773/sister_edinet": hub.pull("tomodo1773/sister_edinet"),
            "tomodo1773/create_web_search_query": hub.pull("tomodo1773/create_web_search_query"),
            "tomodo1773/create_diary_search_query": hub.pull("tomodo1773/create_diary_search_query"),
        },
        "profile": {userid: get_user_profile(userid)},
    }

    cosmos = AgentRepository()
    agent = ChatbotAgent(cached=cached)
    manager = ConnectionManager(agent=agent, cosmos_repository=cosmos)

    # 検証済みトークンをサブプロトコルとして使用
    await manager.connect(websocket, subprotocol=token)
    try:
        while True:
            # CosmosDBから直近の会話履歴を取得
            session = cosmos.fetch_messages()
            messages = session.full_contents

            data = await websocket.receive_text()
            logger.info(f"[Websocket] Received message: {data}")

            # 受信したデータをJSONとしてパース
            data_dict = json.loads(data)
            logger.info(f"[Websocket]user_prompt: {data_dict['content']}")
            messages.append({"type": "human", "content": data_dict["content"]})

            # LLMでレスポンスメッセージを作成
            response = await agent.ainvoke(messages=messages, userid=userid)
            content = response["messages"][-1].content

            await manager.process_and_send_messages(content, websocket, data_dict["type"])

            # 会話履歴を保存
            add_messages = [{"type": "human", "content": data_dict["content"]}, {"type": "ai", "content": content}]
            cosmos.add_messages(userid, add_messages)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        await websocket.close()
        logger.info("[Websocket] Connection closed.")


if __name__ == "__main__":
    app.run()
