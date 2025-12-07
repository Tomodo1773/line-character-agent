"""line_notifier.py のテスト。"""

import os
from unittest.mock import MagicMock, patch

import pytest

from line_notifier import LineNotifier


@patch.dict(os.environ, {"LINE_CHANNEL_ACCESS_TOKEN": "test_token_123"})
@patch("line_notifier.MessagingApi")
@patch("line_notifier.ApiClient")
def test_line_notifier_sends_notification(mock_api_client, mock_messaging_api):
    """LINE 通知が正しく送信されることを確認する。"""
    # Setup
    mock_messaging_instance = MagicMock()
    mock_messaging_api.return_value = mock_messaging_instance

    notifier = LineNotifier()

    # Execute
    notifier.send_notification("U1234567890", "テストメッセージ")

    # Verify
    assert mock_messaging_instance.push_message.called
    call_args = mock_messaging_instance.push_message.call_args
    request = call_args[0][0]
    assert request.to == "U1234567890"
    assert len(request.messages) == 1
    assert request.messages[0].text == "テストメッセージ"


@patch.dict(os.environ, {}, clear=True)
def test_line_notifier_raises_error_when_token_missing():
    """環境変数が設定されていない場合、エラーが発生することを確認する。"""
    with pytest.raises(ValueError, match="LINE_CHANNEL_ACCESS_TOKEN is required"):
        LineNotifier()


@patch("line_notifier.MessagingApi")
@patch("line_notifier.ApiClient")
def test_line_notifier_with_explicit_token(mock_api_client, mock_messaging_api):
    """明示的にトークンを渡した場合の動作を確認する。"""
    mock_messaging_instance = MagicMock()
    mock_messaging_api.return_value = mock_messaging_instance

    notifier = LineNotifier(access_token="explicit_token_456")

    notifier.send_notification("U9876543210", "明示的トークンのテスト")

    assert mock_messaging_instance.push_message.called


@patch.dict(os.environ, {"LINE_CHANNEL_ACCESS_TOKEN": "test_token_123"})
@patch("line_notifier.MessagingApi")
@patch("line_notifier.ApiClient")
def test_line_notifier_propagates_error_on_failure(mock_api_client, mock_messaging_api):
    """通知送信に失敗した場合、エラーが呼び出し元に伝播することを確認する。"""
    mock_messaging_instance = MagicMock()
    mock_messaging_instance.push_message.side_effect = Exception("API Error")
    mock_messaging_api.return_value = mock_messaging_instance

    notifier = LineNotifier()

    with pytest.raises(Exception, match="API Error"):
        notifier.send_notification("U1234567890", "エラーテスト")
