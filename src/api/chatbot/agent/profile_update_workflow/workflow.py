"""LangGraphベースのプロファイル更新ワークフロー定義。

日記の処理完了後、バックグラウンドで実行され、
ユーザープロファイル（profile.md）を更新する。
"""

import tempfile
from pathlib import Path
from typing import Literal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from langsmith import traceable
from typing_extensions import TypedDict

from chatbot.agent.character_graph.nodes import get_cached, set_cached
from chatbot.utils.config import create_logger
from chatbot.utils.google_drive import create_drive_handler

logger = create_logger(__name__)

# Deep Agent 用システムプロンプト
PROFILE_UPDATE_SYSTEM_PROMPT = """
あなたはユーザープロファイル更新担当のエージェントです。
ユーザーの日記を分析し、profile.mdに記録すべき情報があれば反映します。

対象ファイル: /profile.md

## 記録すべき情報の例:
- 趣味・興味関心
- 仕事・職業に関する情報
- 人間関係（家族、友人、ペットなど）
- 好きなもの・嫌いなもの
- 将来の目標・夢
- 重要なライフイベント
- 住んでいる場所・よく行く場所
- 健康状態や習慣

## 更新の方針:
- 新しい情報の追記
- 既存情報の修正・置換（より正確な情報がある場合）
- 不要・誤った情報の削除
- Markdown構造は多少崩れても問題なし（読めればOK）
- 箇条書きや見出しを適宜使用して読みやすく整理する
- 記録すべき情報がなければ、何も変更しない

## 最終成果物の要件:
- 有効なMarkdownであること
- ユーザーにとって読みやすい形式であること
"""


class ProfileUpdateState(TypedDict):
    """プロファイル更新ワークフローの状態。"""

    userid: str
    session_id: str
    diary_text: str | None
    profile_content: str | None
    updated_profile: str | None


def _invalidate_profile_cache(userid: str) -> None:
    """プロファイルのキャッシュを無効化する。"""
    cached = get_cached()
    if userid in cached.get("profile", {}):
        del cached["profile"][userid]
        set_cached(cached)
        logger.info(f"Invalidated profile cache for user: {userid}")


def get_profile_update_workflow():
    """プロファイル更新用の LangGraph ワークフローを構築して返す。"""
    graph_builder = StateGraph(ProfileUpdateState)

    @traceable(run_type="chain", name="Load Profile")
    def load_profile_node(state: ProfileUpdateState) -> Command[Literal["update_profile_node", "__end__"]]:
        """Google Drive から現在の profile.md を読み込む。"""
        logger.info("--- Profile Update: load_profile ---")
        if not state.get("diary_text"):
            logger.info("No diary text provided, skipping profile update")
            return Command(goto=END)

        drive_handler = create_drive_handler(state["userid"])
        if not drive_handler:
            logger.warning("Google Drive handler not available, skipping profile update")
            return Command(goto=END)

        profile_content = drive_handler.get_profile_md()
        return Command(goto="update_profile_node", update={"profile_content": profile_content})

    @traceable(run_type="chain", name="Update Profile")
    def update_profile_node(state: ProfileUpdateState) -> Command[Literal["save_profile_node", "__end__"]]:
        """Deep Agent を使用して日記から情報を抽出し profile.md を更新する。"""
        logger.info("--- Profile Update: update_profile ---")
        profile_content = state.get("profile_content") or ""
        diary_text = state["diary_text"]

        with tempfile.TemporaryDirectory() as workspace:
            profile_path = Path(workspace) / "profile.md"
            profile_path.write_text(profile_content, encoding="utf-8")

            backend = FilesystemBackend(root_dir=Path(workspace), virtual_mode=True)
            llm = ChatOpenAI(model="gpt-5.2", temperature=0, reasoning_effort="medium")
            agent = create_deep_agent(model=llm, system_prompt=PROFILE_UPDATE_SYSTEM_PROMPT, backend=backend)

            user_prompt = f"""
以下の日記を分析し、profile.mdに記録すべき情報があれば反映してください。
記録すべき情報がなければ、何も変更しないでください。

## 本日の日記:
{diary_text}
"""
            agent.invoke({"messages": [("user", user_prompt)]})

            updated_profile = profile_path.read_text(encoding="utf-8")

        # プロファイルに変更がなければ保存をスキップ
        if updated_profile == profile_content:
            logger.info("No changes to profile, skipping save")
            return Command(goto=END)

        logger.info("Profile updated by Deep Agent")
        return Command(goto="save_profile_node", update={"updated_profile": updated_profile})

    @traceable(run_type="tool", name="Save Profile")
    def save_profile_node(state: ProfileUpdateState) -> Command[Literal["__end__"]]:
        """更新された profile.md を Google Drive に保存する。"""
        logger.info("--- Profile Update: save_profile ---")
        updated_profile = state.get("updated_profile")

        if not updated_profile:
            logger.warning("No updated profile to save")
            return Command(goto=END)

        drive_handler = create_drive_handler(state["userid"])
        if not drive_handler:
            logger.error("Failed to create drive handler for saving profile")
            return Command(goto=END)

        file_id = drive_handler.update_profile_md(updated_profile)
        if file_id:
            logger.info(f"Profile saved to Google Drive: {file_id}")
            # キャッシュを無効化
            _invalidate_profile_cache(state["userid"])
        else:
            logger.error("Failed to save profile to Google Drive")

        return Command(goto=END)

    graph_builder.add_node("load_profile_node", load_profile_node)
    graph_builder.add_node("update_profile_node", update_profile_node)
    graph_builder.add_node("save_profile_node", save_profile_node)

    graph_builder.add_edge(START, "load_profile_node")

    return graph_builder.compile()


async def run_profile_update_workflow(userid: str, session_id: str, diary_text: str | None) -> None:
    """プロファイル更新ワークフローを実行する。

    バックグラウンドタスクとして呼び出されることを想定。

    Args:
        userid: ユーザーID
        session_id: セッションID
        diary_text: 日記のテキスト
    """
    if not diary_text:
        logger.info("No diary text provided, skipping profile update workflow")
        return

    try:
        logger.info(f"Starting profile update workflow for user: {userid}")
        workflow = get_profile_update_workflow()
        await workflow.ainvoke(
            {"userid": userid, "session_id": session_id, "diary_text": diary_text},
            {"configurable": {"thread_id": f"profile-update-{session_id}"}},
        )
        logger.info(f"Profile update workflow completed for user: {userid}")
    except Exception as e:
        # バックグラウンド処理のため、エラーはログに記録するのみ
        logger.exception(f"Profile update workflow failed for user {userid}: {e}")
