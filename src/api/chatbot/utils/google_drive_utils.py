from typing import Dict

from chatbot.utils.config import create_logger
from chatbot.utils.google_drive import GoogleDriveHandler

logger = create_logger(__name__)


def get_profile_from_drive() -> Dict:
    """
    Google Driveからprofile.mdを取得する

    Returns:
        ユーザープロファイル情報
    """
    try:
        handler = GoogleDriveHandler(credentials_file="credentials.json")
        content = handler.get_profile_md()

        if content:
            return {"content": content}
        else:
            logger.error("Failed to get profile.md content from Google Drive")
            return {"content": ""}
    except Exception as e:
        logger.error(f"Error while getting profile from Google Drive: {e}")
        return {"content": ""}


def get_digest_from_drive() -> Dict:
    """
    Google Driveからdigest.jsonを取得する

    Returns:
        ダイジェスト情報
    """
    try:
        handler = GoogleDriveHandler(credentials_file="credentials.json")
        content = handler.get_digest_json()

        if content:
            return {"content": content}
        else:
            logger.error("Failed to get digest.json content from Google Drive")
            return {"content": ""}
    except Exception as e:
        logger.error(f"Error while getting digest from Google Drive: {e}")
        return {"content": ""}


def get_dictionary_from_drive() -> str:
    """
    Google Driveからdictionary.mdを取得する

    Returns:
        辞書のmarkdownコンテンツ
    """
    try:
        handler = GoogleDriveHandler(credentials_file="credentials.json")
        content = handler.get_dictionary_md()

        if content:
            return content
        else:
            logger.error("Failed to get dictionary.md content from Google Drive")
            return ""
    except Exception as e:
        logger.error(f"Error while getting dictionary from Google Drive: {e}")
        return ""
