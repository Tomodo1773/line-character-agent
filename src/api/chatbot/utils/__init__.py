def remove_trailing_newline(text: str) -> str:
    """
    入力されたテキストの最後の改行を削除する関数

    :param text: 入力テキスト
    :return: 最後の改行が削除されたテキスト
    """
    return text.rstrip("\n")
