"""キューに積まれたメッセージをエージェントに渡し、LINE に返信する Queue トリガー。"""

import json

import azure.functions as func
from opentelemetry import trace
from opentelemetry.propagate import extract

import agent
import line_client
import users
from logger import create_logger

logger = create_logger(__name__)
tracer = trace.get_tracer(__name__)

bp = func.Blueprint()

RESET_KEYWORD = "閑話休題"
RESET_REPLY = "会話履歴をリセットしたよ。新しい気持ちで話そうね！"
ERROR_REPLY = "予期しないエラーが発生しちゃった。少し時間をおいてもう一度試してね。"


@bp.queue_trigger(arg_name="message", queue_name="%LINE_MESSAGE_QUEUE_NAME%", connection="AzureWebJobsStorage")
def line_worker(message: func.QueueMessage) -> None:
    logger.info("line_worker が呼び出されました")
    payload = json.loads(message.get_body().decode("utf-8"))

    # Gateway が本文に載せた traceparent を親にして、LINE 受信からの1本のトレースに繋げる。
    with tracer.start_as_current_span("line_worker", context=extract(payload["trace_context"])):
        line_client.show_loading_animation(payload["user_id"])
        try:
            reply = _generate_reply(payload["user_id"], payload["text"])
        except Exception:
            logger.exception("応答の生成に失敗しました")
            reply = ERROR_REPLY
        line_client.reply_or_push(payload["user_id"], payload["reply_token"], reply)


def _generate_reply(user_id: str, text: str) -> str:
    if text.strip() == RESET_KEYWORD:
        # 履歴は会話に紐づくため、新しい会話に差し替えるだけでリセットになる（ADR-0001 §3）。
        users.save_conversation_id(user_id, agent.create_conversation())
        logger.info("会話をリセットしました: user_id=%s", user_id)
        return RESET_REPLY

    conversation_id = users.get_conversation_id(user_id)
    if not conversation_id:
        conversation_id = agent.create_conversation()
        users.save_conversation_id(user_id, conversation_id)
        logger.info("新しい会話を開始しました: user_id=%s", user_id)

    return agent.respond(conversation_id, text)
