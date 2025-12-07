"""reorganize_all_digests 関数の LINE 通知機能のテスト。"""

from langchain_core.documents import Document

from function_app import reorganize_all_digests
from google_auth import GoogleDriveUserContext


def test_reorganize_all_digests_sends_line_notification(mocker):
    """ダイジェスト再編成が成功した場合、LINE 通知が送信されることを確認する。"""
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
    mock_notifier_class.return_value = mock_notifier_instance

    reorganize_all_digests()

    # LINE 通知が送信されたことを確認
    mock_notifier_instance.send_notification.assert_called_once_with(
        "user123", "📝 ダイジェストの月次再編成が完了しました。\n日記の整理が更新されました。"
    )


def test_reorganize_all_digests_skips_notification_when_token_missing(mocker):
    """LINE_CHANNEL_ACCESS_TOKEN が設定されていない場合、通知をスキップすることを確認する。"""
    creds = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user123", credentials=creds, drive_folder_id="folder-abc")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.find_file.return_value = {"id": "digest-file-id", "name": "digest.json"}
    mock_drive.get.return_value = Document(page_content='{"daily": [], "monthly": []}', metadata={})

    mock_reorganizer = mocker.patch("function_app.DigestReorganizer").return_value
    mock_reorganizer.reorganize.return_value = '{"daily": [], "monthly": [], "updated": true}'

    # LINE_CHANNEL_ACCESS_TOKEN が設定されていない場合、ValueError が発生する
    mock_notifier_class = mocker.patch("function_app.LineNotifier")
    mock_notifier_class.side_effect = ValueError("LINE_CHANNEL_ACCESS_TOKEN is required")

    # エラーなく完了すること（通知がスキップされる）
    reorganize_all_digests()

    # 通知は送信されない
    mock_notifier_class.assert_called_once()


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


def test_reorganize_all_digests_handles_multiple_users(mocker):
    """複数ユーザーのダイジェスト再編成と通知が正しく処理されることを確認する。"""
    creds1, creds2 = mocker.Mock(), mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="alice", credentials=creds1, drive_folder_id="folder-a"),
        GoogleDriveUserContext(userid="bob", credentials=creds2, drive_folder_id="folder-b"),
    ]

    drive1, drive2 = mocker.Mock(), mocker.Mock()
    drive1.find_file.return_value = {"id": "digest-a", "name": "digest.json"}
    drive2.find_file.return_value = {"id": "digest-b", "name": "digest.json"}
    drive1.get.return_value = Document(page_content='{"daily": []}', metadata={})
    drive2.get.return_value = Document(page_content='{"daily": []}', metadata={})

    mocker.patch("function_app.GoogleDriveHandler", side_effect=[drive1, drive2])

    mock_reorganizer = mocker.patch("function_app.DigestReorganizer").return_value
    mock_reorganizer.reorganize.return_value = '{"daily": [], "updated": true}'

    mock_notifier_class = mocker.patch("function_app.LineNotifier")
    mock_notifier_instance = mocker.Mock()
    mock_notifier_class.return_value = mock_notifier_instance

    reorganize_all_digests()

    # 2人のユーザーに通知が送信されたことを確認
    assert mock_notifier_instance.send_notification.call_count == 2
    calls = mock_notifier_instance.send_notification.call_args_list
    assert calls[0][0][0] == "alice"
    assert calls[1][0][0] == "bob"


def test_reorganize_all_digests_skips_when_digest_not_found(mocker):
    """digest.json が見つからない場合、処理と通知をスキップすることを確認する。"""
    creds = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user123", credentials=creds, drive_folder_id="folder-abc")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.find_file.return_value = None

    mock_notifier_class = mocker.patch("function_app.LineNotifier")
    mock_notifier_instance = mocker.Mock()
    mock_notifier_class.return_value = mock_notifier_instance

    reorganize_all_digests()

    # 通知が送信されないことを確認
    mock_notifier_instance.send_notification.assert_not_called()


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


def test_reorganize_all_digests_continues_on_failure_notification_error(mocker):
    """失敗通知の送信に失敗しても処理が継続することを確認する。"""
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
    mock_notifier_instance.send_notification.side_effect = Exception("Notification error")
    mock_notifier_class.return_value = mock_notifier_instance

    # エラーが発生してもプロセスが継続することを確認（例外が発生しない）
    reorganize_all_digests()

    # 失敗通知の送信が試みられたことを確認
    mock_notifier_instance.send_notification.assert_called_once()

