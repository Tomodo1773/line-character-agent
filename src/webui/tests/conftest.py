import pytest

from diary_admin.config import get_settings


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch):
    """すべてのテストでダミーの設定値を使う。Cosmos DB への接続は行わない。"""
    monkeypatch.setenv("COSMOS_DB_ACCOUNT_URL", "https://example.documents.azure.com:443/")
    monkeypatch.setenv("DIARY_USER_ID", "U-test")
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
