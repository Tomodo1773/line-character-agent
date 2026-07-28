"""評価データセットがエージェントの実装と食い違っていないことを確認する。

実際の採点は Azure への接続が要るためテストしない。ここで見るのは、ツール名の打ち間違いや
ケースの重複といった、実行するまで気づけない壊れ方だけ。
"""

from agent_framework import SkillsProvider

from character_agent.tools import TOOLS
from evals.dataset import load_cases

# スキルの読み込みも評価対象のツール呼び出しに含める（日記登録はスキルの手順に従う前提のため）。
KNOWN_TOOLS = {tool.name for tool in TOOLS} | {
    SkillsProvider.LOAD_SKILL_TOOL_NAME,
    SkillsProvider.READ_SKILL_RESOURCE_TOOL_NAME,
}


def test_dataset_covers_around_ten_cases():
    cases = load_cases()

    assert 8 <= len(cases) <= 12
    assert len({case.id for case in cases}) == len(cases)


def test_every_case_has_turns_and_known_tools():
    for case in load_cases():
        assert case.turns, f"{case.id}: 発話が空"
        assert case.description, f"{case.id}: 説明が空"
        for expected in case.expected_tools:
            assert expected.name in KNOWN_TOOLS, f"{case.id}: 未知のツール {expected.name}"


def test_dataset_has_cases_without_tool_calls():
    # ツールを使わずに答えるべきケース（雑談・話題転換・曖昧な依頼）が抜けていないこと。
    assert any(not case.expected_tools for case in load_cases())
