"""Tests for flex message generation functions."""

from linebot.v3.messaging import FlexMessage

from chatbot.main import create_google_drive_auth_flex_message


def test_create_google_drive_auth_flex_message():
    """
    Google Drive OAuth認証用のFlex Messageが正しく生成されることをテスト
    - 有効なFlexMessageオブジェクトが返されることを確認
    - auth URLが埋め込まれていることを確認
    """
    test_auth_url = "https://accounts.google.com/o/oauth2/auth?test=true"
    
    # Flex Messageを生成
    flex_message = create_google_drive_auth_flex_message(test_auth_url)
    
    # 有効なFlexMessageオブジェクトが返されることを確認
    assert isinstance(flex_message, FlexMessage), "FlexMessageオブジェクトが返されていません"
    assert flex_message.alt_text == "Google Drive連携の設定", "alt_textが正しく設定されていません"
    
    # contentsが存在し、FlexContainerオブジェクトであることを確認
    assert flex_message.contents is not None, "contentsがNoneです"
    assert hasattr(flex_message.contents, "type"), "contentsにtype属性がありません"
    
    # auth URLが埋め込まれていることを確認
    # FlexMessageをJSON形式にシリアライズしてURLを検索
    try:
        import json
        message_dict = flex_message.to_dict()
        message_json = json.dumps(message_dict)
        assert test_auth_url in message_json, f"auth URLがメッセージに含まれていません: {test_auth_url}"
    except Exception as e:
        # to_dict()が失敗した場合、contentsオブジェクトを直接文字列化して確認
        contents_str = str(flex_message.contents)
        assert test_auth_url in contents_str, f"auth URLがメッセージに含まれていません: {test_auth_url}"
