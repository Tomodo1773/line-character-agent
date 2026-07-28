"""ホステッドエージェントの Responses エンドポイントを呼び出すクライアント。

エンドポイントとトークンの取り回しは `AIProjectClient.get_openai_client` に任せる
（`{project_endpoint}/agents/{name}/endpoint/protocols/openai/responses` に Entra 認証で接続する）。
"""

from functools import lru_cache

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from config import get_settings
from logger import create_logger

logger = create_logger(__name__)


@lru_cache(maxsize=1)
def _openai_client():
    settings = get_settings()
    project = AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=DefaultAzureCredential())
    return project.get_openai_client(agent_name=settings.hosted_agent_name)


def create_conversation() -> str:
    """新しい会話を作り、その ID を返す。"""
    logger.info("create_conversation が呼び出されました")
    return _openai_client().conversations.create().id


def respond(conversation_id: str, text: str) -> str:
    """会話の続きとしてメッセージを送り、応答テキストを返す。

    会話 ID を渡す限り履歴はプラットフォームが保持するので、アプリ側では過去の発言を送らない。
    """
    logger.info("respond が呼び出されました: conversation_id=%s", conversation_id)
    response = _openai_client().responses.create(input=text, extra_body={"conversation": conversation_id})
    return response.output_text
