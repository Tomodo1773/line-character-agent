import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from langchain_core.documents import Document
from logger import logger

from google_auth import GOOGLE_SCOPES


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

    def get(self, file_id) -> Document:
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
