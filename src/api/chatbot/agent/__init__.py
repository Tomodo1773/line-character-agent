import os
import sys
from operator import add
from typing import Annotated, Literal

from langchain import hub
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langsmith import traceable
from typing_extensions import TypedDict

from chatbot.agent.tools import azure_ai_search, google_search
from chatbot.database.repositories import UserRepository
from chatbot.utils import get_japan_datetime, messages_to_dict, remove_trailing_newline
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
    documents: Annotated[list, add] = []
    query: str = ""
    profile: dict = {}


# グローバル変数
_cached = {"profile": {}, "prompts": {}}


@traceable(run_type="prompt", name="Get Prompt")
def get_prompt(path: str):
    """キャッシュされたプロンプトを取得、なければhubから取得"""
    global _cached
    if path not in _cached["prompts"]:
        logger.info(f"Fetching prompt from hub as it is not cached: {path}")
        _cached["prompts"][path] = hub.pull(path)
    return _cached["prompts"][path]


def get_user_profile(userid: str) -> dict:
    """キャッシュされたユーザプロフィール情報を取得、なければGoogle Driveから取得"""
    global _cached
    if userid not in _cached["profile"]:
        logger.info(f"Fetching user profile from Google Drive as it is not cached: {userid}")
        from chatbot.utils.google_drive_utils import get_profile_from_drive, get_digest_from_drive
        
        user_profile = get_profile_from_drive()
        if user_profile and "content" in user_profile:
            _cached["profile"][userid] = user_profile["content"]
        else:
            logger.error("Failed to get profile content, using empty profile")
            _cached["profile"][userid] = ""
            
        if "digest" not in _cached:
            _cached["digest"] = {}
        
        digest = get_digest_from_drive()
        if digest and "content" in digest:
            _cached["digest"][userid] = digest["content"]
        else:
            logger.error("Failed to get digest content, using empty digest")
            _cached["digest"][userid] = ""
            
    return {
        "content": _cached["profile"][userid],
        "digest": _cached["digest"].get(userid, "")
    }


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
    return Command(goto="router", update={"profile": get_user_profile(state["userid"])})


def router_node(state: State) -> Command[Literal["create_web_query", "create_diary_query", "url_fetcher", "chatbot"]]:
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

        next: Literal["web_searcher", "diary_searcher", "url_fetcher", "FINISH"]

    # llm = ChatAnthropic(model="claude-3-5-sonnet-latest")
    llm = ChatOpenAI(temperature=0, model="gpt-4o")
    structured_llm = llm.with_structured_output(Router)
    chain = prompt | structured_llm
    response = chain.invoke({"messages": state["messages"]})
    goto = response["next"]
    if goto == "FINISH":
        goto = "chatbot"
    elif goto == "web_searcher":
        goto = "create_web_query"
    elif goto == "diary_searcher":
        goto = "create_diary_query"

    return Command(goto=goto)


