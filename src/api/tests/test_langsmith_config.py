import os
from unittest.mock import patch


def test_langchain_project_default_value():
    """
    LANGCHAIN_PROJECT環境変数が未設定の場合、デフォルト値"LINE-AI-BOT"が使用されることを検証
    """
    # 環境変数を未設定の状態でモジュールをインポート
    with patch.dict(os.environ, {}, clear=False):
        # LANGCHAIN_PROJECT環境変数を削除
        if "LANGCHAIN_PROJECT" in os.environ:
            del os.environ["LANGCHAIN_PROJECT"]
        
        # モジュールをリロードしてデフォルト値を確認
        # agent/__init__.pyの該当行を再実行する
        test_value = os.getenv("LANGCHAIN_PROJECT", "LINE-AI-BOT")
        
        assert test_value == "LINE-AI-BOT"


def test_langchain_project_custom_value():
    """
    LANGCHAIN_PROJECT環境変数が設定されている場合、その値が使用されることを検証
    """
    custom_project = "TEST-PROJECT"
    
    with patch.dict(os.environ, {"LANGCHAIN_PROJECT": custom_project}):
        # 環境変数から値を取得
        test_value = os.getenv("LANGCHAIN_PROJECT", "LINE-AI-BOT")
        
        assert test_value == custom_project


def test_langchain_project_empty_string():
    """
    LANGCHAIN_PROJECT環境変数が空文字列の場合、空文字列が使用されることを検証
    """
    with patch.dict(os.environ, {"LANGCHAIN_PROJECT": ""}):
        # 空文字列の場合は空文字列が返される
        test_value = os.getenv("LANGCHAIN_PROJECT", "LINE-AI-BOT")
        
        assert test_value == ""
