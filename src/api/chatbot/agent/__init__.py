import datetime
import getpass
import os
from operator import add
from typing import Annotated, Literal

import pytz
from chatbot.agent.tools import azure_ai_search, google_search
from chatbot.database import UsersCosmosDB
from langchain import hub
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from typing_extensions import TypedDict

# ############################################
# 事前準備
# ############################################


def _set_if_undefined(var: str) -> None:
    # 環境変数が未設定の場合、ユーザーに入力を促す
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"Please provide your {var}")


# 必要な環境変数を設定
_set_if_undefined("OPENAI_API_KEY")
_set_if_undefined("LANGCHAIN_API_KEY")
_set_if_undefined("GOOGLE_API_KEY")

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

def get_user_profile_node(state: State) -> Command[Literal["router"]]:
    print("--- Get User Profile Node ---")
    cosmos = UsersCosmosDB()
    result = cosmos.fetch_profile(state["userid"])
    # プロファイルデータを整形
    if isinstance(result, list) and result:
        user_profile = result[0].get("profile", {})

    return Command(
        goto="router",
        update={"profile": user_profile})

def router_node(state: State) -> Command[Literal["create_web_query", "create_diary_query", "url_fetcher", "chatbot"]]:
    """
    Determines the next node to transition to based on the current state.
    Args:
        state (State): The current state containing messages.
    Returns:
        Command: A command indicating the next node to transition to.
    """
    print("--- Router Node ---")
    members = ["web_searcher", "diary_searcher", "url_fetcher"]
    system_prompt = (
        "You are a router tasked with managing a conversation between the"
        f" following workers: {members}. Given the following user request,"
        " respond with the worker to act next. Each worker will perform a"
        " task and respond with their results and status. When finished,"
        " respond with FINISH."
    )
    class Router(TypedDict):
        """Worker to route to next. If no workers needed, route to FINISH."""
        next: Literal["web_searcher", "diary_searcher", "url_fetcher", "FINISH"]

    # llm = ChatAnthropic(model="claude-3-5-sonnet-latest")
    llm = ChatOpenAI(temperature=0, model="gpt-4o")
    messages = [
        {"role": "system", "content": system_prompt},
    ] + state["messages"]
    response = llm.with_structured_output(Router).invoke(messages)
    goto = response["next"]
    if goto == "FINISH":
        goto = "chatbot"
    elif goto == "web_searcher":
        goto = "create_web_query"
    elif goto == "diary_searcher":
        goto = "create_diary_query"

    return Command(goto=goto)
    

def remove_trailing_newline(text: str) -> str:
    """
    入力されたテキストの最後の改行を削除する関数

    :param text: 入力テキスト
    :return: 最後の改行が削除されたテキスト
    """
    return text.rstrip("\n")

def chatbot_node(state: State) -> Command[Literal["__end__"]]:
    print("--- Chatbot Node ---")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=1.0)
    # llm = ChatAnthropic(model="claude-3-5-sonnet-latest")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/sister_edinet
    template = hub.pull("tomodo1773/sister_edinet")
    current_datetime = datetime.datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
    prompt = template.partial(current_datetime=current_datetime,user_profile=state["profile"])

    chatbot_chain = prompt | llm | StrOutputParser() | remove_trailing_newline
    content = chatbot_chain.invoke({"messages": state["messages"], "documents": state["documents"]})
    return Command(
        goto= "__end__",
        update={"messages": [AIMessage(content=content)]},
    )

def create_web_query_node(state: State) -> Command[Literal["web_searcher"]]:
    print("--- Create Web Query Node ---")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/create_web_search_query
    template = hub.pull("tomodo1773/create_web_search_query")
    current_datetime = datetime.datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
    prompt = template.partial(current_datetime=current_datetime)
    create_web_query_chain = prompt | llm | StrOutputParser()
    created_query = create_web_query_chain.invoke({"messages": state["messages"]})
    return Command(
        goto="web_searcher",
        update={"query": created_query},
    )

def web_searcher_node(state: State) -> Command[Literal["chatbot"]]:
    print("--- Web Searcher Node ---")
    return Command(
    goto="chatbot",
    update={"documents": google_search(state["query"])},
)

def create_diary_query_node(state: State) -> Command[Literal["diary_searcher"]]:
    print("--- Create Diary Query Node ---")
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/create_diary_search_query
    template = hub.pull("tomodo1773/create_diary_search_query")
    current_datetime = datetime.datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
    prompt = template.partial(current_datetime=current_datetime)
    create_diary_query_chain = prompt | llm | StrOutputParser()
    return Command(
        goto="diary_searcher",
        update={"query": create_diary_query_chain.invoke({"messages": state["messages"]})},
    )

def diary_searcher_node(state: State) -> Command[Literal["chatbot"]]:
    print("--- Diary Searcher Node ---")
    return Command(
    goto="chatbot",
    update={"documents": azure_ai_search(state["query"])},
)

def url_fetcher_node(state: State) -> Command[Literal["chatbot"]]:
    print("--- URL Fetcher Node ---")
    return Command(
    goto="chatbot",
    update={"documents": []},
)

class ChatbotAgent:

    def __init__(self) -> None:

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

    def stream(self, messages: list, userid: str):
        recursion_limit = 8
        events = self.graph.stream({"messages": messages, "userid": userid}, {"recursion_limit": recursion_limit})

        for event in events:
            yield event

    def create_image(self):
        graph_image = self.graph.get_graph(xray=True).draw_mermaid_png()
        with open("agent_graph.png", "wb") as f:
            f.write(graph_image)


if __name__ == "__main__":

    userid = os.environ.get("LINE_USER_ID")

    agent_graph = ChatbotAgent()

    agent_graph.create_image()
    history = []

    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        history.append({"type": "human", "content": user_input})
        for event in agent_graph.stream(messages=history, userid=userid):
            for value in event.values():
                if value and "messages" in value:
                    print("Assistant:", value["messages"][-1].content)
                    history.append({"type": "assistant", "content": value["messages"][-1].content})
