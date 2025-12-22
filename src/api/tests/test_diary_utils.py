"""diary_utils モジュールのテスト。"""

from unittest.mock import MagicMock, patch


from chatbot.utils.diary_utils import save_diary_to_drive
from chatbot.utils.google_drive import GoogleDriveHandler


class TestSaveDiaryToDrive:
    """save_diary_to_drive 関数のテスト。"""

    def test_save_diary_creates_year_folder_when_not_exists(self):
        """年フォルダが存在しない場合に新規作成して保存することを確認。"""
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
        # 年フォルダが作成されたことを確認
        mock_drive_handler.find_or_create_folder.assert_called_once_with("2025")

        # 年フォルダ内のファイル一覧を取得したことを確認
        mock_drive_handler.list_files.assert_called_once_with("year_folder_id_123")

        # 年フォルダに保存されたことを確認
        mock_drive_handler.save_markdown.assert_called_once_with(diary_content, "2025年01月15日(水).md", "year_folder_id_123")

        # ファイル名が返されたことを確認
        assert result == "2025年01月15日(水)"

    def test_save_diary_uses_existing_year_folder(self):
        """既存の年フォルダに保存することを確認。"""
        # Arrange
        mock_drive_handler = MagicMock(spec=GoogleDriveHandler)
        mock_drive_handler.find_or_create_folder.return_value = "existing_year_folder_id_789"
        mock_drive_handler.list_files.return_value = [{"name": "2025年01月10日(金).md"}, {"name": "2025年01月11日(土).md"}]
        mock_drive_handler.save_markdown.return_value = "file_id_999"

        diary_content = "既存フォルダへの保存テスト。"

        # Act
        with patch("chatbot.utils.diary_utils.generate_diary_filename") as mock_generate:
            mock_generate.return_value = "2025年01月15日(水)"
            result = save_diary_to_drive(diary_content, mock_drive_handler)

        # Assert
        # 既存の年フォルダが使用されたことを確認
        mock_drive_handler.find_or_create_folder.assert_called_once_with("2025")

        # 年フォルダ内のファイル一覧を取得したことを確認
        mock_drive_handler.list_files.assert_called_once_with("existing_year_folder_id_789")

        # 既存年フォルダに保存されたことを確認
        mock_drive_handler.save_markdown.assert_called_once_with(
            diary_content, "2025年01月15日(水).md", "existing_year_folder_id_789"
        )

        # ファイル名が返されたことを確認
        assert result == "2025年01月15日(水)"

    def test_save_diary_handles_duplicate_filename(self):
        """同じファイル名が存在する場合にサフィックスを付けて保存することを確認。"""
        # Arrange
        mock_drive_handler = MagicMock(spec=GoogleDriveHandler)
        mock_drive_handler.find_or_create_folder.return_value = "year_folder_id_555"
        mock_drive_handler.list_files.return_value = [{"name": "2025年01月15日(水).md"}, {"name": "2025年01月15日(水)_1.md"}]
        mock_drive_handler.save_markdown.return_value = "file_id_777"

        diary_content = "重複ファイル名のテスト。"

        # Act
        with patch("chatbot.utils.diary_utils.generate_diary_filename") as mock_generate:
            mock_generate.return_value = "2025年01月15日(水)"
            result = save_diary_to_drive(diary_content, mock_drive_handler)

        # Assert
        # 年フォルダが使用されたことを確認
        mock_drive_handler.find_or_create_folder.assert_called_once_with("2025")

        # 重複チェックでファイル一覧を取得したことを確認
        mock_drive_handler.list_files.assert_called_once_with("year_folder_id_555")

        # サフィックス付きで保存されたことを確認（_2 が追加される）
        mock_drive_handler.save_markdown.assert_called_once_with(
            diary_content, "2025年01月15日(水)_2.md", "year_folder_id_555"
        )

        # サフィックス付きファイル名が返されたことを確認
        assert result == "2025年01月15日(水)_2"

    def test_save_diary_returns_none_when_save_fails(self):
        """保存に失敗した場合にNoneを返すことを確認。"""
        # Arrange
        mock_drive_handler = MagicMock(spec=GoogleDriveHandler)
        mock_drive_handler.find_or_create_folder.return_value = "year_folder_id_111"
        mock_drive_handler.list_files.return_value = []
        mock_drive_handler.save_markdown.return_value = ""  # 空文字列は失敗を意味する

        diary_content = "保存失敗テスト。"

        # Act
        with patch("chatbot.utils.diary_utils.generate_diary_filename") as mock_generate:
            mock_generate.return_value = "2025年01月15日(水)"
            result = save_diary_to_drive(diary_content, mock_drive_handler)

        # Assert
        assert result is None

    def test_save_diary_returns_none_when_exception_occurs(self):
        """例外が発生した場合にNoneを返すことを確認。"""
        # Arrange
        mock_drive_handler = MagicMock(spec=GoogleDriveHandler)
        mock_drive_handler.find_or_create_folder.side_effect = Exception("Drive API error")

        diary_content = "例外処理テスト。"

        # Act
        with patch("chatbot.utils.diary_utils.generate_diary_filename") as mock_generate:
            mock_generate.return_value = "2025年01月15日(水)"
            result = save_diary_to_drive(diary_content, mock_drive_handler)

        # Assert
        assert result is None

    def test_save_diary_extracts_year_correctly_from_filename(self):
        """ファイル名から年を正しく抽出することを確認。"""
        # Arrange
        mock_drive_handler = MagicMock(spec=GoogleDriveHandler)
        mock_drive_handler.find_or_create_folder.return_value = "year_folder_id_2024"
        mock_drive_handler.list_files.return_value = []
        mock_drive_handler.save_markdown.return_value = "file_id_2024"

        diary_content = "2024年のテスト。"

        # Act
        with patch("chatbot.utils.diary_utils.generate_diary_filename") as mock_generate:
            mock_generate.return_value = "2024年12月31日(火)"
            result = save_diary_to_drive(diary_content, mock_drive_handler)

        # Assert
        # 2024年のフォルダが作成/取得されたことを確認
        mock_drive_handler.find_or_create_folder.assert_called_once_with("2024")
        assert result == "2024年12月31日(火)"
