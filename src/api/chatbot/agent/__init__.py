import os
import sys
from typing import Annotated, Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langsmith import Client, traceable
from typing_extensions import TypedDict

from chatbot.agent.tools import diary_search_tool
from chatbot.utils import get_japan_datetime, remove_trailing_newline
from chatbot.utils.config import check_environment_variables, create_logger

logger = create_logger(__name__)

# ############################################
# 事前準備
# ############################################

# Optional, add tracing in LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "LINE-AI-BOT"


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]
    userid: str
    profile: dict = {}
    digest: dict = {}


# グローバル変数
_cached = {"profile": {}, "prompts": {}, "digest": {}}
_mcp_client = None
_langsmith_client: Client | None = None


def get_langsmith_client() -> Client:
    """LangSmithクライアントのシングルトンインスタンスを取得"""
    global _langsmith_client
    if _langsmith_client is None:
        _langsmith_client = Client()
    return _langsmith_client


async def get_mcp_client():
    """MCPクライアントのシングルトンインスタンスを取得"""
    global _mcp_client
    if _mcp_client is None:
        # MCP serverの設定
        connections = {"spotify": {"url": os.getenv("MCP_FUNCTION_URL", "http://localhost:7000/mcp"), "transport": "sse"}}
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


@traceable(run_type="prompt", name="Get Prompt")
def get_prompt(path: str):
    """キャッシュされたプロンプトを取得、なければLangSmithから取得"""
    global _cached
    if path not in _cached["prompts"]:
        logger.info(f"Fetching prompt from LangSmith as it is not cached: {path}")
        try:
            client = get_langsmith_client()
            _cached["prompts"][path] = client.pull_prompt(path)
        except Exception as exc:
            logger.error(f"Failed to fetch prompt from LangSmith: {exc}")
            raise
    return _cached["prompts"][path]


def get_user_profile(userid: str) -> dict:
    """キャッシュされたユーザプロフィール情報を取得、なければGoogle Driveから取得"""
    global _cached
    if userid not in _cached["profile"]:
        logger.info(f"Fetching user profile from Google Drive as it is not cached: {userid}")
        from chatbot.utils.google_auth import GoogleDriveOAuthManager
        from chatbot.utils.google_drive import GoogleDriveHandler
        from chatbot.utils.google_drive_utils import get_digest_from_drive, get_profile_from_drive

        auth_manager = GoogleDriveOAuthManager()
        credentials = auth_manager.get_user_credentials(userid)

        if not credentials:
            logger.warning("Google Drive credentials not found for user: %s", userid)
            _cached["profile"][userid] = ""
            _cached["digest"][userid] = ""
            return {"profile": "", "digest": ""}

        drive_handler = GoogleDriveHandler(credentials=credentials)
        user_profile = get_profile_from_drive(drive_handler)
        if user_profile and "content" in user_profile:
            _cached["profile"][userid] = user_profile["content"]
        else:
            logger.error("Failed to get profile content, using empty profile")
            _cached["profile"][userid] = ""

        digest = get_digest_from_drive(drive_handler)
        if digest and "content" in digest:
            _cached["digest"][userid] = digest["content"]
        else:
            logger.error("Failed to get digest content, using empty digest")
            _cached["digest"][userid] = ""
    return {"profile": _cached["profile"].get(userid, ""), "digest": _cached["digest"].get(userid, "")}


@traceable(run_type="tool", name="Get User Profile")
def get_user_profile_node(state: State) -> Command[Literal["router"]]:
    """
    ユーザーのプロフィール情報を取得します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）。
    Returns:
        Command: routerノードへの遷移＆ユーザプロフィール情報
    """
    logger.info("--- Get User Profile Node ---")
    user_info = get_user_profile(state["userid"])
    return Command(goto="router", update={"profile": user_info["profile"], "digest": user_info["digest"]})


def router_node(state: State) -> Command[Literal["diary_agent", "chatbot", "spotify_agent"]]:
    """
    現在の状態に基づいて次に遷移するノードを決定します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: 次に遷移するノード。
    """
    logger.info("--- Router Node ---")
    prompt = get_prompt("tomodo1773/character-agent-router")

    class Router(TypedDict):
        """Worker to route to next. If no workers needed, route to FINISH."""

        next: Literal["spotify_agent", "diary_searcher", "FINISH"]

    llm = ChatOpenAI(temperature=0, model="gpt-5.1")
    structured_llm = llm.with_structured_output(Router)
    chain = prompt | structured_llm
    response = chain.invoke({"messages": state["messages"]})
    goto = response["next"]
    if goto == "FINISH":
        goto = "chatbot"
    elif goto == "diary_searcher":
        goto = "diary_agent"

    return Command(goto=goto)


