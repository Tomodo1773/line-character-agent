"""Foundry プロジェクト経由でモデルを呼び出すクライアント。

エンドポイントとトークンの取り回しは `AIProjectClient.get_openai_client` に任せる
（`{project_endpoint}/openai/v1` に Entra 認証で接続する）。ADR-0001 §6 のとおり
`OPENAI_API_KEY` は使わない。
"""

from functools import lru_cache

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from openai import OpenAI

from character_agent.config import create_logger, get_settings

logger = create_logger(__name__)


@lru_cache(maxsize=1)
def _openai_client() -> OpenAI:
    project = AIProjectClient(endpoint=get_settings().foundry_project_endpoint, credential=DefaultAzureCredential())
    return project.get_openai_client()


def embed(text: str) -> list[float]:
    """テキストの埋め込みベクトルを返す。"""
    logger.info("embed が呼び出されました")
    response = _openai_client().embeddings.create(model=get_settings().embedding_deployment_name, input=text)
    return response.data[0].embedding


def complete(instructions: str, text: str) -> str:
    """モデルに1往復だけ問い合わせ、応答テキストを返す。

    会話ではなく単発の変換処理に使うため、履歴は保存しない（`store=False`）。
    """
    logger.info("complete が呼び出されました")
    response = _openai_client().responses.create(
        model=get_settings().model_deployment_name,
        instructions=instructions,
        input=text,
        store=False,
    )
    return response.output_text
