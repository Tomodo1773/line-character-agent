"""
Test module for upload_recent_diaries function.
This test uses SPAN_DAYS=1 to test the upload_recent_diaries function
with mocked Google Drive and CosmosDB interactions.
"""

import datetime

from langchain_core.documents import Document

from function_app import upload_recent_diaries
from logger import logger


def test_upload_recent_diaries_span_days_1(mocker):
    """
    Test upload_recent_diaries function with SPAN_DAYS=1 using mocked services.
    """

    logger.info("Starting test_upload_recent_diaries_span_days_1")

    mock_token_manager_class = mocker.patch("function_app.GoogleUserTokenManager")
    mock_token_manager_instance = mock_token_manager_class.return_value
    mock_credentials = mocker.Mock()
    mock_token_manager_instance.get_all_user_credentials.return_value = [("user-1", mock_credentials)]

    mock_drive_handler_class = mocker.patch("function_app.GoogleDriveHandler")
    mock_drive_handler_instance = mock_drive_handler_class.return_value
    modified_time = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    mock_drive_handler_instance.list.return_value = [
        {"id": "file-1", "name": "note.md", "createdTime": modified_time, "modifiedTime": modified_time}
    ]
    mock_drive_handler_instance.get.return_value = Document(page_content="content", metadata={"source": "note.md"})

    mock_uploader_class = mocker.patch("function_app.CosmosDBUploader")
    mock_uploader_instance = mock_uploader_class.return_value

    upload_recent_diaries(span_days=1)

    mock_token_manager_class.assert_called_once()
    mock_token_manager_instance.get_all_user_credentials.assert_called_once()
    mock_drive_handler_class.assert_called_once_with(credentials=mock_credentials)
    mock_drive_handler_instance.list.assert_called_once()
    call_kwargs = mock_drive_handler_instance.list.call_args.kwargs
    assert "modified_after" in call_kwargs
    assert call_kwargs["modified_after"].endswith("Z")
    mock_drive_handler_instance.get.assert_called_once_with("file-1")
    mock_uploader_class.assert_called_once_with(userid="user-1")
    mock_uploader_instance.upload.assert_called_once()

    uploaded_docs = mock_uploader_instance.upload.call_args[0][0]
    assert len(uploaded_docs) == 1

    logger.info("test_upload_recent_diaries_span_days_1 completed")


if __name__ == "__main__":
    test_upload_recent_diaries_span_days_1()
