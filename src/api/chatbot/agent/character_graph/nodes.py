"""Node definitions for character graph."""

import os
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from typing_extensions import TypedDict

from chatbot.agent.character_graph.prompts import (
    ROUTER_PROMPT,
    SISTER_EDINET_PROMPT,
    SISTER_EDINET_SHORT_DIARY_PROMPT,
    SISTER_EDINET_SHORT_PROMPT,
)
from chatbot.agent.character_graph.state import State
from chatbot.agent.tools import create_diary_drive_tool, diary_search_tool
from chatbot.utils import get_japan_datetime
from chatbot.utils.config import create_logger
from chatbot.utils.google_auth import GoogleDriveOAuthManager
from chatbot.utils.google_drive import GoogleDriveHandler

logger = create_logger(__name__)

# グローバル変数
_cached = {"profile": {}, "digest": {}}
_mcp_client = None


def get_cached() -> dict:
    """キャッシュされたデータを取得"""
    return _cached


def set_cached(cached: dict) -> None:
    """キャッシュを設定"""
    global _cached
    # 2キーがdictで存在するように補完
    for k in ("profile", "digest"):
        if k not in cached or not isinstance(cached[k], dict):
            cached[k] = {}
    _cached = cached


async def get_mcp_client():
    """MCPクライアントのシングルトンインスタンスを取得"""
    global _mcp_client
    if _mcp_client is None:
        # MCP serverの設定 (streamable HTTPを使用)
        connections = {
            "spotify": {
                "url": os.getenv("MCP_FUNCTION_URL", "http://localhost:7072/runtime/webhooks/mcp"),
                "transport": "streamable_http",
            }
        }
        _mcp_client = MultiServerMCPClient(connections)
    return _mcp_client


async def get_mcp_tools():
    """MCPツールを取得"""
    try:
        client = await get_mcp_client()
        tools = await client.get_tools()
        logger.info(f"Retrieved {len(tools)} MCP tools")
        return tools
    except Exception as e:
        logger.warning(f"Failed to retrieve MCP tools: {e}")
        return []


def _create_drive_handler(userid: str, user_repository):
    """ユーザのOAuth認証情報からGoogleDriveHandlerを生成する。取得できない場合はNoneを返す。"""
    auth_manager = GoogleDriveOAuthManager(user_repository)
    credentials = auth_manager.get_user_credentials(userid)
    if not credentials:
        logger.warning("Google Drive credentials not found for user: %s", userid)
        return None

    folder_id = user_repository.fetch_drive_folder_id(userid)
    if not folder_id:
        logger.warning("Google Drive folder ID not found for user: %s", userid)
        return None

    return GoogleDriveHandler(credentials=credentials, folder_id=folder_id)


def _get_cached_drive_content(userid: str, user_repository, cache_key: str, fetch_fn) -> str:
    """Google Drive からコンテンツを取得しキャッシュする汎用関数。"""
    global _cached
    if userid not in _cached[cache_key]:
        logger.info(f"Fetching {cache_key} from Google Drive as it is not cached: {userid}")
        drive_handler = _create_drive_handler(userid, user_repository)
        if not drive_handler:
            _cached[cache_key][userid] = ""
            return ""

        result = fetch_fn(drive_handler)
        if result and "content" in result:
            _cached[cache_key][userid] = result["content"]
        else:
            logger.error("Failed to get %s content, using empty value", cache_key)
            _cached[cache_key][userid] = ""
    return _cached[cache_key].get(userid, "")


def get_user_profile(userid: str, user_repository) -> str:
    """キャッシュされたユーザプロフィール情報を取得、なければGoogle Driveから取得"""
    from chatbot.utils.google_drive_utils import get_profile_from_drive

    return _get_cached_drive_content(userid, user_repository, "profile", get_profile_from_drive)


def get_user_digest(userid: str, user_repository) -> str:
    """キャッシュされたユーザダイジェスト情報を取得、なければGoogle Driveから取得"""
    from chatbot.utils.google_drive_utils import get_digest_from_drive

    return _get_cached_drive_content(userid, user_repository, "digest", get_digest_from_drive)


