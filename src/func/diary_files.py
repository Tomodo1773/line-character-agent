import re
from datetime import datetime
from typing import Optional

JP_DIARY_FILENAME_RE = re.compile(r"^(\d{4})年(\d{2})月(\d{2})日\(([月火水木金土日])\)\.md$")

WEEKDAY_MAP = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}


def is_diary_filename(name: str) -> bool:
    """YYYY年MM月DD日(曜).md 形式かどうかを判定する。"""
    return bool(JP_DIARY_FILENAME_RE.match(name))


def extract_date_info_from_source(source: str) -> Optional[dict]:
    """
    ファイル名（source）から日付情報を抽出して構造化して返す。

    日記形式に一致しない場合は None を返す。
    """
    match = JP_DIARY_FILENAME_RE.search(source)
    if not match:
        return None

    year, month, day, weekday_jp = match.groups()
    date_str = f"{year}-{month}-{day}"
    day_of_week = WEEKDAY_MAP.get(weekday_jp, datetime.strptime(date_str, "%Y-%m-%d").weekday())

    return {
        "date": date_str,
        "year": int(year),
        "month": int(month),
        "day": int(day),
        "dayOfWeek": day_of_week,
    }
