"""エージェント定義が組み立てられることを確認する。

モデルは呼ばないため接続先はダミー値でよい（`FoundryChatClient` は生成時に通信しない）。
"""

import re

import pytest

from character_agent.agent import AGENT_NAME, create_agent, get_current_datetime
from character_agent.prompts import CHARACTER_PROMPT


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.services.ai.azure.com/api/projects/dummy")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "dummy-deployment")
    return create_agent()


def test_agent_uses_character_prompt(agent):
    assert agent.name == AGENT_NAME
    assert agent.default_options["instructions"] == CHARACTER_PROMPT


def test_agent_delegates_history_to_platform(agent):
    # 会話履歴はホスティング基盤が持つ（ADR-0001 §3）。
    assert agent.default_options["store"] is False


def test_agent_model_comes_from_environment(agent):
    assert agent.default_options["model"] == "dummy-deployment"


def test_agent_registers_datetime_tool(agent):
    assert [tool.name for tool in agent.default_options["tools"]] == ["get_current_datetime"]


def test_create_agent_requires_project_endpoint(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "dummy-deployment")
    with pytest.raises(KeyError):
        create_agent()


def test_get_current_datetime_returns_japan_time():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \([A-Za-z]{3}\)", get_current_datetime.func())
