import datetime
import os
from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pytz import timezone

from chatbot.utils.config import create_logger
from chatbot.utils.google_drive import GoogleDriveHandler

logger = create_logger(__name__)


def generate_diary_filename() -> str:
    """
    前日の日付に基づいたMarkdownファイル名（拡張子なし）を生成する
    フォーマット: YYYY年MM月DD日(曜日)

    Returns:
        前日の日付に基づいたファイル名（拡張子なし）
    """
    jst = timezone("Asia/Tokyo")
    now = datetime.datetime.now(jst)
    yesterday = now - datetime.timedelta(days=1)

    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekday_jp[yesterday.weekday()]

    filename = f"{yesterday.year}年{yesterday.month:02d}月{yesterday.day:02d}日({weekday})"
    return filename


def check_filename_duplicate(drive_handler: GoogleDriveHandler, folder_id: str, filename: str) -> str:
    """
    ファイル名が重複している場合にサフィックスを追加する（拡張子なし）

    Args:
        drive_handler: GoogleDriveHandlerのインスタンス
        folder_id: フォルダID
        filename: チェックするファイル名（拡張子なし）

    Returns:
        重複を避けた新しいファイル名（拡張子なし）
    """
    name_without_ext = filename
    extension = "md"

    files = drive_handler.list_files(folder_id)
    existing_filenames = [file["name"].rsplit(".", 1)[0] for file in files if file["name"].endswith(f".{extension}")]

    if filename not in existing_filenames:
        return filename

    counter = 1
    new_filename = f"{name_without_ext}_{counter}"

    while new_filename in existing_filenames:
        counter += 1
        new_filename = f"{name_without_ext}_{counter}"

    return new_filename


def save_diary_to_drive(diary_content: str) -> Optional[str]:
    """
    日記コンテンツをGoogle Driveに保存する

    Args:
        diary_content: 保存する日記のテキスト

    Returns:
        保存に成功した場合はファイル名（拡張子なし）、失敗した場合はNone
    """
    try:
        drive_handler = GoogleDriveHandler()

        filename = generate_diary_filename()
        folder_id = os.environ.get("DRIVE_FOLDER_ID")

        filename = check_filename_duplicate(drive_handler, folder_id, filename)
        filename_with_ext = f"{filename}.md"

        file_id = drive_handler.save_markdown(diary_content, filename_with_ext, folder_id)

        if file_id:
            logger.info(f"日記をGoogle Driveに保存しました: {filename}")
            return filename
        else:
            logger.error("Google Driveへの保存に失敗しました")
            return None

    except Exception as e:
        logger.error(f"Google Driveへの保存中にエラーが発生しました: {e}")
        return None


def generate_diary_digest(diary_content: str) -> str:
    """
    日記の内容からAIを使ってダイジェスト（要約）を生成する

    Args:
        diary_content: 日記の内容

    Returns:
        生成されたダイジェスト
    """
    try:
        template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
                    あなたは日記の内容から、その日の最も重要な出来事を1つのシンプルなフレーズにまとめる専門家です。
                    与えられた日記の内容から、その日を最も象徴する出来事やテーマを1-5語程度の非常に短いフレーズで表現してください。
                    複数の出来事があっても、最も印象的で重要なもの1つに絞ってください。
                    感情は不要で、体言止めまたは短い文で端的に表現してください。

                    例:
                    入力: 午前中は家の掃除をして、昼はラーメンを食べに行った。午後は映画を見て、夜は友達と電話した。
                    出力: 映画鑑賞

                    入力: 今日は会社の健康診断があった。その後同僚とランチして、夕方は資料作成。
                    出力: 健康診断

                    入力: 家族でディズニーランドに行き、たくさんアトラクションに乗った。お土産も買った。
                    出力: ディズニーランド
                    """,
                ),
                ("human", "{diary_content}"),
            ]
        )

        llm = ChatOpenAI(model="gpt-4.1", temperature=0.2)
        chain = template | llm | StrOutputParser()

        return chain.invoke({"diary_content": diary_content})
    except Exception as e:
        logger.error(f"ダイジェスト生成中にエラーが発生しました: {e}")
        return ""


def save_digest_to_drive(digest_content: str, diary_filename: str) -> bool:
    """
    日記のダイジェストをGoogle Driveに保存する
    ファイルが存在しない場合は新規作成し、存在する場合は追記する

    Args:
        digest_content: 保存するダイジェストのテキスト
        diary_filename: 日記ファイル名（拡張子なし、日付）

    Returns:
        保存に成功した場合はTrue、失敗した場合はFalse
    """
    try:
        drive_handler = GoogleDriveHandler()

        # digest.mdに追記する日付としてdiary_filenameをそのまま使う
        date_str = diary_filename

        filename = "digest.md"
        folder_id = os.environ.get("DRIVE_FOLDER_ID")

        formatted_digest = f"\n## {date_str}\n{digest_content}\n"

        file_id = drive_handler.append_or_create_markdown(formatted_digest, filename, folder_id)

        return bool(file_id)
    except Exception as e:
        logger.error(f"ダイジェストの保存中にエラーが発生しました: {e}")
        return False
