import datetime
import os

import azure.functions as func
from dotenv import load_dotenv

from cosmosdb import CosmosDBUploader
from get_google_drive import GoogleDriveHandler
from logger import logger

# 環境変数を.envファイルから読み込み
load_dotenv()

app = func.FunctionApp()


@app.timer_trigger(schedule="0 0 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def timer_trigger(myTimer: func.TimerRequest) -> None:
    span_days = int(os.getenv("SPAN_DAYS", 3650))
    upload_recent_diaries(span_days)


def upload_recent_diaries(span_days: int = 1):
    # 除外するファイル名のリスト
    excluded_files = {"dictionary.md", "digest.json", "profile.md"}

    # Get the list of files from Google Drive
    drive_handler = GoogleDriveHandler()
    files = drive_handler.list()
    for file in files:
        print(f"{file['name']} ({file['id']}) ({file['createdTime']}) ({file['modifiedTime']})")

    # Get the current time
    now = datetime.datetime.now()

    # Initialize the CosmosDBUploader
    uploader = CosmosDBUploader()

    # Iterate over the files and check their modified time
    documents = []
    for file in files:
        # 除外ファイルチェック
        if file["name"] in excluded_files:
            logger.info(f"File {file['name']} is excluded from upload.")
            continue

        modified_time = datetime.datetime.strptime(file["modifiedTime"], "%Y-%m-%dT%H:%M:%S.%fZ")

        # Check if the file was modified within the last day
        if (now - modified_time).days < span_days:
            # Get the content of the file
            document = drive_handler.get(file["id"])
            documents.append(document)
            logger.info(f"Document {document.metadata['source']} added to upload list.")

    # Upload the content to CosmosDB (既存の日記をスキップ)
    uploader.upload(documents)


if __name__ == "__main__":
    upload_recent_diaries(3650)
