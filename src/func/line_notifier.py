"""LINE 通知を送信するヘルパー。"""

import os
from typing import Optional

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

from logger import logger


class LineNotifier:
    """LINE Push 通知を送信する。"""

    def __init__(self, access_token: Optional[str] = None) -> None:
        """
        LINE Notifier を初期化する。

        Args:
            access_token: LINE チャネルアクセストークン。
                         指定しない場合は環境変数 LINE_CHANNEL_ACCESS_TOKEN から取得。
        """
        token = access_token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        if not token:
            raise ValueError("LINE_CHANNEL_ACCESS_TOKEN is required")

        configuration = Configuration(access_token=token)
        self.api_client = ApiClient(configuration)
        self.messaging_api = MessagingApi(self.api_client)

    def send_notification(self, user_id: str, message_text: str) -> None:
        """
        指定されたユーザーに LINE Push 通知を送信する。

        Args:
            user_id: LINE ユーザー ID
            message_text: 送信するメッセージテキスト
        """
        try:
            text_message = TextMessage(text=message_text)
            request = PushMessageRequest(to=user_id, messages=[text_message])
            self.messaging_api.push_message(request)
            logger.info("LINE notification sent to user %s", user_id)
        except Exception as error:
            logger.error("Failed to send LINE notification to user %s: %s", user_id, error)
            raise
