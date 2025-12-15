import os


def resolve_cosmos_connection_verify() -> bool | str:
    """Cosmos DB 接続時のTLS証明書検証設定を解決する。

    - 未設定: True（検証ON）
    - true/false(0/1/yes/no 含む): bool
    - それ以外: CA証明書バンドルへのパス（requests の verify 引数相当）
    """
    verify_setting = os.getenv("COSMOS_DB_CONNECTION_VERIFY")
    if verify_setting is None or verify_setting == "":
        return True

    lowered = verify_setting.lower()
    if lowered in {"false", "0", "no"}:
        return False
    if lowered in {"true", "1", "yes"}:
        return True

    return verify_setting
