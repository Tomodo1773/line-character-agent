"""
Test module for upload_recent_diaries function.

This test uses SPAN_DAYS=1 to test the upload_recent_diaries function
with actual Google Drive data retrieval and mocked CosmosDB upload.
"""

import pytest
from unittest.mock import Mock, patch
from function_app import upload_recent_diaries
from get_google_drive import GoogleDriveHandler
from langchain_core.documents import Document
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


def test_google_drive_handler_file_format_detection():
    """
    Test GoogleDriveHandler to ensure it correctly handles both Google Docs and MD files.
    
    This test mocks the Google Drive API to simulate different file types
    and verifies that the handler processes them correctly.
    """
    logger.info("Starting test_google_drive_handler_file_format_detection")
    
    # Mock Google Drive service
    with patch('get_google_drive.service_account'), \
         patch('get_google_drive.build') as mock_build:
        
        # Setup mock service
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Test data for Google Docs file
        google_docs_metadata = {
            "name": "2025年07月27日(土).docx",
            "mimeType": "application/vnd.google-apps.document"
        }
        
        # Test data for MD file
        md_file_metadata = {
            "name": "2025年07月27日(土).md", 
            "mimeType": "text/markdown"
        }
        
        # Mock Google Docs file processing
        mock_service.files().get.return_value.execute.return_value = google_docs_metadata
        mock_service.files().export_media.return_value = Mock()
        
        # Mock the download process for Google Docs
        mock_downloader = Mock()
        mock_downloader.next_chunk.side_effect = [(None, False), (None, True)]
        
        with patch('get_google_drive.MediaIoBaseDownload', return_value=mock_downloader), \
             patch('get_google_drive.io.BytesIO') as mock_bytesio:
            
            # Mock the content for Google Docs
            mock_fh = Mock()
            mock_fh.getvalue.return_value = b"Google Docs content in plain text"
            mock_bytesio.return_value = mock_fh
            
            # Create handler and test Google Docs processing
            handler = GoogleDriveHandler()
            result = handler.get("test_google_docs_id")
            
            # Assertions for Google Docs
            assert result is not None
            assert result.page_content == "Google Docs content in plain text"
            assert result.metadata["source"] == "2025年07月27日(土).docx"
            assert result.metadata["mime_type"] == "application/vnd.google-apps.document"
            
            # Verify export_media was called for Google Docs
            mock_service.files().export_media.assert_called_with(
                fileId="test_google_docs_id", mimeType="text/plain"
            )
        
        # Reset mocks for MD file test
        mock_service.reset_mock()
        mock_service.files().get.return_value.execute.return_value = md_file_metadata
        mock_service.files().get_media.return_value = Mock()
        
        # Mock the download process for MD file
        with patch('get_google_drive.MediaIoBaseDownload', return_value=mock_downloader), \
             patch('get_google_drive.io.BytesIO') as mock_bytesio:
            
            # Mock the content for MD file
            mock_fh = Mock()
            mock_fh.getvalue.return_value = b"# Markdown content\n\nThis is markdown."
            mock_bytesio.return_value = mock_fh
            
            # Test MD file processing
            result = handler.get("test_md_id")
            
            # Assertions for MD file
            assert result is not None
            assert result.page_content == "# Markdown content\n\nThis is markdown."
            assert result.metadata["source"] == "2025年07月27日(土).md"
            assert result.metadata["mime_type"] == "text/markdown"
            
            # Verify get_media was called for MD file
            mock_service.files().get_media.assert_called_with(fileId="test_md_id")
    
    logger.info("test_google_drive_handler_file_format_detection completed")


def test_google_drive_handler_error_handling():
    """
    Test GoogleDriveHandler error handling for various failure scenarios.
    """
    logger.info("Starting test_google_drive_handler_error_handling")
    
    with patch('get_google_drive.service_account'), \
         patch('get_google_drive.build') as mock_build:
        
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Test HTTP error handling
        from googleapiclient.errors import HttpError
        
        # Mock HttpError
        mock_service.files().get.side_effect = HttpError(
            Mock(status=404), b'{"error": {"message": "File not found"}}'
        )
        
        handler = GoogleDriveHandler()
        result = handler.get("nonexistent_file_id")
        
        # Should return None on error
        assert result is None
        
    logger.info("test_google_drive_handler_error_handling completed")


if __name__ == "__main__":
    test_upload_recent_diaries_span_days_1()
    test_google_drive_handler_file_format_detection()
    test_google_drive_handler_error_handling()