def router_node(state: State, config: RunnableConfig) -> Command[Literal["diary_agent", "chatbot", "spotify_agent"]]:
    """
    プロフィール/ダイジェストを取得し、次に遷移するノードを決定します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
        config (RunnableConfig): LangGraphのconfig。user_repositoryを含む。
    Returns:
        Command: 次に遷移するノード（profile/digest の state 更新を含む）。
    """
    logger.info("--- Router Node ---")

    user_repository = config["configurable"]["user_repository"]
    userid = state["userid"]
    profile = get_user_profile(userid, user_repository)
    digest = get_user_digest(userid, user_repository)

    class Router(TypedDict):
        """Worker to route to next. If no workers needed, route to FINISH."""

        next: Literal["spotify_agent", "diary_searcher", "FINISH"]

    llm = ChatOpenAI(temperature=0, model="gpt-5.2")

    agent = create_agent(
        llm,
        tools=[],
        system_prompt=ROUTER_PROMPT,
        response_format=ProviderStrategy(Router),
    )

    try:
        result = agent.invoke({"messages": state["messages"]})
        router_result = result.get("structured_response") or {}
        goto = router_result.get("next", "chatbot")
    except Exception as e:  # noqa: BLE001
        logger.error("Router agent failed: %s", e)
        goto = "chatbot"

    if goto == "FINISH":
        goto = "chatbot"
    elif goto == "diary_searcher":
        goto = "diary_agent"

    return Command(goto=goto, update={"profile": profile, "digest": digest})


async def chatbot_node(state: State) -> Command[Literal["__end__"]]:
    """
    ユーザーのメッセージに対して応答を生成します。必要に応じてWeb検索も実行します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Chatbot Node ---")

    # プロンプトに現在時刻・プロフィール・ダイジェストを埋め込む
    system_prompt = SISTER_EDINET_PROMPT.format(
        current_datetime=get_japan_datetime(),
        user_profile=state.get("profile", ""),
        user_digest=state.get("digest", ""),
    )

    llm = ChatOpenAI(model="gpt-5.2", temperature=1.0)
    # OpenAI built-in の web_search_preview ツールを利用
    tools = [{"type": "web_search_preview"}]

    agent = create_agent(
        llm,
        tools=tools,
        system_prompt=system_prompt,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=result["messages"][-1].text)]},
    )


async def spotify_agent_node(state: State) -> Command[Literal["__end__"]]:
    """
    Spotify関連のリクエストに対してMCPツールを使って応答を生成するノード。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Spotify Agent Node ---")

    llm = ChatOpenAI(model="gpt-5.2", temperature=0.5)
    # MCPツール取得
    mcp_tools = await get_mcp_tools()
    if not mcp_tools:
        logger.error("MCP tools unavailable. Skipping Spotify agent execution.")
        fallback_message = "ごめんね。MCP サーバーに接続できなかったみたい。"
        return Command(
            goto="__end__",
            update={"messages": [AIMessage(content=fallback_message)]},
        )

    agent = create_agent(
        llm,
        tools=mcp_tools,
        system_prompt=SISTER_EDINET_SHORT_PROMPT,
    )
    content = await agent.ainvoke({"messages": state["messages"]})
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content["messages"][-1].text)]},
    )


async def diary_agent_node(state: State, config: RunnableConfig) -> Command[Literal["__end__"]]:
    """
    日記検索関連のリクエストに対してdiary search toolを使って応答を生成するノード。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
        config (RunnableConfig): LangGraphのconfig。user_repositoryを含む。
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Diary Agent Node ---")

    # プロンプトに現在日時を埋め込む
    system_prompt = SISTER_EDINET_SHORT_DIARY_PROMPT.format(
        current_datetime=get_japan_datetime(),
    )

    llm = ChatOpenAI(model="gpt-5.2", temperature=0.5, reasoning_effort="medium")

    diary_tools = [diary_search_tool]

    user_repository = config["configurable"]["user_repository"]
    userid = state["userid"]
    drive_handler = _create_drive_handler(userid, user_repository)
    if drive_handler:
        diary_tools.append(create_diary_drive_tool(drive_handler))

    agent = create_agent(
        llm,
        tools=diary_tools,
        system_prompt=system_prompt,
    )
    content = await agent.ainvoke({"messages": state["messages"]})
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content["messages"][-1].text)]},
    )
