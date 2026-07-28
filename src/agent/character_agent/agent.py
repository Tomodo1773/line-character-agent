"""Microsoft Agent Framework によるシングルエージェントの定義。"""

from pathlib import Path

from agent_framework import Agent, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from character_agent.config import create_logger, get_settings
from character_agent.prompts import CHARACTER_PROMPT
from character_agent.tools import TOOLS

logger = create_logger(__name__)

AGENT_NAME = "character-agent"

SKILLS_DIR = Path(__file__).parent / "skills"


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


def create_agent(model: str | None = None) -> Agent:
    """ホステッドエージェントとして公開するエージェントを組み立てる。

    モデルは Foundry プロジェクトのエンドポイント経由で Entra 認証により呼び出す。
    モデル名は環境変数で切り替える前提のため、コードには持たせない（ADR-0001 モデル選定）。
    `model` は評価でモデルを差し替えるための引数で、通常は指定しない（`evals/run_eval.py`）。
    """
    logger.info("create_agent が呼び出されました")
    settings = get_settings()

    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=model or settings.model_deployment_name,
        credential=DefaultAzureCredential(),
    )
    # ツールが投げた例外の内容をモデルに返す。日付の指定ミスなどをモデル自身が直せるようにする。
    client.function_invocation_configuration["include_detailed_errors"] = True

    return Agent(
        client=client,
        name=AGENT_NAME,
        instructions=CHARACTER_PROMPT,
        tools=TOOLS,
        context_providers=[create_skills_provider()],
        # 会話履歴はホスティング基盤が管理するため、エージェント側では保存しない（ADR-0001 §3）。
        default_options={"store": False},
    )
