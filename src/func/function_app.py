import datetime
import os

import azure.functions as func
from dotenv import load_dotenv

from cosmosdb import CosmosDBUploader
from get_google_drive import GoogleDriveHandler
from google_auth import GoogleUserTokenManager
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
    excluded_files = {"dictionary.md", "digest.json", "digest.md", "profile.md"}

    token_manager = GoogleUserTokenManager()
    user_credentials = token_manager.get_all_user_credentials()

    if not user_credentials:
        logger.warning("No Google Drive credentials found in users container.")
        return

    for userid, credentials in user_credentials:
        drive_handler = GoogleDriveHandler(credentials=credentials)
        files = drive_handler.list()
        for file in files:
            logger.debug(f"{file['name']} ({file['id']}) ({file['createdTime']}) ({file['modifiedTime']})")

        now = datetime.datetime.now()
        uploader = CosmosDBUploader(userid=userid)

        documents = []
        for file in files:
            # 除外ファイルチェック
            if file["name"] in excluded_files:
                logger.info(f"File {file['name']} is excluded from upload.")
                continue

            modified_time = datetime.datetime.strptime(file["modifiedTime"], "%Y-%m-%dT%H:%M:%S.%fZ")

            # Check if the file was modified within the desired range
            if (now - modified_time).days < span_days:
                document = drive_handler.get(file["id"])
                if document:
                    documents.append(document)
                    logger.info("Document %s added to upload list for user %s.", document.metadata["source"], userid)

        if documents:
            uploader.upload(documents)


if __name__ == "__main__":
    upload_recent_diaries(3650)
