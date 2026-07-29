"""Responses プロトコルのサーバーとしてエージェントを公開するエントリポイント。

`/responses` と `/readiness` のルーティング、SSE ストリーミング、Application Insights への
OpenTelemetry トレース送出はプロトコルライブラリが担うため、ここでの実装は不要。
"""

from agent_framework_foundry_hosting import ResponsesHostServer

from character_agent.agent import create_agent
from character_agent.config import create_logger

logger = create_logger(__name__)


def main() -> None:
    logger.info("エージェントサーバーを起動します")
    ResponsesHostServer(create_agent()).run()


if __name__ == "__main__":
    main()
