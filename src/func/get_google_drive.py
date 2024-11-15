import io
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from langchain_core.documents import Document


class GoogleDriveHandler:
    SCOPES = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/documents.readonly"]

    def __init__(self, credentials_file="credentials.json"):
        self.creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=self.SCOPES)
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
            return items
        except HttpError as error:
            print(f"An error occurred while listing files: {error}")
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
            return Document(page_content=content, metadata={"source": file_metadata["name"]})

        except HttpError as error:
            print(f"An error occurred while getting file content: {error}")
            return None


# 使用例
if __name__ == "__main__":
    drive_handler = GoogleDriveHandler()

    # リスト取得
    file_list = drive_handler.list()
    for file in file_list:
        print(f"{file['name']} ({file['id']}) ({file['createdTime']}) ({file['modifiedTime']})")

    # 特定のファイルの内容を取得
    if file_list:
        document = drive_handler.get(file_list[1]["id"])
        if document:
            print(f"Content of {document.metadata['source']}:")
            print(document.page_content[:500])  # 最初の500文字だけ表示
