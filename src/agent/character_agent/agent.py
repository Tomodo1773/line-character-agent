"""Microsoft Agent Framework によるシングルエージェントの定義。"""

import os
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from character_agent.config import create_logger
from character_agent.prompts import CHARACTER_PROMPT

logger = create_logger(__name__)

AGENT_NAME = "character-agent"

_JAPAN = ZoneInfo("Asia/Tokyo")


@tool(approval_mode="never_require", description="現在の日本時間（日付・時刻・曜日）を取得する。")
def get_current_datetime() -> Annotated[str, "yyyy-mm-dd hh:mm:ss (曜日) 形式の日本時間"]:
    """現在の日本時間を返す。

    プロンプトに日時を埋め込むとコンテナの起動時刻で固定されてしまうため、ツールとして都度取得する。
    """
    logger.info("get_current_datetime が呼び出されました")
    return datetime.now(_JAPAN).strftime("%Y-%m-%d %H:%M:%S (%a)")


def create_agent() -> Agent:
    """ホステッドエージェントとして公開するエージェントを組み立てる。

    モデルは Foundry プロジェクトのエンドポイント経由で Entra 認証により呼び出す。
    モデル名は環境変数で切り替える前提のため、コードには持たせない（ADR-0001 モデル選定）。
    """
    logger.info("create_agent が呼び出されました")

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    return Agent(
        client=client,
        name=AGENT_NAME,
        instructions=CHARACTER_PROMPT,
        tools=[get_current_datetime],
        # 会話履歴はホスティング基盤が管理するため、エージェント側では保存しない（ADR-0001 §3）。
        default_options={"store": False},
    )
