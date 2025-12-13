"""CosmosDB entriesコンテナ作成ロジックのテスト"""

import pytest


def test_ensure_entries_container_creates_with_correct_config(mocker):
    """entriesコンテナが適切な設定で作成されることを確認"""
    # モックの準備
    mock_database = mocker.Mock()

    # _ensure_entries_containerを直接テスト
    from chatbot.agent.tools import _ensure_entries_container

    _ensure_entries_container(mock_database)

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
    import logging

    caplog.set_level(logging.INFO)

    # モックの準備
    mock_database = mocker.Mock()

    # _ensure_entries_containerを呼び出し
    from chatbot.agent.tools import _ensure_entries_container

    _ensure_entries_container(mock_database)

    # ログ出力の確認
    assert "entriesコンテナの準備が完了しました" in caplog.text


def test_ensure_entries_container_logs_and_raises_on_error(mocker, caplog):
    """コンテナ作成失敗時にログ出力と例外発生を確認"""
    import logging

    caplog.set_level(logging.ERROR)

    # モックの準備
    mock_database = mocker.Mock()
    mock_database.create_container_if_not_exists.side_effect = Exception("Container creation failed")

    # _ensure_entries_containerで例外が発生することを確認
    from chatbot.agent.tools import _ensure_entries_container

    with pytest.raises(Exception, match="Container creation failed"):
        _ensure_entries_container(mock_database)

    # エラーログの確認
    assert "entriesコンテナの作成/確認でエラーが発生しました" in caplog.text


def test_get_cosmos_container_calls_ensure(mocker):
    """get_cosmos_container()が_ensure_entries_containerを呼び出すことを確認"""
    # モックの準備
    mock_cosmos_client = mocker.Mock()
    mock_database = mocker.Mock()
    mock_container = mocker.Mock()

    mock_cosmos_client.get_database_client.return_value = mock_database
    mock_database.get_container_client.return_value = mock_container

    mocker.patch("chatbot.agent.tools.get_cosmos_client", return_value=mock_cosmos_client)

    # get_cosmos_containerを呼び出し
    from chatbot.agent.tools import get_cosmos_container

    # グローバル変数をリセット
    import chatbot.agent.tools as tools_module

    tools_module._cosmos_container = None

    container = get_cosmos_container()

    # データベースとコンテナクライアントが取得されたことを確認
    mock_cosmos_client.get_database_client.assert_called_once_with("diary")
    mock_database.create_container_if_not_exists.assert_called_once()
    mock_database.get_container_client.assert_called_once_with("entries")
    assert container == mock_container
