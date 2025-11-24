"""Tests for flex message generation functions."""

from linebot.v3.messaging import FlexMessage

from chatbot.main import create_google_drive_auth_flex_message


def test_create_google_drive_auth_flex_message():
    """
    Google Drive OAuth認証用のFlex Messageが正しく生成されることをテスト
    - FlexMessageオブジェクトが返されることを確認
    - alt_textが設定されていることを確認
    - contents構造をJSON形式で検証
    - buttonのURIが正しく設定されていることを確認
    """
    test_auth_url = "https://accounts.google.com/o/oauth2/auth?test=true"
    
    flex_message = create_google_drive_auth_flex_message(test_auth_url)
    
    # FlexMessageオブジェクトが返されることを確認
    assert isinstance(flex_message, FlexMessage)
    
    # alt_textが設定されていることを確認
    assert flex_message.alt_text == "Google Drive連携の設定"
    
    # contentsをJSONに変換して検証
    # LINE SDK v3では、contentsはFlexContainerオブジェクトとして返される
    contents_dict = flex_message.to_dict()["contents"]
    
    # contentsの構造を確認
    assert contents_dict["type"] == "bubble"
    # Note: LINE SDK v3はto_dict()でsizeフィールドを保持しない場合がある
    
    # headerの確認
    assert "header" in contents_dict
    header = contents_dict["header"]
    assert header["type"] == "box"
    assert len(header["contents"]) > 0
    assert header["contents"][0]["text"] == "Google Drive 連携"
    
    # bodyの確認
    assert "body" in contents_dict
    body = contents_dict["body"]
    assert body["type"] == "box"
    assert len(body["contents"]) > 0
    assert "Google Drive" in body["contents"][0]["text"]
    assert body["contents"][0]["wrap"] is True
    
    # footerの確認
    assert "footer" in contents_dict
    footer = contents_dict["footer"]
    assert footer["type"] == "box"
    assert len(footer["contents"]) > 0
    
    # buttonの確認
    button = footer["contents"][0]
    assert button["type"] == "button"
    assert button["action"]["type"] == "uri"
    assert button["action"]["label"] == "認証ページへ進む"
    assert button["action"]["uri"] == test_auth_url
    assert button["color"] == "#0F9D58"
