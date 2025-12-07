import datetime
import os

import azure.functions as func
from dotenv import load_dotenv

from cosmosdb import CosmosDBUploader
from digest_reorganizer import DigestReorganizer
from get_google_drive import GoogleDriveHandler
from google_auth import GoogleUserTokenManager
from line_notifier import LineNotifier
from logger import logger

# 環境変数を.envファイルから読み込み
load_dotenv()

# Optional, add tracing in LangSmith (via LangChain)
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT") or "diary-rag"

app = func.FunctionApp()


@app.timer_trigger(schedule="0 0 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def timer_trigger(myTimer: func.TimerRequest) -> None:
    span_days = int(os.getenv("SPAN_DAYS", 3650))
    upload_recent_diaries(span_days)


def upload_recent_diaries(span_days: int = 1):
    # 除外するファイル名のリスト
    excluded_files = {"dictionary.md", "digest.json", "digest.md", "profile.md"}

    token_manager = GoogleUserTokenManager()
    user_contexts = token_manager.get_all_user_credentials()

    if not user_contexts:
        logger.warning("No Google Drive credentials found in users container.")
        return

    for context in user_contexts:
        if not context.drive_folder_id:
            logger.warning("Drive folder ID is missing for user %s. Skipping.", context.userid)
            continue

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now_utc - datetime.timedelta(days=span_days)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        drive_handler = GoogleDriveHandler(credentials=context.credentials, folder_id=context.drive_folder_id)
        files = drive_handler.list(modified_after=cutoff_str)
        for file in files:
            logger.debug(f"{file['name']} ({file['id']}) ({file['createdTime']}) ({file['modifiedTime']})")

        uploader = CosmosDBUploader(userid=context.userid)

        documents = []
        for file in files:
            # 除外ファイルチェック
            if file["name"] in excluded_files:
                logger.info(f"File {file['name']} is excluded from upload.")
                continue

            document = drive_handler.get(file["id"])
            if document:
                documents.append(document)
                logger.info("Document %s added to upload list for user %s.", document.metadata["source"], context.userid)

        if documents:
            uploader.upload(documents)


@app.timer_trigger(schedule="0 15 1 * *", arg_name="digestTimer", run_on_startup=False, use_monitor=False)
def reorganize_digest(digestTimer: func.TimerRequest) -> None:  # noqa: N803 (Azure Functions naming)
    reorganize_all_digests()


def reorganize_all_digests():
    token_manager = GoogleUserTokenManager()
    user_contexts = token_manager.get_all_user_credentials()

    if not user_contexts:
        logger.warning("No Google Drive credentials found in users container for digest reorg.")
        return

    reorganizer = DigestReorganizer()

    # LINE 通知機能を初期化（環境変数がない場合はスキップ）
    line_notifier = None
    try:
        line_notifier = LineNotifier()
    except ValueError:
        logger.warning("LINE_CHANNEL_ACCESS_TOKEN not set. Skipping LINE notifications.")

    for context in user_contexts:
        if not context.drive_folder_id:
            logger.warning("Drive folder ID is missing for user %s. Skipping digest reorg.", context.userid)
            continue

        drive_handler = GoogleDriveHandler(credentials=context.credentials, folder_id=context.drive_folder_id)
        digest_file = drive_handler.find_file("digest.json")
        if not digest_file:
            logger.info("digest.json not found in Drive for user %s. Skipping.", context.userid)
            continue

        document = drive_handler.get(digest_file["id"])
        if not document:
            logger.warning("Failed to download digest.json for user %s. Skipping.", context.userid)
            continue

        digest_text = document.page_content
        try:
            updated = reorganizer.reorganize(digest_text)
        except Exception as error:  # noqa: BLE001 - log and continue per user
            logger.error("Failed to reorganize digest for user %s: %s", context.userid, error)
            continue

        if not updated:
            logger.warning("Reorganized digest content is empty for user %s. Skipping upload.", context.userid)
            continue

        drive_handler.upsert_text_file("digest.json", updated, folder_id=context.drive_folder_id)
        logger.info("Reorganized digest.json for user %s", context.userid)

        # ダイジェスト再編成完了の LINE 通知を送信
        if line_notifier:
            try:
                line_notifier.send_notification(
                    context.userid,
                    "📝 ダイジェストの月次再編成が完了しました。\n日記の整理が更新されました。",
                )
            except Exception as error:  # noqa: BLE001 - log and continue
                logger.error("Failed to send LINE notification to user %s: %s", context.userid, error)


if __name__ == "__main__":
    upload_recent_diaries(3650)
