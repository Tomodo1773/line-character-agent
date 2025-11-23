import datetime

from langchain_core.documents import Document

from function_app import upload_recent_diaries


def _fixed_now():
    """UTC固定時刻（2025-01-10 12:00:00）を返すヘルパー。"""

    return datetime.datetime(2025, 1, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)


def test_excludes_and_orders_documents(mocker):
    """除外ファイルをスキップし、残りを順序通り upload するか。"""

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        ("user-1", token)
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    modified = _fixed_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    mock_drive.list.return_value = [
        {"id": "f1", "name": "dictionary.md", "createdTime": modified, "modifiedTime": modified},
        {"id": "f2", "name": "note.md", "createdTime": modified, "modifiedTime": modified},
        {"id": "f3", "name": "draft.md", "createdTime": modified, "modifiedTime": modified},
    ]
    mock_drive.get.side_effect = [
        Document(page_content="note", metadata={"source": "note.md"}),
        Document(page_content="draft", metadata={"source": "draft.md"}),
    ]

    mock_uploader = mocker.patch("function_app.CosmosDBUploader").return_value

    upload_recent_diaries(span_days=1)

    # 除外1件を除き、2件が順序通り渡される
    uploaded_docs = mock_uploader.upload.call_args[0][0]
    assert [d.metadata["source"] for d in uploaded_docs] == ["note.md", "draft.md"]


def test_multiple_users_isolated_uploads(mocker):
    """ユーザーごとにハンドラ／アップローダが分かれて呼ばれるか。"""

    creds1, creds2 = mocker.Mock(), mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        ("alice", creds1),
        ("bob", creds2),
    ]

    drive1, drive2 = mocker.Mock(), mocker.Mock()
    drive1.list.return_value = [{"id": "a1", "name": "alice.md", "createdTime": "", "modifiedTime": ""}]
    drive2.list.return_value = [{"id": "b1", "name": "bob.md", "createdTime": "", "modifiedTime": ""}]
    drive1.get.return_value = Document(page_content="alice", metadata={"source": "alice.md"})
    drive2.get.return_value = Document(page_content="bob", metadata={"source": "bob.md"})

    mocker.patch("function_app.GoogleDriveHandler", side_effect=[drive1, drive2])

    uploader1, uploader2 = mocker.Mock(), mocker.Mock()
    mocker.patch("function_app.CosmosDBUploader", side_effect=[uploader1, uploader2])

    upload_recent_diaries(span_days=1)

    uploader1.upload.assert_called_once()
    uploader2.upload.assert_called_once()
    assert uploader1.upload.call_args[0][0][0].metadata["source"] == "alice.md"
    assert uploader2.upload.call_args[0][0][0].metadata["source"] == "bob.md"


def test_modified_after_is_calculated_from_span_days(mocker, monkeypatch):
    """cutoff の ISO8601 文字列が span_days に応じて計算されるか。"""

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return _fixed_now()

    monkeypatch.setattr("function_app.datetime.datetime", FixedDateTime)

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        ("user-1", token)
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.list.return_value = []

    mocker.patch("function_app.CosmosDBUploader")

    upload_recent_diaries(span_days=2)

    modified_after = mock_drive.list.call_args.kwargs["modified_after"]
    assert modified_after == "2025-01-08T12:00:00Z"


def test_no_files_skip_upload(mocker):
    """ファイルが無い場合に upload が呼ばれないか。"""

    token = mocker.Mock()
    mocker.patch("function_app.GoogleUserTokenManager").return_value.get_all_user_credentials.return_value = [
        ("user-1", token)
    ]

    mock_drive = mocker.patch("function_app.GoogleDriveHandler").return_value
    mock_drive.list.return_value = []

    mock_uploader = mocker.patch("function_app.CosmosDBUploader").return_value

    upload_recent_diaries(span_days=1)

    mock_uploader.upload.assert_not_called()
