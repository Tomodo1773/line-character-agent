import datetime
from collections.abc import Sequence

import pytz
from langchain_core.messages.base import BaseMessage


def remove_trailing_newline(text: str) -> str:
    """
    入力されたテキストの最後の改行を削除する関数

    :param text: 入力テキスト
    :return: 最後の改行が削除されたテキスト
    """
    return text.rstrip("\n")


def get_japan_datetime() -> str:
    """
    日本時間の日次と曜日を取得して返す関数

    :return: 日本時間の日次と曜日 (yyyy:mm:dd hh:mm (a)形式)
    """
    tz = pytz.timezone("Asia/Tokyo")
    now = datetime.datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S (%a)")


def messages_to_dict(messages: Sequence[BaseMessage]) -> list[dict]:
    """
    BaseMessageオブジェクトのシーケンスを辞書のリストに変換する関数

    :param messages: BaseMessageオブジェクトのシーケンス
    :return: 各メッセージのタイプと内容を含む辞書のリスト
    """

    messages_dict = []
    for m in messages:
        message_data = m.model_dump()
        if "content" in message_data:
            messages_dict.append({"type": m.type, "content": message_data["content"]})
    return messages_dict
