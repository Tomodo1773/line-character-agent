"""Functions アプリが使う環境変数の定義。

ランタイム側に `os.environ` を散在させず、必要な値をここで一括して検証する。
値が足りなければ最初の利用時に明確なエラーで落ちる。
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """LINE 経路の Function が必要とする設定値。"""

    line_channel_secret: str
    line_channel_access_token: str
    cosmos_db_account_url: str
    foundry_project_endpoint: str
    hosted_agent_name: str


def _required(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(f"環境変数 {key} が設定されていません")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定値を読み込む（プロセス内で1回だけ評価する）。"""
    return Settings(
        line_channel_secret=_required("LINE_CHANNEL_SECRET"),
        line_channel_access_token=_required("LINE_CHANNEL_ACCESS_TOKEN"),
        cosmos_db_account_url=_required("COSMOS_DB_ACCOUNT_URL"),
        foundry_project_endpoint=_required("FOUNDRY_PROJECT_ENDPOINT"),
        hosted_agent_name=_required("HOSTED_AGENT_NAME"),
    )
