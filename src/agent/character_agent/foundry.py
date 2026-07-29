"""Foundry プロジェクト経由で埋め込みを作るクライアント。

エンドポイントとトークンの取り回しは `AIProjectClient.get_openai_client` に任せる
（`{project_endpoint}/openai/v1` に Entra 認証で接続する）。ADR-0001 §6 のとおり
`OPENAI_API_KEY` は使わない。

ここに置くのはベクトル索引のための埋め込み生成だけとする。文章を作る生成 LLM の呼び出しは
メインエージェント自身の役割で、ツールの内側からは行わない（`tools.py` の冒頭を参照）。
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
