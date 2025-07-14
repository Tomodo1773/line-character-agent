import io
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from chatbot.utils.config import create_logger

logger = create_logger(__name__)


class GoogleDriveHandler:
    """Google Driveとの連携を行うクラス"""

    SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/documents"]

    def __init__(self, credentials_file="credentials.json"):
        """
        Google Drive APIクライアントを初期化する

        Args:
            credentials_file: サービスアカウントの認証情報ファイルパス
        """
        try:
            self.creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=self.SCOPES)
            self.service = build("drive", "v3", credentials=self.creds)
            logger.info("Initialized Google Drive API client.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive API client: {e}")
            raise

    def list_files(self, folder_id: str) -> List[Dict]:
        """
        指定されたフォルダ内のファイル一覧を取得する

        Args:
            folder_id: フォルダID

        Returns:
            ファイル情報のリスト
        """
        try:
            query = f"'{folder_id}' in parents and trashed = false"
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
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            file_metadata = {"name": filename, "mimeType": "text/markdown", "parents": [folder_id]}

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
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
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

    def append_or_create_markdown(self, content: str, filename: str, folder_id: Optional[str] = None) -> str:
        """
        指定されたコンテンツをMarkdownファイルに追記または新規作成する

        Args:
            content: 追記するコンテンツ
            filename: ファイル名
            folder_id: 保存先フォルダID（指定がない場合は環境変数から取得）

        Returns:
            処理されたファイルのID
        """
        try:
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                # ファイルが存在する場合は内容を取得して追記
                file_id = files[0]["id"]
                existing_content = self.get_file_content(file_id)
                updated_content = existing_content + "\n" + content

                media = MediaIoBaseUpload(
                    io.BytesIO(updated_content.encode("utf-8")), mimetype="text/markdown", resumable=True
                )
                self.service.files().update(fileId=file_id, media_body=media).execute()
                logger.info(f"Updated file {filename} in Google Drive. ID: {file_id}")
                return file_id
            else:
                return self.save_markdown(content, filename, folder_id)
        except HttpError as error:
            logger.error(f"An error occurred while appending to file: {error}")
            return ""

    def append_or_create_json(self, new_digest: dict, filename: str, folder_id: Optional[str] = None) -> str:
        """
        指定されたダイジェストをJSONファイルに追加または新規作成する

        Args:
            new_digest: 追加するダイジェストエントリ
            filename: ファイル名
            folder_id: 保存先フォルダID（指定がない場合は環境変数から取得）

        Returns:
            処理されたファイルのID
        """
        try:
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                # ファイルが存在する場合は内容を取得して更新
                file_id = files[0]["id"]
                existing_content = self.get_file_content(file_id)
                
                if existing_content.strip():
                    digest_data = json.loads(existing_content)
                else:
                    digest_data = self._create_default_digest_structure()
                
                # recentセクションに新しいダイジェストを追加
                digest_data["recent"].insert(0, new_digest)
                digest_data["lastUpdated"] = datetime.now().strftime("%Y-%m-%d")
                
                updated_content = json.dumps(digest_data, ensure_ascii=False, indent=2)
                
                media = MediaIoBaseUpload(
                    io.BytesIO(updated_content.encode("utf-8")), mimetype="application/json", resumable=True
                )
                self.service.files().update(fileId=file_id, media_body=media).execute()
                logger.info(f"Updated file {filename} in Google Drive. ID: {file_id}")
                return file_id
            else:
                # ファイルが存在しない場合は新規作成
                digest_data = self._create_default_digest_structure()
                digest_data["recent"].append(new_digest)
                digest_data["lastUpdated"] = datetime.now().strftime("%Y-%m-%d")
                
                content = json.dumps(digest_data, ensure_ascii=False, indent=2)
                
                media = MediaIoBaseUpload(
                    io.BytesIO(content.encode("utf-8")), mimetype="application/json", resumable=True
                )
                metadata = {"name": filename, "parents": [folder_id]}
                file = self.service.files().create(body=metadata, media_body=media, fields="id").execute()
                logger.info(f"Created new file {filename} in Google Drive. ID: {file.get('id')}")
                return file.get("id")
        except HttpError as error:
            logger.error(f"An error occurred while working with JSON file: {error}")
            return ""
        except json.JSONDecodeError as error:
            logger.error(f"JSON decode error: {error}")
            return ""

    def _create_default_digest_structure(self) -> dict:
        """
        デフォルトのダイジェストJSONデータ構造を作成する

        Returns:
            デフォルトのダイジェストデータ構造
        """
        return {
            "version": "1.0",
            "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
            "recent": [],
            "monthly": [],
            "yearly": []
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
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            query = f"name = 'profile.md' and '{folder_id}' in parents and trashed = false"
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

    def get_digest_md(self, folder_id: Optional[str] = None) -> str:
        """
        digest.mdファイルの内容を取得する

        Args:
            folder_id: フォルダID（指定がない場合は環境変数から取得）

        Returns:
            ファイルの内容
        """
        try:
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            query = f"name = 'digest.md' and '{folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                file_id = files[0]["id"]
                return self.get_file_content(file_id)
            else:
                logger.error("digest.md file not found in Google Drive.")
                return ""
        except HttpError as error:
            logger.error(f"An error occurred while getting digest.md: {error}")
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
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            query = f"name = 'digest.json' and '{folder_id}' in parents and trashed = false"
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
            if folder_id is None:
                folder_id = os.environ.get("DRIVE_FOLDER_ID")

            query = f"name = 'dictionary.md' and '{folder_id}' in parents and trashed = false"
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
