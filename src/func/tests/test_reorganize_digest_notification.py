"""reorganize_all_digests 関数の LINE 通知機能のテスト。"""

from langchain_core.documents import Document

from function_app import reorganize_all_digests
from google_auth import GoogleDriveUserContext


def test_reorganize_all_digests_continues_on_notification_failure(mocker):
    """LINE 通知の送信に失敗しても処理が継続することを確認する。"""
    creds = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user123", credentials=creds, drive_folder_id="folder-abc")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.find_file.return_value = {"id": "digest-file-id", "name": "digest.json"}
    mock_drive.get.return_value = Document(page_content='{"daily": [], "monthly": []}', metadata={})

    mock_reorganizer = mocker.patch("function_app.DigestReorganizer").return_value
    mock_reorganizer.reorganize.return_value = '{"daily": [], "monthly": [], "updated": true}'

    mock_notifier_class = mocker.patch("function_app.LineNotifier")
    mock_notifier_instance = mocker.Mock()
    mock_notifier_instance.send_notification.side_effect = Exception("LINE API Error")
    mock_notifier_class.return_value = mock_notifier_instance

    # エラーが発生してもプロセスが継続することを確認
    reorganize_all_digests()

    # ファイルがアップロードされたことを確認
    mock_drive.upsert_text_file.assert_called_once()


def test_reorganize_all_digests_sends_failure_notification_on_reorganize_error(mocker):
    """ダイジェスト再編成が失敗した場合、失敗通知が送信されることを確認する。"""
    creds = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user123", credentials=creds, drive_folder_id="folder-abc")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.find_file.return_value = {"id": "digest-file-id", "name": "digest.json"}
    mock_drive.get.return_value = Document(page_content='{"daily": [], "monthly": []}', metadata={})

    mock_reorganizer = mocker.patch("function_app.DigestReorganizer").return_value
    mock_reorganizer.reorganize.side_effect = Exception("Reorganization failed")

    mock_notifier_class = mocker.patch("function_app.LineNotifier")
    mock_notifier_instance = mocker.Mock()
    mock_notifier_class.return_value = mock_notifier_instance

    reorganize_all_digests()

    # 失敗通知が送信されたことを確認
    mock_notifier_instance.send_notification.assert_called_once_with(
        "user123", "⚠️ ダイジェストの月次再編成に失敗しました。\n後ほど再度実行されます。"
    )


def test_reorganize_all_digests_sends_failure_notification_on_empty_content(mocker):
    """再編成後のコンテンツが空の場合、失敗通知が送信されることを確認する。"""
    creds = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user123", credentials=creds, drive_folder_id="folder-abc")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.find_file.return_value = {"id": "digest-file-id", "name": "digest.json"}
    mock_drive.get.return_value = Document(page_content='{"daily": [], "monthly": []}', metadata={})

    mock_reorganizer = mocker.patch("function_app.DigestReorganizer").return_value
    mock_reorganizer.reorganize.return_value = ""

    mock_notifier_class = mocker.patch("function_app.LineNotifier")
    mock_notifier_instance = mocker.Mock()
    mock_notifier_class.return_value = mock_notifier_instance

    reorganize_all_digests()

    # 失敗通知が送信されたことを確認
    mock_notifier_instance.send_notification.assert_called_once_with(
        "user123", "⚠️ ダイジェストの月次再編成に失敗しました。\n後ほど再度実行されます。"
    )

