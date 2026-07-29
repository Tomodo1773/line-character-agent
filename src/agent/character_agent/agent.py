"""Microsoft Agent Framework によるシングルエージェントの定義。"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_framework import Agent, MCPStreamableHTTPTool, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from character_agent.config import create_logger, get_settings
from character_agent.prompts import CHARACTER_PROMPT
from character_agent.tools import TOOLS

logger = create_logger(__name__)

AGENT_NAME = "character-agent"

SKILLS_DIR = Path(__file__).parent / "skills"

# Toolbox の MCP エンドポイントを叩くためのトークンのスコープ。
TOOLBOX_SCOPE = "https://ai.azure.com/.default"

# エージェントから見た Toolbox の呼び名。MCP サーバーが公開する個々のツール名とは別物。
TOOLBOX_TOOL_NAME = "foundry_toolbox"

# Toolbox が公開する Web 検索ツールの名前。評価データセットとテストがこの名前で期待値を書く。
WEB_SEARCH_TOOL_NAME = "web_search"


def create_skills_provider() -> SkillsProvider:
    """`skills/` 配下の SKILL.md を発見し、progressive disclosure で読み込めるようにする。

    スキルはリポジトリでコンテナに同梱する信頼できるものだけで、LINE 越しの会話にはツール承認を
    返す相手がいないため、`load_skill` / `read_skill_resource` の承認は求めない。
    スクリプトは持たないので `script_runner` は設定しない。
    """
    logger.info("create_skills_provider が呼び出されました")
    return SkillsProvider.from_paths(
        skill_paths=str(SKILLS_DIR),
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
    )


def toolbox_endpoint() -> str:
    """Foundry Toolbox の MCP エンドポイント URL を組み立てる。

    バージョンを含めない形は Toolbox の既定バージョンへ解決される。Toolbox 側で新しい
    バージョンを既定へ昇格させれば、エージェントを再デプロイせずにツール構成が入れ替わる。
    """
    settings = get_settings()
    base = settings.foundry_project_endpoint.rstrip("/")
    return f"{base}/toolboxes/{settings.toolbox_name}/mcp?api-version=v1"


def toolbox_headers(credential: DefaultAzureCredential) -> Callable[[dict[str, Any]], dict[str, str]]:
    """Toolbox へのリクエストに毎回載せる Entra 認証ヘッダを作る（ADR-0001 §6・キーは使わない）。

    トークンの取得と更新は `get_bearer_token_provider` が持つ。
    """
    token = get_bearer_token_provider(credential, TOOLBOX_SCOPE)
    return lambda _: {"Authorization": f"Bearer {token()}"}


def create_toolbox_tool(credential: DefaultAzureCredential) -> MCPStreamableHTTPTool:
    """Foundry Toolbox へ MCP で接続するツールを作る（ADR-0001 §2 の Web 検索）。

    ホステッドエージェントはエージェント定義への Foundry 側ツールの直接追加をサポートしないため、
    Web 検索は Toolbox に登録し、その MCP エンドポイント越しに使う。どのツールが並ぶかは
    Toolbox の定義（`azure.yaml` の `web-search-tools` サービス）が決め、ここでは接続だけを持つ。

    認証は `header_provider` で毎回 Entra のトークンを載せる。フレームワークがこのヘッダを
    `url` と同一オリジンのリクエストにだけ付けるため、リダイレクト先へトークンが漏れない。
    LINE 越しの会話にはツール承認を返す相手がいないので、承認は求めない。
    """
    logger.info("create_toolbox_tool が呼び出されました")
    return MCPStreamableHTTPTool(
        name=TOOLBOX_TOOL_NAME,
        url=toolbox_endpoint(),
        description="Foundry Toolbox が公開するツール群。最新情報を調べる Web 検索はここにある。",
        header_provider=toolbox_headers(credential),
        # 使うのはツールだけで、Toolbox 側のプロンプトは読み込まない。
        load_prompts=False,
        approval_mode="never_require",
    )


def create_agent(model: str | None = None) -> Agent:
    """ホステッドエージェントとして公開するエージェントを組み立てる。

    モデルは Foundry プロジェクトのエンドポイント経由で Entra 認証により呼び出す。
    モデル名は環境変数で切り替える前提のため、コードには持たせない（ADR-0001 モデル選定）。
    `model` は評価でモデルを差し替えるための引数で、通常は指定しない（`evals/run_eval.py`）。
    """
    logger.info("create_agent が呼び出されました")
    settings = get_settings()
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=model or settings.model_deployment_name,
        credential=credential,
    )
    # ツールが投げた例外の内容をモデルに返す。日付の指定ミスなどをモデル自身が直せるようにする。
    client.function_invocation_configuration["include_detailed_errors"] = True

    return Agent(
        client=client,
        name=AGENT_NAME,
        instructions=CHARACTER_PROMPT,
        # MCP ツールはフレームワークが実行時に接続し、公開されたツールを一覧へ足す。
        tools=[*TOOLS, create_toolbox_tool(credential)],
        context_providers=[create_skills_provider()],
        # 会話履歴はホスティング基盤が管理するため、エージェント側では保存しない（ADR-0001 §3）。
        default_options={"store": False},
    )
