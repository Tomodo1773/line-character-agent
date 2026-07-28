"""テスト共通のダミー設定。

`config.get_settings` は必須の環境変数をまとめて検証するため、どのテストでも一式が要る。
キャッシュを持つ生成物は前後で捨て、テスト間で設定が漏れないようにする。
"""

import pytest

CHANNEL_SECRET = "test-channel-secret"
DIARY_USER_ID = "U-owner"
STORAGE_ACCOUNT_NAME = "examplestorage"
DIARY_BACKUP_CONTAINER_NAME = "diary-backup"

ENVIRONMENT = {
    "LINE_CHANNEL_SECRET": CHANNEL_SECRET,
    "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
    "COSMOS_DB_ACCOUNT_URL": "https://example.documents.azure.com:443/",
    "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/dummy",
    "HOSTED_AGENT_NAME": "character-agent",
    "STORAGE_ACCOUNT_NAME": STORAGE_ACCOUNT_NAME,
    "DIARY_BACKUP_CONTAINER_NAME": DIARY_BACKUP_CONTAINER_NAME,
    "DIARY_USER_ID": DIARY_USER_ID,
}


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch):
    import config
    import line_client

    for key, value in ENVIRONMENT.items():
        monkeypatch.setenv(key, value)

    config.get_settings.cache_clear()
    line_client._webhook_parser.cache_clear()
    yield
    config.get_settings.cache_clear()
    line_client._webhook_parser.cache_clear()