async def chatbot_node(state: State) -> Command[Literal["__end__"]]:
    """
    ユーザーのメッセージに対して応答を生成します。必要に応じてWeb検索も実行します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Chatbot Node ---")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/sister_edinet
    template = get_prompt("tomodo1773/sister_edinet")

    prompt = template.partial(
        current_datetime=get_japan_datetime(),
        user_profile=state["profile"],
        user_digest=state["digest"],
    )

    llm = ChatOpenAI(model="gpt-5.1", temperature=1.0)
    llm_with_tools = llm.bind_tools([{"type": "web_search_preview"}])

    chatbot_chain = prompt | llm_with_tools | StrOutputParser() | remove_trailing_newline
    content = await chatbot_chain.ainvoke({"messages": state["messages"]})

    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content)]},
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
    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/sister_edinet_short
    prompt = get_prompt("tomodo1773/sister_edinet_short")

    llm = ChatOpenAI(model="gpt-5.1", temperature=0.5)
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
        prompt=prompt,
    )
    content = await agent.ainvoke({"messages": state["messages"]})
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content["messages"][-1].content)]},
    )


async def diary_agent_node(state: State) -> Command[Literal["__end__"]]:
    """
    日記検索関連のリクエストに対してdiary search toolを使って応答を生成するノード。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Diary Agent Node ---")
    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/sister_edinet_short_diary
    prompt = get_prompt("tomodo1773/sister_edinet_short_diary")

    # current_datetimeをpartialで事前に設定
    if "current_datetime" in prompt.input_variables:
        prompt = prompt.partial(current_datetime=get_japan_datetime())

    llm = ChatOpenAI(model="gpt-5.1", temperature=0.5)
    # 日記検索ツールを使用
    diary_tools = [diary_search_tool]
    agent = create_agent(
        llm,
        tools=diary_tools,
        prompt=prompt,
    )
    content = await agent.ainvoke({"messages": state["messages"]})
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content["messages"][-1].content)]},
    )


class ChatbotAgent:
    RECURSION_LIMIT = 20

    def __init__(self, cached: dict = None) -> None:
        """Initialize agent with cached prompts"""
        global _cached
        if cached:
            # 3キーがdictで存在するように補完
            for k in ("profile", "prompts", "digest"):
                if k not in cached or not isinstance(cached[k], dict):
                    cached[k] = {}
            _cached = cached

        graph_builder = StateGraph(State)
        graph_builder.add_edge(START, "get_user_profile")
        graph_builder.add_node("get_user_profile", get_user_profile_node)
        graph_builder.add_node("router", router_node)
        graph_builder.add_node("chatbot", chatbot_node)
        graph_builder.add_node("spotify_agent", spotify_agent_node)
        graph_builder.add_node("diary_agent", diary_agent_node)
        self.graph = graph_builder.compile()

    async def ainvoke(self, messages: list, userid: str):
        return await self.graph.ainvoke({"messages": messages, "userid": userid}, {"recursion_limit": self.RECURSION_LIMIT})

    async def astream(self, messages: list, userid: str):
        async for msg, metadata in self.graph.astream(
            {"messages": messages, "userid": userid},
            {"recursion_limit": self.RECURSION_LIMIT},
            stream_mode="messages",
            # stream_mode=["messages", "values"],
        ):
            yield msg, metadata

    async def astream_updates(self, messages: list, userid: str):
        async for msg in self.graph.astream(
            {"messages": messages, "userid": userid},
            {"recursion_limit": self.RECURSION_LIMIT},
            stream_mode="updates",
        ):
            yield msg

    def create_image(self):
        # imagesフォルダがなければ作成
        images_dir = "images"
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)

        graph_image = self.graph.get_graph(xray=True).draw_mermaid_png()
        # imagesフォルダに保存
        with open(os.path.join(images_dir, "agent_graph.png"), "wb") as f:
            f.write(graph_image)


if __name__ == "__main__":
    # 環境変数のチェック
    is_valid, missing_vars = check_environment_variables()
    if not is_valid:
        logger.error("必要な環境変数が設定されていません。アプリケーションを終了します。")
        logger.error(f"未設定の環境変数: {', '.join(missing_vars)}")
        sys.exit(1)

    userid = os.environ.get("LINE_USER_ID")

    agent_graph = ChatbotAgent()

    agent_graph.create_image()
    history = []

    # invoke
    # while True:
    #     user_input = input("User: ")
    #     if user_input.lower() in ["quit", "exit", "q"]:
    #         print("Goodbye!")
    #         break
    #     history.append({"type": "human", "content": user_input})

    #     response = agent_graph.invoke(messages=history, userid=userid)
    #     print("Assistant:", response)

    import asyncio

    async def main():
        while True:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            history.append({"type": "human", "content": user_input})

            # ainvoke
            # response = await agent_graph.ainvoke(messages=history, userid=userid)
            # print("Assistant:", response)
            # print("Assistant:", response["messages"][-1].content)

            # astream(stream_mode=["messages"])
            # async for msg in agent_graph.astream(messages=history, userid=userid, stream_mode="updates"):
            # print(f"msg: {msg}")
            # print("\n")
            # print(f"metadata: {metadata}")
            # if msg.content and not isinstance(msg, HumanMessage):
            # print(msg.content, end="", flush=True)

            # astream_updates
            async for msg in agent_graph.astream_updates(messages=history, userid=userid):
                print(f"msg: {msg}")
                print("\n")

            # print(event)
            # for value in event.values():
            #     if value and "messages" in value:
            #         print("Assistant:", value["messages"][-1].content)
            # history.append({"type": "assistant", "content": value["messages"][-1].content})

    asyncio.run(main())
