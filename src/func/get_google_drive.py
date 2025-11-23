import io
import os

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

    def __init__(self, credentials: Credentials):
        if not credentials:
            raise ValueError("Google Drive credentials are required")

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        self.creds = credentials
        self.service = build("drive", "v3", credentials=self.creds)

    def list(self, folder_id=None):
        if folder_id is None:
            folder_id = os.environ.get("DRIVE_FOLDER_ID")

        items = []
        page_token = None
        try:
            while True:
                results = (
                    self.service.files()
                    .list(
                        q=f"'{folder_id}' in parents",
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


# 以下は手動テスト用のコード例です。必要に応じてコメントアウトしてご利用ください。
# if __name__ == "__main__":
#     # 必要に応じて認証情報の取得方法を記述してください
#     from google.oauth2.credentials import Credentials
#     import os
# 
#     # 例: 環境変数やファイルから認証情報を取得
#     creds = None
#     # creds = Credentials.from_authorized_user_file("path/to/token.json", GoogleDriveHandler.SCOPES)
# 
#     handler = GoogleDriveHandler(creds)
#     files = handler.list()
#     print(f"Found {len(files)} files.")
#     if files:
#         doc = handler.get(files[0]['id'])
#         print(doc)
