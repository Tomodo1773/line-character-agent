import datetime

from langchain_core.documents import Document

from function_app import upload_recent_diaries
from google_auth import GoogleDriveUserContext


def _fixed_now():
    """UTC固定時刻（2025-01-10 12:00:00）を返すヘルパー。"""

    return datetime.datetime(2025, 1, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)


def test_only_diary_filename_pattern_is_uploaded(mocker):
    """日記ファイル名パターンのみが upload されるか。"""

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user-1", credentials=token, drive_folder_id="folder-1")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    modified = _fixed_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    # 年フォルダを返す
    mock_drive.list_folders.return_value = [{"id": "year-2025", "name": "2025"}]
    mock_drive.list.return_value = [
        {"id": "f1", "name": "note.md", "createdTime": modified, "modifiedTime": modified},
        {"id": "f2", "name": "2025年05月15日(木).md", "createdTime": modified, "modifiedTime": modified},
    ]
    mock_drive.get.side_effect = [
        Document(page_content="2025-05-15", metadata={"source": "2025年05月15日(木).md"}),
    ]

    mock_uploader = mocker.patch("function_app.CosmosDBUploader").return_value

    upload_recent_diaries(span_days=1)

    # 日記ファイル名パターンの1件のみが渡される
    uploaded_docs = mock_uploader.upload.call_args[0][0]
    assert [d.metadata["source"] for d in uploaded_docs] == ["2025年05月15日(木).md"]


def test_multiple_users_isolated_uploads(mocker):
    """ユーザーごとにハンドラ／アップローダが分かれて呼ばれるか（日記ファイル名パターン前提）。"""

    creds1, creds2 = mocker.Mock(), mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="alice", credentials=creds1, drive_folder_id="folder-a"),
        GoogleDriveUserContext(userid="bob", credentials=creds2, drive_folder_id="folder-b"),
    ]

    drive1, drive2 = mocker.Mock(), mocker.Mock()
    drive1.list_folders.return_value = [{"id": "year-2025", "name": "2025"}]
    drive2.list_folders.return_value = [{"id": "year-2025", "name": "2025"}]
    drive1.list.return_value = [{"id": "a1", "name": "2025年05月15日(木).md", "createdTime": "", "modifiedTime": ""}]
    drive2.list.return_value = [{"id": "b1", "name": "2025年05月16日(金).md", "createdTime": "", "modifiedTime": ""}]
    drive1.get.return_value = Document(page_content="alice", metadata={"source": "2025年05月15日(木).md"})
    drive2.get.return_value = Document(page_content="bob", metadata={"source": "2025年05月16日(金).md"})

    mocker.patch("function_app.GoogleDriveHandler", side_effect=[drive1, drive2])

    uploader1, uploader2 = mocker.Mock(), mocker.Mock()
    mocker.patch("function_app.CosmosDBUploader", side_effect=[uploader1, uploader2])

    upload_recent_diaries(span_days=1)

    uploader1.upload.assert_called_once()
    uploader2.upload.assert_called_once()
    assert uploader1.upload.call_args[0][0][0].metadata["source"] == "2025年05月15日(木).md"
    assert uploader2.upload.call_args[0][0][0].metadata["source"] == "2025年05月16日(金).md"


def test_modified_after_is_calculated_from_span_days(mocker, monkeypatch):
    """cutoff の ISO8601 文字列が span_days に応じて計算されるか。"""

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return _fixed_now()

    monkeypatch.setattr("function_app.datetime.datetime", FixedDateTime)

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user-1", credentials=token, drive_folder_id="folder-1")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.list_folders.return_value = [{"id": "year-2025", "name": "2025"}]
    mock_drive.list.return_value = []

    mocker.patch("function_app.CosmosDBUploader")

    upload_recent_diaries(span_days=2)

    modified_after = mock_drive.list.call_args.kwargs["modified_after"]
    assert modified_after == "2025-01-08T12:00:00Z"


def test_no_files_skip_upload(mocker):
    """ファイルが無い場合に upload が呼ばれないか。"""

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user-1", credentials=token, drive_folder_id="folder-1")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.list_folders.return_value = [{"id": "year-2025", "name": "2025"}]
    mock_drive.list.return_value = []

    mock_uploader = mocker.patch("function_app.CosmosDBUploader").return_value

    upload_recent_diaries(span_days=1)

    mock_uploader.upload.assert_not_called()


def test_skip_when_folder_id_missing(mocker):
    """フォルダIDが未設定のユーザーはスキップされるか。"""

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user-1", credentials=token, drive_folder_id=None)
    ]

    drive_class = mocker.patch("function_app.GoogleDriveHandler")
    uploader_class = mocker.patch("function_app.CosmosDBUploader")

    upload_recent_diaries(span_days=1)

    drive_class.assert_not_called()
    uploader_class.assert_not_called()


def test_files_from_multiple_year_folders_are_collected(mocker):
    """複数の年フォルダからファイルを収集できるか。"""

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        GoogleDriveUserContext(userid="user-1", credentials=token, drive_folder_id="folder-1")
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    modified = _fixed_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    # 複数の年フォルダを返す
    mock_drive.list_folders.return_value = [
        {"id": "year-2024", "name": "2024"},
        {"id": "year-2025", "name": "2025"},
    ]
    # 各年フォルダからファイルを返す
    mock_drive.list.side_effect = [
        [{"id": "f1", "name": "2024年12月31日(火).md", "createdTime": modified, "modifiedTime": modified}],
        [{"id": "f2", "name": "2025年01月01日(水).md", "createdTime": modified, "modifiedTime": modified}],
    ]
    mock_drive.get.side_effect = [
        Document(page_content="2024-12-31", metadata={"source": "2024年12月31日(火).md"}),
        Document(page_content="2025-01-01", metadata={"source": "2025年01月01日(水).md"}),
    ]

    mock_uploader = mocker.patch("function_app.CosmosDBUploader").return_value

    upload_recent_diaries(span_days=1)

    # 両方の年フォルダから日記が収集される
    uploaded_docs = mock_uploader.upload.call_args[0][0]
    sources = [d.metadata["source"] for d in uploaded_docs]
    assert "2024年12月31日(火).md" in sources
    assert "2025年01月01日(水).md" in sources
