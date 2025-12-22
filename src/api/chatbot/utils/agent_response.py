from typing import Any, Tuple


def _extract_interrupt_message(interrupts: list[Any]) -> str:
    """
    interrupt payload は `ensure_oauth_settings_node` または `ensure_folder_id_settings_node` が投入する
    `{type: missing_oauth_credentials, message: ...}` または `{type: missing_drive_folder_id, message: ...}` を想定する。
    """
    if not interrupts:
        return "入力が必要みたい。フォルダのURLかIDを送ってね。"

    value = getattr(interrupts[0], "value", None)
    if isinstance(value, dict):
        message = value.get("message")
        if isinstance(message, str):
            return message

    if isinstance(value, str):
        return value

    return "入力が必要みたい。フォルダのURLかIDを送ってね。"


def extract_agent_text(response: dict[str, Any]) -> Tuple[str, bool]:
    """
    LangGraphのレスポンスから表示用テキストとinterruptフラグを取り出す。

    戻り値:
        (text, is_interrupt)
        - is_interrupt=True のとき text は __interrupt__ 由来
        - is_interrupt=False のとき text は messages[-1].content 由来
    """
    if response.get("__interrupt__"):
        text = _extract_interrupt_message(response["__interrupt__"])
        return text, True

    messages = response.get("messages") or []
    if not messages:
        raise ValueError("Agent response has no messages or __interrupt__.")

    last = messages[-1]
    if isinstance(last, dict):
        content = last.get("content", "")
    else:
        content = getattr(last, "content", "")

    if not isinstance(content, str):
        content = str(content)

    return content, False
