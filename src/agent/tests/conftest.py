import pytest

from character_agent.config import get_settings


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch):
    """すべてのテストでダミーの設定値を使う。実際の接続は行わない。"""
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.services.ai.azure.com/api/projects/dummy")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "dummy-deployment")
    monkeypatch.setenv("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", "dummy-embedding")
    monkeypatch.setenv("COSMOS_DB_ACCOUNT_URL", "https://example.documents.azure.com:443/")
    monkeypatch.setenv("DIARY_USER_ID", "U-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
