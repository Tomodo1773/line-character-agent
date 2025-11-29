import os

from dotenv import load_dotenv
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
)
from linebot.v3.webhooks import MessageEvent

from chatbot.utils.config import create_logger

logger = create_logger(__name__)

load_dotenv()


class LineMessenger:
    def __init__(self, event: MessageEvent | None = None, user_id: str | None = None) -> None:
        line_api_configuration = Configuration(access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))

        self.line_api_client = ApiClient(line_api_configuration)
        self.line_api = MessagingApi(self.line_api_client)
        self.line_api_blob = MessagingApiBlob(self.line_api_client)
        if event:
            self.user_id = event.source.user_id
            self.reply_token = event.reply_token
            self.message_id = event.message.id
        elif user_id:
            self.user_id = user_id
            self.reply_token = None
            self.message_id = None
        else:
            raise ValueError("Either event or user_id must be provided")

    def show_loading_animation(self) -> None:
        self.line_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=self.user_id, loadingSeconds=60))
        logger.info("Displayed loading animation.")

    def reply_message(self, messages_list: list) -> None:
        if not self.reply_token:
            raise ValueError("reply_token is required to send a reply message")
        self.line_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=self.reply_token, messages=messages_list))
        logger.info("Replied to the message.")

    def push_message(self, messages_list: list) -> None:
        self.line_api.push_message(PushMessageRequest(to=self.user_id, messages=messages_list))
        logger.info("Pushed a message to user %s.", self.user_id)

    def get_content(self) -> None:
        logger.info("Get blob content")
        return self.line_api_blob.get_message_content(self.message_id)
