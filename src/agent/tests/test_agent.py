"""エージェント定義が組み立てられることを確認する。

モデルは呼ばないため接続先はダミー値でよい（`FoundryChatClient` は生成時に通信しない）。
"""

import asyncio
import re

import pytest
from agent_framework import FileSkillsSource, SkillsProvider, SkillsSourceContext

from character_agent.agent import AGENT_NAME, SKILLS_DIR, create_agent
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
        "digest_regenerate",
    ]


def test_agent_registers_the_skills_provider(agent):
    assert any(isinstance(provider, SkillsProvider) for provider in agent.context_providers)


def test_every_skill_is_discoverable(agent):
    source = FileSkillsSource(str(SKILLS_DIR))

    skills = asyncio.run(source.get_skills(SkillsSourceContext(agent=agent)))

    assert sorted(skill.frontmatter.name for skill in skills) == ["diary-maintenance", "diary-writing"]


def test_create_agent_requires_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    get_settings.cache_clear()
    with pytest.raises(EnvironmentError):
        create_agent()


def test_get_current_datetime_returns_japan_time():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \([A-Za-z]{3}\)", get_current_datetime.func())
