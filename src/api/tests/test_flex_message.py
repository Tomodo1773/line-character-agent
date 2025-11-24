"""Tests for flex message generation functions."""

from linebot.v3.messaging import FlexMessage

from chatbot.main import create_google_drive_auth_flex_message


def test_create_google_drive_auth_flex_message():
    """
    Google Drive OAuth認証用のFlex Messageが正しく生成されることをテスト
    - FlexMessageオブジェクトが返されることを確認（有効なフォーマット）
    - auth URLが埋め込まれていることを確認
    """
    test_auth_url = "https://accounts.google.com/o/oauth2/auth?test=true"
    
    flex_message = create_google_drive_auth_flex_message(test_auth_url)
    
    # 有効なFlexMessageオブジェクトが返されることを確認
    assert isinstance(flex_message, FlexMessage)
    assert flex_message.alt_text is not None
    
    # to_dict()で有効なJSON構造に変換できることを確認
    message_dict = flex_message.to_dict()
    assert "contents" in message_dict
    assert message_dict["contents"]["type"] == "bubble"
    
    # auth URLが埋め込まれていることを確認
    # メッセージをJSON文字列に変換してURLが含まれているか確認
    import json
    message_json = json.dumps(message_dict)
    assert test_auth_url in message_json
