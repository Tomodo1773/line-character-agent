import os

from chatbot.utils.config import create_logger
from dotenv import load_dotenv
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
)
from linebot.v3.webhooks import MessageEvent

logger = create_logger(__name__)

load_dotenv()


class LineMessenger:
    def __init__(
        self,
        event: MessageEvent,
    ) -> None:
        line_api_configuration = Configuration(access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))

        self.line_api_client = ApiClient(line_api_configuration)
        self.line_api = MessagingApi(self.line_api_client)
        self.line_api_blob = MessagingApiBlob(self.line_api_client)
        self.user_id = event.source.user_id
        self.reply_token = event.reply_token
        self.message_id = event.message.id

    def show_loading_animation(self) -> None:
        self.line_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=self.user_id, loadingSeconds=60))
        logger.info("Displayed loading animation.")

    def reply_message(self, messages_list: list) -> None:
        self.line_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=self.reply_token, messages=messages_list))
        logger.info("Replied to the message.")

    def get_content(self) -> None:
        logger.info("Get blob content")
        return self.line_api_blob.get_message_content(self.message_id)
