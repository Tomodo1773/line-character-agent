import re
from typing import Optional


def extract_drive_folder_id(text: str) -> Optional[str]:
    """ユーザ入力からGoogle DriveフォルダIDを抽出する。

    - drive.google.com のフォルダURL
    - drive.google.com の共有URL（u/{number} を含むもの）
    - 英数/ハイフン/アンダースコアのみで20文字以上の値（フォルダID想定）
    """

    if not text:
        return None

    normalized = text.strip()
    if not normalized:
        return None

    url_match = re.search(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([\w-]+)", normalized)
    if url_match:
        return url_match.group(1)

    raw_id_match = re.fullmatch(r"[\w-]{20,}", normalized)
    if raw_id_match:
        return raw_id_match.group(0)

    return None

