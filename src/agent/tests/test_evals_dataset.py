"""評価データセットがエージェントの実装と食い違っていないことを確認する。

実際の採点は Azure への接続が要るためテストしない。ここで見るのは、ツール名の打ち間違いや
ケースの重複といった、実行するまで気づけない壊れ方だけ。
"""

import inspect

from agent_framework import SkillsProvider

from character_agent import cosmos
from character_agent.agent import WEB_SEARCH_TOOL_NAME
from character_agent.tools import TOOLS
from evals.dataset import load_cases
from evals.fake_backend import fake_backend

# スキルの読み込みも評価対象のツール呼び出しに含める（日記登録はスキルの手順に従う前提のため）。
# Web 検索はエージェントに直接登録されず、Foundry Toolbox の MCP エンドポイントから来る。
KNOWN_TOOLS = {tool.name for tool in TOOLS} | {
    SkillsProvider.LOAD_SKILL_TOOL_NAME,
    SkillsProvider.READ_SKILL_RESOURCE_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
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


def test_dataset_covers_web_search():
    """最新情報を必要とするケースが抜けていないこと（Toolbox 経由の Web 検索を選べるかを見る）。"""
    cases = load_cases()

    assert any(WEB_SEARCH_TOOL_NAME in {tool.name for tool in case.expected_tools} for case in cases)


def test_dataset_has_cases_without_tool_calls():
    # ツールを使わずに答えるべきケース（雑談・話題転換・曖昧な依頼）が抜けていないこと。
    assert any(not case.expected_tools for case in load_cases())


FAKED_COSMOS_FUNCTIONS = (
    "read_user",
    "save_digest",
    "find_entry",
    "list_summaries",
    "create_entry",
    "update_entry",
    "move_entry",
    "delete_entry",
    "search_entries",
)


def test_fake_backend_matches_the_real_cosmos_signatures():
    """評価用の差し替えが本物の `cosmos` と同じ引数を取ること。

    差し替えは呼ばれるまでエラーにならないため、引数が食い違うと評価だけが静かに壊れる。
    """
    real = {name: inspect.signature(getattr(cosmos, name)) for name in FAKED_COSMOS_FUNCTIONS}

    with fake_backend():
        for name, signature in real.items():
            # 差し替えはバウンドメソッドなので self は現れない。そのまま比べられる。
            assert inspect.signature(getattr(cosmos, name)) == signature, f"{name} の引数が本物と食い違っている"
