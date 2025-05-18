import datetime
import os
from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pytz import timezone

from chatbot.utils.config import create_logger
from chatbot.utils.google_drive import GoogleDriveHandler

logger = create_logger(__name__)


def generate_diary_filename() -> str:
    """
    前日の日付に基づいたMarkdownファイル名を生成する
    フォーマット: YYYY年MM月DD日(曜日).md

    Returns:
        前日の日付に基づいたファイル名
    """
    jst = timezone("Asia/Tokyo")
    now = datetime.datetime.now(jst)
    yesterday = now - datetime.timedelta(days=1)

    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekday_jp[yesterday.weekday()]

    filename = f"{yesterday.year}年{yesterday.month:02d}月{yesterday.day:02d}日({weekday}).md"
    return filename


def check_filename_duplicate(drive_handler: GoogleDriveHandler, folder_id: str, filename: str) -> str:
    """
    ファイル名が重複している場合にサフィックスを追加する

    Args:
        drive_handler: GoogleDriveHandlerのインスタンス
        folder_id: フォルダID
        filename: チェックするファイル名

    Returns:
        重複を避けた新しいファイル名
    """
    name_without_ext = filename.rsplit(".", 1)[0]
    extension = filename.rsplit(".", 1)[1] if "." in filename else ""

    files = drive_handler.list_files(folder_id)
    existing_filenames = [file["name"] for file in files]

    if filename not in existing_filenames:
        return filename

    counter = 1
    new_filename = f"{name_without_ext}_{counter}.{extension}"

    while new_filename in existing_filenames:
        counter += 1
        new_filename = f"{name_without_ext}_{counter}.{extension}"

    return new_filename


def save_diary_to_drive(diary_content: str) -> Optional[str]:
    """
    日記コンテンツをGoogle Driveに保存する

    Args:
        diary_content: 保存する日記のテキスト

    Returns:
        保存に成功した場合はファイル名、失敗した場合はNone
    """
    try:
        drive_handler = GoogleDriveHandler()

        filename = generate_diary_filename()
        folder_id = os.environ.get("DRIVE_FOLDER_ID")

        if not folder_id:
            logger.error("DRIVE_FOLDER_IDが設定されていません")
            return None

        filename = check_filename_duplicate(drive_handler, folder_id, filename)

        file_id = drive_handler.save_markdown(diary_content, filename, folder_id)

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
        template = ChatPromptTemplate.from_messages([
            ("system", """
            あなたは日記の内容から、その日に起きた主要な出来事をまとめるダイジェスト生成の専門家です。
            与えられた日記の内容から、重要な出来事、感情、考えをまとめた短いダイジェストを作成してください。
            箇条書きではなく、文章形式で作成してください。
            元の日記の内容を尊重し、新しい情報を追加しないでください。
            """),
            ("human", "{diary_content}")
        ])
        
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.2)
        chain = template | llm | StrOutputParser()
        
        return chain.invoke({"diary_content": diary_content})
    except Exception as e:
        logger.error(f"ダイジェスト生成中にエラーが発生しました: {e}")
        return ""


def save_digest_to_drive(digest_content: str) -> bool:
    """
    日記のダイジェストをGoogle Driveに保存する
    ファイルが存在しない場合は新規作成し、存在する場合は追記する

    Args:
        digest_content: 保存するダイジェストのテキスト

    Returns:
        保存に成功した場合はTrue、失敗した場合はFalse
    """
    try:
        drive_handler = GoogleDriveHandler()
        
        jst = timezone("Asia/Tokyo")
        now = datetime.datetime.now(jst)
        date_str = f"{now.year}-{now.month:02d}-{now.day:02d}"
        
        filename = "digest.md"
        folder_id = os.environ.get("DRIVE_FOLDER_ID")
        
        if not folder_id:
            logger.error("DRIVE_FOLDER_IDが設定されていません")
            return False
        
        formatted_digest = f"\n## {date_str}\n{digest_content}\n"
        
        file_id = drive_handler.append_or_create_markdown(formatted_digest, filename, folder_id)
        
        return bool(file_id)
    except Exception as e:
        logger.error(f"ダイジェストの保存中にエラーが発生しました: {e}")
        return False
