"""CosmosDBUploaderのコンテナ作成ロジックのテスト"""

import pytest


def test_ensure_entries_container_creates_with_correct_config(mocker):
    """entriesコンテナが適切な設定で作成されることを確認"""
    # モックの準備
    mock_cosmos_client = mocker.patch("cosmosdb.CosmosClient")
    mocker.patch("cosmosdb.OpenAI")

    mock_database = mocker.Mock()
    mock_cosmos_instance = mock_cosmos_client.return_value
    mock_cosmos_instance.get_database_client.return_value = mock_database

    # 環境変数の設定
    mocker.patch.dict(
        "os.environ",
        {
            "COSMOS_DB_ACCOUNT_URL": "https://test.documents.azure.com:443/",
            "COSMOS_DB_ACCOUNT_KEY": "test_key",
            "OPENAI_API_KEY": "test_openai_key",
        },
    )

    # CosmosDBUploaderのインスタンス化
    from cosmosdb import CosmosDBUploader

    CosmosDBUploader(userid="test_user")

    # create_container_if_not_existsが適切なパラメータで呼ばれたことを確認
    mock_database.create_container_if_not_exists.assert_called_once()
    call_kwargs = mock_database.create_container_if_not_exists.call_args.kwargs

    assert call_kwargs["id"] == "entries"
    assert call_kwargs["offer_throughput"] == 400
    assert "indexing_policy" in call_kwargs
    assert "vector_embedding_policy" in call_kwargs

    # インデックスポリシーの確認
    indexing_policy = call_kwargs["indexing_policy"]
    assert indexing_policy["indexingMode"] == "consistent"
    assert indexing_policy["automatic"] is True
    assert len(indexing_policy["vectorIndexes"]) == 1
    assert indexing_policy["vectorIndexes"][0]["path"] == "/contentVector"
    assert indexing_policy["vectorIndexes"][0]["type"] == "diskANN"

    # ベクトル埋め込みポリシーの確認
    vector_policy = call_kwargs["vector_embedding_policy"]
    assert len(vector_policy["vectorEmbeddings"]) == 1
    assert vector_policy["vectorEmbeddings"][0]["path"] == "/contentVector"
    assert vector_policy["vectorEmbeddings"][0]["dimensions"] == 1536
    assert vector_policy["vectorEmbeddings"][0]["distanceFunction"] == "cosine"


def test_ensure_entries_container_logs_on_success(mocker, caplog):
    """コンテナ作成成功時にログが出力されることを確認"""
    # モックの準備
    mock_cosmos_client = mocker.patch("cosmosdb.CosmosClient")
    mocker.patch("cosmosdb.OpenAI")

    mock_database = mocker.Mock()
    mock_cosmos_instance = mock_cosmos_client.return_value
    mock_cosmos_instance.get_database_client.return_value = mock_database

    # 環境変数の設定
    mocker.patch.dict(
        "os.environ",
        {
            "COSMOS_DB_ACCOUNT_URL": "https://test.documents.azure.com:443/",
            "COSMOS_DB_ACCOUNT_KEY": "test_key",
            "OPENAI_API_KEY": "test_openai_key",
        },
    )

    # CosmosDBUploaderのインスタンス化
    from cosmosdb import CosmosDBUploader
    import logging

    caplog.set_level(logging.INFO)

    CosmosDBUploader(userid="test_user")

    # ログ出力の確認
    assert "entriesコンテナの準備が完了しました" in caplog.text


def test_ensure_entries_container_raises_on_error(mocker):
    """コンテナ作成失敗時に例外が発生することを確認"""
    # モックの準備
    mock_cosmos_client = mocker.patch("cosmosdb.CosmosClient")
    mocker.patch("cosmosdb.OpenAI")

    mock_database = mocker.Mock()
    mock_cosmos_instance = mock_cosmos_client.return_value
    mock_cosmos_instance.get_database_client.return_value = mock_database

    # create_container_if_not_existsで例外を発生させる
    mock_database.create_container_if_not_exists.side_effect = Exception("Container creation failed")

    # 環境変数の設定
    mocker.patch.dict(
        "os.environ",
        {
            "COSMOS_DB_ACCOUNT_URL": "https://test.documents.azure.com:443/",
            "COSMOS_DB_ACCOUNT_KEY": "test_key",
            "OPENAI_API_KEY": "test_openai_key",
        },
    )

    # CosmosDBUploaderのインスタンス化で例外が発生することを確認
    from cosmosdb import CosmosDBUploader

    with pytest.raises(Exception, match="Container creation failed"):
        CosmosDBUploader(userid="test_user")
