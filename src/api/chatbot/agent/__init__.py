import datetime
import getpass
import os
from typing import Annotated

import pytz
from chatbot.agent.tools import firecrawl_search
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict
from chatbot.agent.prompt import get_character_prompt

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
_set_if_undefined("TAVILY_API_KEY")

# Optional, add tracing in LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "LINE-AI-BOT"


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


class ChatbotAgent:

    def __init__(self) -> None:

        self.tools = [TavilySearchResults(max_results=3), firecrawl_search]
        graph_builder = StateGraph(State)
        graph_builder.add_node("chatbot", self._chatbot_node)
        graph_builder.add_node("tools", self._tool_node)
        graph_builder.add_conditional_edges(
            "chatbot",
            tools_condition,
        )
        graph_builder.add_edge("tools", "chatbot")
        graph_builder.set_entry_point("chatbot")
        self.graph = graph_builder.compile()

    def _chatbot_node(self, state: State):
        llm = ChatOpenAI(model="gpt-4o")
        llm_with_tools = llm.bind_tools(self.tools)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", get_character_prompt()),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        chatbot_chain = prompt | llm_with_tools
        return {"messages": [chatbot_chain.invoke(state)]}

    def _tool_node(self, state: State):
        return ToolNode(tools=self.tools)

    def invoke(self, messages: list):
        recursion_limit = 5
        return self.graph.invoke({"messages": messages}, {"recursion_limit": recursion_limit})

    def stream(self, messages: list):
        recursion_limit = 5
        events = self.graph.stream({"messages": messages}, {"recursion_limit": recursion_limit}, stream_mode="values")

        for event in events:
            if "messages" in event:
                yield event["messages"][-1].content

    def create_image(self):
        graph_image = self.graph.get_graph(xray=True).draw_mermaid_png()
        with open("quick_start.png", "wb") as f:
            f.write(graph_image)


if __name__ == "__main__":
    history = [
        ("user", "こんばんは、わたしはともどです。"),
        ("assistant", "こんにちは！ともど！悩みがあるなら、話してみてちょうだい"),
    ]

    agent_graph = ChatbotAgent()

    # agent_graph.create_image()

    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        # response = agent_graph.invoke(user_input, history)
        # print(response["messages"][-1].content)
        history.append({"type": "human", "content": user_input})
        response = agent_graph.stream(history)
        for chunk in response:
            print(chunk)