def chatbot_node(state: State) -> Command[Literal["__end__"]]:
    """
    ユーザーのメッセージに対して応答を生成します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Chatbot Node ---")

    # 検索結果があるときは詳細に、それ以外は簡潔に回答する
    if state["documents"] and any("web_contents" in doc for doc in state["documents"]):
        instruction = "ユーザからの質問に詳しく返答してください。"
    else:
        instruction = "ユーザと1～3文の返答でテンポよく雑談してください。"
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=1.0)
    # llm = ChatAnthropic(model="claude-3-5-sonnet-latest")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/sister_edinet
    template = get_prompt("tomodo1773/sister_edinet")
    prompt = template.partial(current_datetime=get_japan_datetime(), user_profile=state["profile"], instruction=instruction)

    chatbot_chain = prompt | llm | StrOutputParser() | remove_trailing_newline
    content = chatbot_chain.invoke({"messages": state["messages"], "documents": state["documents"]})
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content)]},
    )


def create_web_query_node(state: State) -> Command[Literal["web_searcher"]]:
    """
    ウェブ検索用のクエリを生成します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: web_searcherノードへの遷移＆作成したクエリ
    """
    logger.info("--- Create Web Query Node ---")
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/create_web_search_query
    template = get_prompt("tomodo1773/create_web_search_query")
    prompt = template.partial(current_datetime=get_japan_datetime(), user_profile=state["profile"])
    create_web_query_chain = prompt | llm | StrOutputParser()

    created_query = create_web_query_chain.invoke({"messages": messages_to_dict(state["messages"])})
    return Command(
        goto="web_searcher",
        update={"query": created_query},
    )


def web_searcher_node(state: State) -> Command[Literal["chatbot"]]:
    """
    生成されたクエリを使用してウェブ検索を実行します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: chatbotノードへの遷移＆検索結果
    """
    logger.info("--- Web Searcher Node ---")
    return Command(
        goto="chatbot",
        update={"documents": google_search(state["query"])},
    )


def create_diary_query_node(state: State) -> Command[Literal["diary_searcher"]]:
    """
    日記検索用のクエリを生成します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: diary_searcherノードへの遷移＆作成したクエリ
    """
    logger.info("--- Create Diary Query Node ---")
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/create_diary_search_query
    template = get_prompt("tomodo1773/create_diary_search_query")
    prompt = template.partial(current_datetime=get_japan_datetime())
    create_diary_query_chain = prompt | llm | StrOutputParser()
    return Command(
        goto="diary_searcher",
        update={"query": create_diary_query_chain.invoke({"messages": messages_to_dict(state["messages"])})},
    )


def diary_searcher_node(state: State) -> Command[Literal["chatbot"]]:
    """
    生成されたクエリを使用して日記検索を実行します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: chatbotノードへの遷移＆検索結果
    """
    logger.info("--- Diary Searcher Node ---")
    return Command(
        goto="chatbot",
        update={"documents": azure_ai_search(state["query"])},
    )


def url_fetcher_node(state: State) -> Command[Literal["chatbot"]]:
    """
    URLから情報を取得します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: chatbotノードへの遷移（主要機能は未実装）
    """
    logger.info("--- URL Fetcher Node ---")
    return Command(
        goto="chatbot",
        update={"documents": []},
    )


class ChatbotAgent:
    def __init__(self, cached: dict = None) -> None:
        """Initialize agent with cached prompts"""
        global _cached
        if cached:
            _cached = cached

        graph_builder = StateGraph(State)
        graph_builder.add_edge(START, "get_user_profile")
        graph_builder.add_node("get_user_profile", get_user_profile_node)
        graph_builder.add_node("router", router_node)
        graph_builder.add_node("chatbot", chatbot_node)
        graph_builder.add_node("create_web_query", create_web_query_node)
        graph_builder.add_node("web_searcher", web_searcher_node)
        graph_builder.add_node("url_fetcher", url_fetcher_node)
        graph_builder.add_node("create_diary_query", create_diary_query_node)
        graph_builder.add_node("diary_searcher", diary_searcher_node)
        self.graph = graph_builder.compile()

    def invoke(self, messages: list, userid: str):
        recursion_limit = 8
        return self.graph.invoke({"messages": messages, "userid": userid}, {"recursion_limit": recursion_limit})

    async def ainvoke(self, messages: list, userid: str):
        recursion_limit = 8
        return await self.graph.ainvoke({"messages": messages, "userid": userid}, {"recursion_limit": recursion_limit})

    async def astream(self, messages: list, userid: str):
        recursion_limit = 8
        async for msg, metadata in self.graph.astream(
            {"messages": messages, "userid": userid},
            {"recursion_limit": recursion_limit},
            stream_mode="messages",
            # stream_mode=["messages", "values"],
        ):
            yield msg, metadata

    async def astream_events(self, messages: list, userid: str):
        recursion_limit = 8
        async for event in self.graph.astream_events(
            {"messages": messages, "userid": userid},
            {"recursion_limit": recursion_limit},
            version="v1",
        ):
            yield event

    def create_image(self):
        graph_image = self.graph.get_graph(xray=True).draw_mermaid_png()
        with open("agent_graph.png", "wb") as f:
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
            async for msg, metadata in agent_graph.astream(messages=history, userid=userid):
                # print(f"msg: {msg}")
                # print(f"metadata: {metadata}")
                if msg.content and not isinstance(msg, HumanMessage):
                    print(msg.content, end="", flush=True)

            # astream_events
            # async for msg in agent_graph.astream_events(messages=history, userid=userid):
            # print(f"event: {msg}")

            # print(event)
            # for value in event.values():
            #     if value and "messages" in value:
            #         print("Assistant:", value["messages"][-1].content)
            # history.append({"type": "assistant", "content": value["messages"][-1].content})

    asyncio.run(main())
    asyncio.run(main())
