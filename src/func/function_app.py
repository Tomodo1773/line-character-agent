import datetime
import logging

import azure.functions as func

from aisearch import AISearchUploader
from get_google_drive import GoogleDriveHandler

app = func.FunctionApp()

@app.timer_trigger(schedule="0 * * * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False) 
def timer_trigger(myTimer: func.TimerRequest) -> None:
    upload_recent_diaries(3650)


def upload_recent_diaries(span_days: int = 1):
    # Get the list of files from Google Drive
    drive_handler = GoogleDriveHandler()
    files = drive_handler.list()
    for file in files:
        print(f"{file['name']} ({file['id']}) ({file['createdTime']}) ({file['modifiedTime']})")

    # Get the current time
    now = datetime.datetime.now()

    # Initialize the AISearchUploader
    uploader = AISearchUploader()

    # Iterate over the files and check their modified time
    documents = []
    for file in files:
        modified_time = datetime.datetime.strptime(file['modifiedTime'], "%Y-%m-%dT%H:%M:%S.%fZ")

        # Check if the file was modified within the last day
        if (now - modified_time).days < span_days:
            # Get the content of the file
            document = drive_handler.get(file["id"])
            documents.append(document)

    # Upload the content to Azure AI Search
    uploader.upload(documents)

if __name__ == "__main__":
    upload_recent_diaries(3650)