"""LINE webhook を受け取り、検証してキューに積む HTTP トリガー。

エージェントの応答を待たずに 200 を返すことで、Functions とエージェントのコールドスタートを
LINE のタイムアウトから切り離す（ADR-0001 §1）。
"""

import json

import azure.functions as func
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import Event, MessageEvent, TextMessageContent
from opentelemetry.propagate import inject

import line_client
from config import get_settings
from logger import create_logger

logger = create_logger(__name__)

bp = func.Blueprint()

# 音声の文字起こしはスマートフォン側に移譲した（ADR-0001「廃止するもの」）。
NON_TEXT_GUIDANCE = "ごめん、いまはテキストしか読めないんだ。テキストで送ってね！"


@bp.route(route="line/callback", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@bp.queue_output(arg_name="queue", queue_name="%LINE_MESSAGE_QUEUE_NAME%", connection="AzureWebJobsStorage")
def line_gateway(req: func.HttpRequest, queue: func.Out[list[str]]) -> func.HttpResponse:
    logger.info("line_gateway が呼び出されました")
    try:
        events = line_client.parse_events(req.get_body().decode("utf-8"), req.headers.get("x-line-signature", ""))
    except InvalidSignatureError:
        logger.error("署名検証に失敗しました")
        return func.HttpResponse("invalid signature", status_code=400)

    messages = [json.dumps(payload) for payload in _to_queue_payloads(events)]
    if messages:
        queue.set(messages)
        logger.info("%d 件のメッセージをキューに投入しました", len(messages))

    return func.HttpResponse("ok", status_code=200)


def _to_queue_payloads(events: list[Event]) -> list[dict]:
    """Worker に渡すテキストメッセージだけを取り出す。

    個人用エージェントのため、`DIARY_USER_ID` と一致する送信者だけを処理する。
    テキスト以外のメッセージには、reply token が新しいこの場で案内を返す。
    """
    payloads = []
    authorized_user_id = get_settings().diary_user_id
    for event in events:
        if not isinstance(event, MessageEvent):
            logger.info("処理対象外のイベントのため無視します: %s", type(event).__name__)
        elif event.source.user_id != authorized_user_id:
            logger.warning("許可されていない LINE ユーザからのイベントを無視します")
        elif isinstance(event.message, TextMessageContent):
            payloads.append(_build_payload(event))
        else:
            logger.info("テキスト以外のメッセージを受信しました: %s", type(event.message).__name__)
            line_client.reply_or_push(event.source.user_id, event.reply_token, NON_TEXT_GUIDANCE)
    return payloads


def _build_payload(event: MessageEvent) -> dict:
    # Storage Queue のメッセージはメタデータを持たず trace context が自動伝搬しないため、
    # traceparent を本文に載せて Worker 側で親コンテキストとして復元する（ADR-0001 §5）。
    trace_context: dict[str, str] = {}
    inject(trace_context)
    return {
        "user_id": event.source.user_id,
        "reply_token": event.reply_token,
        "text": event.message.text,
        "trace_context": trace_context,
    }
