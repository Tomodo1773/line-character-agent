import datetime
import pytz
from .config import logger
from .line import LineMessenger
from .nijivoice import NijiVoiceClient
from .transcript import Diaryranscription


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
