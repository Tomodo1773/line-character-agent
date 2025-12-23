import io
import json
from datetime import datetime
from typing import Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from chatbot.utils.config import create_logger

logger = create_logger(__name__)


class GoogleDriveHandler:
    """Google Driveとの連携を行うクラス"""

    SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/documents"]

    def __init__(self, credentials: Credentials, folder_id: str):
        """
        Google Drive APIクライアントを初期化する（OAuth資格情報のみ対応）

        Args:
            credentials: OAuth認証済みユーザーの資格情報
            folder_id: 操作用のGoogle DriveフォルダID
        """
        if not credentials:
            raise ValueError("OAuth credentials must be provided for Google Drive access")
        if not folder_id or not folder_id.strip():
            raise ValueError("Google Drive folder ID must be provided")
        try:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            self.creds = credentials
            self.service = build("drive", "v3", credentials=self.creds)
            self.folder_id = folder_id.strip()
            logger.info("Initialized Google Drive API client (OAuth only mode).")
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive API client: {e}")
            raise

    def _resolve_folder_id(self, folder_id: Optional[str] = None) -> str:
        resolved = folder_id or self.folder_id
        if not resolved:
            raise ValueError("Google Drive folder ID is required")
        return resolved

    def list_files(self, folder_id: Optional[str] = None) -> List[Dict]:
        """
        指定されたフォルダ内のファイル一覧を取得する

        Args:
            folder_id: フォルダID（指定がない場合はコンストラクタで与えたIDを使用）

        Returns:
            ファイル情報のリスト
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = f"'{target_folder_id}' in parents and trashed = false"
            results = (
                self.service.files().list(q=query, spaces="drive", fields="files(id, name, mimeType, modifiedTime)").execute()
            )

            files = results.get("files", [])
            logger.info(f"Retrieved {len(files)} files.")
            return files
        except HttpError as error:
            logger.error(f"An error occurred while retrieving the file list: {error}")
            return []

    def save_markdown(self, content: str, filename: str, folder_id: Optional[str] = None) -> str:
        """
        指定されたコンテンツをMarkdownファイルとしてGoogle Driveに保存する

        Args:
            content: 保存するコンテンツ
            filename: ファイル名
            folder_id: 保存先フォルダID（指定がない場合は環境変数から取得）

        Returns:
            保存されたファイルのID
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            file_metadata = {"name": filename, "mimeType": "text/markdown", "parents": [target_folder_id]}

            media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/markdown", resumable=True)

            file = self.service.files().create(body=file_metadata, media_body=media, fields="id").execute()

            file_id = file.get("id")
            logger.info(f"Saved file {filename} to Google Drive. ID: {file_id}")
            return file_id
        except HttpError as error:
            logger.error(f"An error occurred while saving the file to Google Drive: {error}")
            return ""

    def check_file_exists(self, filename: str, folder_id: Optional[str] = None) -> bool:
        """
        指定されたファイル名のファイルが指定フォルダ内に存在するかチェックする

        Args:
            filename: チェックするファイル名
            folder_id: フォルダID（指定がない場合は環境変数から取得）

        Returns:
            ファイルが存在する場合はTrue、存在しない場合はFalse
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = f"name = '{filename}' and '{target_folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()

            return len(results.get("files", [])) > 0
        except HttpError as error:
            logger.error(f"An error occurred while checking file existence: {error}")
            return False

    def get_file_content(self, file_id: str) -> str:
        """
        指定されたファイルの内容を取得する

        Args:
            file_id: ファイルID

        Returns:
            ファイルの内容
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            return fh.getvalue().decode("utf-8")
        except HttpError as error:
            logger.error(f"An error occurred while getting file content: {error}")
            return ""

    def append_or_create_json(self, new_digest: dict, filename: str, folder_id: Optional[str] = None) -> str:
        """
        指定されたダイジェストをJSONファイルに追加または新規作成する

        Args:
            new_digest: 追加するダイジェストエントリ
            filename: ファイル名
            folder_id: 保存先フォルダID（指定がない場合はコンストラクタで指定したIDを使用）

        Returns:
            処理されたファイルのID
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = f"name = '{filename}' and '{target_folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                file_id = files[0]["id"]
                existing_content = self.get_file_content(file_id)
                digest_data = (
                    json.loads(existing_content) if existing_content.strip() else self._create_default_digest_structure()
                )

                digest_data["daily"].insert(0, new_digest)
                digest_data["lastUpdated"] = datetime.now().strftime("%Y-%m-%d")

                updated_content = json.dumps(digest_data, ensure_ascii=False, indent=2)
                media = MediaIoBaseUpload(
                    io.BytesIO(updated_content.encode("utf-8")), mimetype="application/json", resumable=True
                )
                self.service.files().update(fileId=file_id, media_body=media).execute()
                logger.info(f"Updated file {filename} in Google Drive. ID: {file_id}")
                return file_id

            digest_data = self._create_default_digest_structure()
            digest_data["daily"].append(new_digest)
            digest_data["lastUpdated"] = datetime.now().strftime("%Y-%m-%d")

            content = json.dumps(digest_data, ensure_ascii=False, indent=2)
            media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="application/json", resumable=True)
            metadata = {"name": filename, "parents": [target_folder_id]}
            file = self.service.files().create(body=metadata, media_body=media, fields="id").execute()
            logger.info(f"Created new file {filename} in Google Drive. ID: {file.get('id')}")
            return file.get("id")
        except HttpError as error:
            logger.error(f"An error occurred while working with JSON file: {error}")
            return ""
        except json.JSONDecodeError as error:
            logger.error(f"JSON decode error: {error}")
            return ""

    def find_or_create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        """
        指定された名前のフォルダを検索し、なければ作成する

        Args:
            folder_name: フォルダ名（例: "2025"）
            parent_folder_id: 親フォルダID（指定がない場合はコンストラクタで与えたIDを使用）

        Returns:
            フォルダID
        """
        try:
            target_parent_id = self._resolve_folder_id(parent_folder_id)
            query = (
                f"name = '{folder_name}' and '{target_parent_id}' in parents "
                f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            )
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                folder_id = files[0]["id"]
                logger.info(f"Found existing folder '{folder_name}' with ID: {folder_id}")
                return folder_id

            # フォルダが存在しない場合は作成
            folder_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [target_parent_id],
            }
            folder = self.service.files().create(body=folder_metadata, fields="id").execute()
            folder_id = folder.get("id")
            logger.info(f"Created new folder '{folder_name}' with ID: {folder_id}")
            return folder_id
        except HttpError as error:
            logger.error(f"An error occurred while finding or creating folder '{folder_name}': {error}")
            raise

    def _create_default_digest_structure(self) -> dict:
        """
        デフォルトのダイジェストJSONデータ構造を作成する

        Returns:
            デフォルトのダイジェストデータ構造
        """
        return {
            "version": "2.0",
            "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
            "daily": [],
            "monthly": [],
            "yearly": [],
        }

    def get_profile_md(self, folder_id: Optional[str] = None) -> str:
        """
        profile.mdファイルの内容を取得する

        Args:
            folder_id: フォルダID（指定がない場合は環境変数から取得）

        Returns:
            ファイルの内容
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = f"name = 'profile.md' and '{target_folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                file_id = files[0]["id"]
                return self.get_file_content(file_id)
            else:
                logger.error("profile.md file not found in Google Drive.")
                return ""
        except HttpError as error:
            logger.error(f"An error occurred while getting profile.md: {error}")
            return ""

    def get_digest_json(self, folder_id: Optional[str] = None) -> str:
        """
        digest.jsonファイルの内容を取得する

        Args:
            folder_id: フォルダID（指定がない場合は環境変数から取得）

        Returns:
            ファイルの内容
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = f"name = 'digest.json' and '{target_folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                file_id = files[0]["id"]
                return self.get_file_content(file_id)
            else:
                logger.error("digest.json file not found in Google Drive.")
                return ""
        except HttpError as error:
            logger.error(f"An error occurred while getting digest.json: {error}")
            return ""

    def get_dictionary_md(self, folder_id: Optional[str] = None) -> str:
        """
        dictionary.mdファイルの内容を取得する

        Args:
            folder_id: フォルダID（指定がない場合は環境変数から取得）

        Returns:
            ファイルの内容
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = f"name = 'dictionary.md' and '{target_folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                file_id = files[0]["id"]
                return self.get_file_content(file_id)
            else:
                logger.error("dictionary.md file not found in Google Drive.")
                return ""
        except HttpError as error:
            logger.error(f"An error occurred while getting dictionary.md: {error}")
            return ""
