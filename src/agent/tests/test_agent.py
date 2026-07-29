"""エージェント定義が組み立てられることを確認する。

モデルは呼ばないため接続先はダミー値でよい（`FoundryChatClient` は生成時に通信しない）。
"""

import asyncio
import re

import pytest
from agent_framework import FileSkillsSource, MCPStreamableHTTPTool, SkillsProvider, SkillsSourceContext
from azure.identity import DefaultAzureCredential

from character_agent.agent import AGENT_NAME, SKILLS_DIR, TOOLBOX_SCOPE, create_agent, toolbox_headers
from character_agent.config import get_settings
from character_agent.prompts import CHARACTER_PROMPT
from character_agent.tools import get_current_datetime


@pytest.fixture
def agent():
    return create_agent()


def test_agent_uses_character_prompt(agent):
    assert agent.name == AGENT_NAME
    assert agent.default_options["instructions"] == CHARACTER_PROMPT


def test_agent_delegates_history_to_platform(agent):
    # 会話履歴はホスティング基盤が持つ（ADR-0001 §3）。
    assert agent.default_options["store"] is False


def test_agent_model_comes_from_environment(agent):
    assert agent.default_options["model"] == "dummy-deployment"


def test_agent_registers_every_tool(agent):
    assert [tool.name for tool in agent.default_options["tools"]] == [
        "get_current_datetime",
        "read_profile",
        "diary_search",
        "diary_create",
        "diary_update",
        "diary_delete",
        "diary_rename",
        "digest_read",
        "digest_save",
    ]


def test_agent_reaches_web_search_through_the_toolbox(agent):
    """Web 検索は Toolbox の MCP エンドポイント越しに使う（ADR-0001 §2）。"""
    (toolbox,) = agent.mcp_tools

    assert isinstance(toolbox, MCPStreamableHTTPTool)
    assert toolbox.url == (
        "https://example.services.ai.azure.com/api/projects/dummy/toolboxes/dummy-toolbox/mcp?api-version=v1"
    )


def test_toolbox_requests_carry_an_entra_token(monkeypatch: pytest.MonkeyPatch):
    """Toolbox へのリクエストには毎回 Entra のトークンを載せる（キーは使わない）。"""
    scopes = []
    monkeypatch.setattr(
        "character_agent.agent.get_bearer_token_provider",
        lambda credential, scope: scopes.append(scope) or (lambda: "token-1"),
    )

    headers = toolbox_headers(DefaultAzureCredential())

    assert headers({}) == {"Authorization": "Bearer token-1"}
    assert scopes == [TOOLBOX_SCOPE]


def test_agent_registers_the_skills_provider(agent):
    assert any(isinstance(provider, SkillsProvider) for provider in agent.context_providers)


def test_every_skill_is_discoverable(agent):
    source = FileSkillsSource(str(SKILLS_DIR))

    skills = asyncio.run(source.get_skills(SkillsSourceContext(agent=agent)))

    assert sorted(skill.frontmatter.name for skill in skills) == ["diary-maintenance", "diary-writing", "digest-rollup"]


def test_create_agent_requires_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    get_settings.cache_clear()
    with pytest.raises(EnvironmentError):
        create_agent()


def test_get_current_datetime_returns_japan_time():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \([A-Za-z]{3}\)", get_current_datetime.func())
