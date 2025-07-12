"""
Test module for upload_recent_diaries function.

This test uses SPAN_DAYS=1 to test the upload_recent_diaries function
with actual Google Drive data retrieval and mocked CosmosDB upload.
"""

import pytest
from function_app import upload_recent_diaries
from logger import logger


def test_upload_recent_diaries_span_days_1(mocker):
    """
    Test upload_recent_diaries function with SPAN_DAYS=1.

    This test performs:
    - Actual Google Drive data retrieval
    - Mocked CosmosDB upload (to avoid test complexity and environment variable requirements)

    Note: Duplicate files would be updated, which is expected behavior.
    """
    logger.info("Starting test_upload_recent_diaries_span_days_1")

    # Mock the CosmosDBUploader class entirely to avoid environment variable requirements
    # Need to patch where it's imported in function_app.py
    mock_uploader_class = mocker.patch("function_app.CosmosDBUploader")
    mock_uploader_instance = mock_uploader_class.return_value
    mock_uploader_instance.upload.return_value = None

    # Execute the function with SPAN_DAYS=1
    try:
        upload_recent_diaries(span_days=1)
        logger.info("upload_recent_diaries completed successfully")

        # Verify that the CosmosDBUploader was instantiated
        mock_uploader_class.assert_called_once()

        # Verify that the upload method was called
        mock_uploader_instance.upload.assert_called_once()

        # Get the documents that were passed to upload
        uploaded_docs = mock_uploader_instance.upload.call_args[0][0]
        logger.info(f"CosmosDB upload was called with {len(uploaded_docs)} documents")

    except Exception as e:
        logger.error(f"upload_recent_diaries failed: {e}")
        pytest.fail(f"upload_recent_diaries failed with error: {e}")

    logger.info("test_upload_recent_diaries_span_days_1 completed")


if __name__ == "__main__":
    test_upload_recent_diaries_span_days_1()
