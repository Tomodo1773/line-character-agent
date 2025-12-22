import io
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from langchain_core.documents import Document

from google_auth import GOOGLE_SCOPES
from logger import logger


class GoogleDriveHandler:
    SCOPES = GOOGLE_SCOPES

    def __init__(self, credentials: Credentials, folder_id: str):
        if not credentials:
            raise ValueError("Google Drive credentials are required")

        if not folder_id or not folder_id.strip():
            raise ValueError("Google Drive folder ID is required")

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        self.creds = credentials
        self.service = build("drive", "v3", credentials=self.creds)
        self.folder_id = folder_id.strip()

    def _resolve_folder_id(self, folder_id: str | None = None) -> str:
        target = folder_id or self.folder_id
        if not target:
            raise ValueError("Google Drive folder ID is required")
        return target

    def list(self, folder_id=None, modified_after=None):
        target_folder_id = self._resolve_folder_id(folder_id)

        # modified_after は RFC3339 (UTC, 末尾Z) 文字列で渡すことを想定
        time_filter = ""
        if modified_after:
            time_filter = f" and modifiedTime > '{modified_after}'"

        items = []
        page_token = None
        try:
            while True:
                query = f"'{target_folder_id}' in parents and trashed = false{time_filter}"
                results = (
                    self.service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields="nextPageToken, files(id, name, createdTime, modifiedTime)",
                        orderBy="modifiedTime desc",
                        pageSize=1000,
                        pageToken=page_token,
                    )
                    .execute()
                )

                items.extend(results.get("files", []))
                page_token = results.get("nextPageToken")
                if not page_token:
                    break
            logger.info(f"{len(items)} files listed from Google Drive.")
            return items
        except HttpError as error:
            logger.error(f"An error occurred while listing files: {error}")
            return []

    def get(self, file_id) -> Optional[Document]:
        try:
            file_metadata = self.service.files().get(fileId=file_id, fields="name, mimeType").execute()

            if file_metadata["mimeType"] == "application/vnd.google-apps.document":
                request = self.service.files().export_media(fileId=file_id, mimeType="text/plain")
            else:
                request = self.service.files().get_media(fileId=file_id)

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            content = fh.getvalue().decode("utf-8-sig")
            logger.info(f"File {file_metadata['name']} downloaded successfully.")
            return Document(page_content=content, metadata={"source": file_metadata["name"]})

        except HttpError as error:
            logger.error(f"An error occurred while getting file content: {error}")
            return None

    def find_file(self, filename: str, folder_id: str | None = None) -> Optional[dict]:
        """指定フォルダ内でファイル名が一致する最初のファイルを返す。"""
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = f"name = '{filename}' and '{target_folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name, mimeType)").execute()
            files = results.get("files", [])
            return files[0] if files else None
        except HttpError as error:
            logger.error("An error occurred while searching file %s: %s", filename, error)
            return None

    def find_or_create_folder(self, folder_name: str, parent_folder_id: str | None = None) -> str:
        """指定された名前のフォルダを検索し、なければ作成する。

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
                logger.info("Found existing folder '%s' with ID: %s", folder_name, folder_id)
                return folder_id

            # フォルダが存在しない場合は作成
            folder_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [target_parent_id],
            }
            folder = self.service.files().create(body=folder_metadata, fields="id").execute()
            folder_id = folder.get("id")
            logger.info("Created new folder '%s' with ID: %s", folder_name, folder_id)
            return folder_id
        except HttpError as error:
            logger.error("An error occurred while finding or creating folder '%s': %s", folder_name, error)
            raise

    def list_folders(self, folder_id: str | None = None) -> list[dict]:
        """指定フォルダ内のフォルダのみを一覧取得する。

        Args:
            folder_id: 親フォルダID（指定がない場合はコンストラクタで与えたIDを使用）

        Returns:
            フォルダ情報のリスト
        """
        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            query = (
                f"'{target_folder_id}' in parents "
                f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            )
            results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            folders = results.get("files", [])
            logger.info("%d folders listed from Google Drive.", len(folders))
            return folders
        except HttpError as error:
            logger.error("An error occurred while listing folders: %s", error)
            return []

    def upsert_text_file(
        self, filename: str, content: str, *, folder_id: str | None = None, mime_type: str = "application/json"
    ) -> str:
        """指定されたコンテンツでファイルを作成または更新する。"""

        try:
            target_folder_id = self._resolve_folder_id(folder_id)
            existing = self.find_file(filename, target_folder_id)
            media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype=mime_type, resumable=True)

            if existing:
                file_id = existing["id"]
                self.service.files().update(fileId=file_id, media_body=media).execute()
                logger.info("Updated file %s (%s)", filename, file_id)
                return file_id

            metadata = {"name": filename, "parents": [target_folder_id]}
            created = self.service.files().create(body=metadata, media_body=media, fields="id").execute()
            file_id = created.get("id", "")
            logger.info("Created file %s (%s)", filename, file_id)
            return file_id
        except HttpError as error:
            logger.error("An error occurred while upserting %s: %s", filename, error)
            return ""
