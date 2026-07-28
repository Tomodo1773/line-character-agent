"""LINE Messaging API との入出力をまとめたモジュール。"""

from functools import lru_cache

from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import Event

from config import get_settings
from logger import create_logger

logger = create_logger(__name__)

# ローディング表示の上限。5の倍数かつ最大60秒。
# https://developers.line.biz/en/docs/messaging-api/use-loading-indicator/
LOADING_SECONDS = 60


@lru_cache(maxsize=1)
def _messaging_api() -> MessagingApi:
    configuration = Configuration(access_token=get_settings().line_channel_access_token)
    return MessagingApi(ApiClient(configuration))


@lru_cache(maxsize=1)
def _webhook_parser() -> WebhookParser:
    return WebhookParser(get_settings().line_channel_secret)


def parse_events(body: str, signature: str) -> list[Event]:
    """webhook のリクエストを署名検証したうえでイベントに変換する。

    署名が一致しない場合は `InvalidSignatureError` を送出する。
    """
    logger.info("parse_events が呼び出されました")
    return _webhook_parser().parse(body, signature)


def show_loading_animation(user_id: str) -> None:
    """応答を生成している間、トーク画面にローディングを表示する。"""
    logger.info("show_loading_animation が呼び出されました")
    _messaging_api().show_loading_animation(ShowLoadingAnimationRequest(chatId=user_id, loadingSeconds=LOADING_SECONDS))


def reply_or_push(user_id: str, reply_token: str, text: str) -> None:
    """reply で返信し、失敗した場合だけ push にフォールバックする。

    reply token は受信から1分間しか有効でないため、エージェントの応答が長引くと失効する。
    一方 push はフリープランで月200通の上限があるため、フォールバック専用とする（ADR-0001 §1）。
    """
    logger.info("reply_or_push が呼び出されました")
    messages = [TextMessage(text=text)]
    try:
        _messaging_api().reply_message(ReplyMessageRequest(reply_token=reply_token, messages=messages))
        logger.info("reply で返信しました: user_id=%s", user_id)
    except ApiException as e:
        logger.warning("reply に失敗したため push にフォールバックします: status=%s", e.status)
        _messaging_api().push_message(PushMessageRequest(to=user_id, messages=messages))
        logger.info("push で返信しました: user_id=%s", user_id)
