def split_text(text: str, max_length: int = 50) -> list[str]:
    """テキストを適切な長さに分割する

    Args:
        text (str): 分割する元のテキスト
        max_length (int, optional): 1メッセージの最大文字数. Defaults to 50.

    Returns:
        list[str]: 分割されたメッセージのリスト
    """
    lines = text.split("\n")
    result = []

    for line in lines:
        if not line:
            continue

        sentences = line.split("。")
        for sentence in sentences:
            if not sentence:
                continue

            if len(sentence) > max_length:
                parts = sentence.split("、")
                result.extend([f"{p}、" for p in parts[:-1]] + [parts[-1]])
            else:
                result.append(sentence)

    return [f"{msg}。" if i < len(result) - 1 else msg for i, msg in enumerate(result)]
