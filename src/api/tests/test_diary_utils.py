"""diary_utils モジュールのテスト。"""

import datetime
from unittest.mock import MagicMock, patch

from chatbot.utils.diary_utils import generate_diary_filename, save_diary_to_drive
from chatbot.utils.google_drive import GoogleDriveHandler


class TestGenerateDiaryFilename:
    """generate_diary_filename 関数のテスト。"""

    def test_fixed_date(self):
        """固定日付でフォーマットと曜日が正しいことを確認。"""
        date = datetime.date(2025, 1, 6)  # 月曜日
        assert generate_diary_filename(date) == "2025年01月06日(月)"


class TestSaveDiaryToDrive:
    """save_diary_to_drive 関数のテスト。"""

    def test_save_diary_creates_year_folder(self):
        """年フォルダを作成/取得して保存することを確認。"""
        # Arrange
        mock_drive_handler = MagicMock(spec=GoogleDriveHandler)
        mock_drive_handler.find_or_create_folder.return_value = "year_folder_id_123"
        mock_drive_handler.list_files.return_value = []
        mock_drive_handler.save_markdown.return_value = "file_id_456"

        diary_content = "今日は楽しい一日でした。"

        # Act
        with patch("chatbot.utils.diary_utils.generate_diary_filename") as mock_generate:
            mock_generate.return_value = "2025年01月15日(水)"
            result = save_diary_to_drive(diary_content, mock_drive_handler)

        # Assert
        mock_drive_handler.find_or_create_folder.assert_called_once_with("2025")
        mock_drive_handler.list_files.assert_called_once_with("year_folder_id_123")
        mock_drive_handler.save_markdown.assert_called_once_with(diary_content, "2025年01月15日(水).md", "year_folder_id_123")
        assert result == "2025年01月15日(水)"
