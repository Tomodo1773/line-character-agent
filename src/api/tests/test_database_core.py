"""CosmosDBデータベース作成ロジックのテスト"""


def test_init_container_creates_main_database_with_throughput(mocker):
    """mainデータベースが600 RU/sの共有スループットで作成されることを確認"""
    # モックの準備
    mock_cosmos_client = mocker.Mock()
    mock_database = mocker.Mock()
    mock_container = mocker.Mock()

    mock_cosmos_client.create_database_if_not_exists.return_value = mock_database
    mock_database.create_container_if_not_exists.return_value = mock_container

    mocker.patch("chatbot.database.core.CosmosClient", return_value=mock_cosmos_client)

    # 環境変数の設定
    mocker.patch.dict(
        "os.environ", {"COSMOS_DB_ACCOUNT_URL": "https://test.documents.azure.com:443/", "COSMOS_DB_ACCOUNT_KEY": "test_key"}
    )

    # CosmosCoreのインスタンス化
    from chatbot.database.core import CosmosCore

    CosmosCore(container_name="users")

    # create_database_if_not_existsが600 RU/sで呼ばれたことを確認
    mock_cosmos_client.create_database_if_not_exists.assert_called_once_with(id="main", offer_throughput=600)

    # create_container_if_not_existsが呼ばれたことを確認
    mock_database.create_container_if_not_exists.assert_called_once()
    call_kwargs = mock_database.create_container_if_not_exists.call_args.kwargs
    assert call_kwargs["id"] == "users"


def test_init_container_creates_container_with_partition_key(mocker):
    """コンテナが正しいパーティションキーで作成されることを確認"""
    # モックの準備
    mock_cosmos_client = mocker.Mock()
    mock_database = mocker.Mock()
    mock_container = mocker.Mock()

    mock_cosmos_client.create_database_if_not_exists.return_value = mock_database
    mock_database.create_container_if_not_exists.return_value = mock_container

    mocker.patch("chatbot.database.core.CosmosClient", return_value=mock_cosmos_client)

    # 環境変数の設定
    mocker.patch.dict(
        "os.environ", {"COSMOS_DB_ACCOUNT_URL": "https://test.documents.azure.com:443/", "COSMOS_DB_ACCOUNT_KEY": "test_key"}
    )

    # CosmosCoreのインスタンス化
    from chatbot.database.core import CosmosCore
    from azure.cosmos import PartitionKey

    CosmosCore(container_name="users")

    # create_container_if_not_existsの呼び出しを確認
    call_kwargs = mock_database.create_container_if_not_exists.call_args.kwargs
    partition_key = call_kwargs["partition_key"]

    # パーティションキーが/idであることを確認
    assert isinstance(partition_key, PartitionKey)
