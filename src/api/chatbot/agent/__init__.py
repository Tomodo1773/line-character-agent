import datetime
import getpass
import os
from typing import Annotated, Literal

import pytz
from chatbot.agent.prompt import get_character_prompt
from chatbot.agent.tools import azure_ai_search, firecrawl_search
from langchain_anthropic import ChatAnthropic
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langchain_core.prompts import PromptTemplate


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

    def __init__(self, userid: str) -> None:

        self.tools = [TavilySearchResults(max_results=3), firecrawl_search, azure_ai_search]
        self.userid = userid
        graph_builder = StateGraph(State)
        graph_builder.add_node("supervisor", self._supervisor_node)
        graph_builder.add_node("chatbot", self._chatbot_node)
        graph_builder.add_node("tools", self._tool_node)
        graph_builder.add_conditional_edges(
            "chatbot",
            tools_condition,
        )
        graph_builder.add_edge("tools", "chatbot")
        graph_builder.add_edge(START, "supervisor")
        self.graph = graph_builder.compile()

    def _supervisor_node(self, state: State) -> Command[Literal["agent_1", "agent_2", "__end__"]]:
        # you can pass relevant parts of the state to the LLM (e.g., state["messages"])
        # to determine which agent to call next. a common pattern is to call the model
        # with a structured output (e.g. force it to return an output with a "next_agent" field)
        # response = model.invoke(...)
        # route to one of the agents or exit based on the supervisor's decision
        # if the supervisor returns "__end__", the graph will finish execution

        """
        Determines whether the retrieved documents are relevant to the question.

        Args:
            state (messages): The current state

        Returns:
            str: A decision for whether the documents are relevant or not
        """

        print("---CHECK RELEVANCE---")

        members = ["web_searcher", "diary_searcher"]

        system_prompt = (
            "You are a supervisor tasked with managing a conversation between the"
            f" following workers: {members}. Given the following user request,"
            " respond with the worker to act next. Each worker will perform a"
            " task and respond with their results and status. When finished,"
            " respond with FINISH."
        )

        class Router(TypedDict):
            """Worker to route to next. If no workers needed, route to FINISH."""
            next: Literal["web_searcher", "diary_searcher", "FINISH"]

        llm = ChatAnthropic(model="claude-3-5-sonnet-latest")
        messages = [
            {"role": "system", "content": system_prompt},
        ] + state["messages"]
        response = llm.with_structured_output(Router).invoke(messages)
        goto = response["next"]
        if goto == "FINISH":
            goto = END

        return Command(goto=goto)

    def _chatbot_node(self, state: State):
        # llm = ChatOpenAI(model="gpt-4o")
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro-latest")
        # llm = ChatAnthropic(model="claude-3-5-sonnet-latest")
        llm_with_tools = llm.bind_tools(self.tools)
        prompt = get_character_prompt(self.userid)
        chatbot_chain = prompt | llm_with_tools
        return {"messages": [chatbot_chain.invoke(state)]}

    def _tool_node(self, state: State):
        return ToolNode(tools=self.tools)

    def invoke(self, messages: list):
        recursion_limit = 8
        return self.graph.invoke({"messages": messages}, {"recursion_limit": recursion_limit})

    def stream(self, messages: list):
        recursion_limit = 8
        events = self.graph.stream({"messages": messages}, {"recursion_limit": recursion_limit})

        for event in events:
            yield event

    def create_image(self):
        graph_image = self.graph.get_graph(xray=True).draw_mermaid_png()
        with open("quick_start.png", "wb") as f:
            f.write(graph_image)


if __name__ == "__main__":
    history = [
        ("user", "こんばんは、わたしはともどです。"),
        ("assistant", "こんにちは！ともど！悩みがあるなら、話してみてちょうだい"),
    ]

    userid = os.environ.get("LINE_USER_ID")

    agent_graph = ChatbotAgent(userid)

    # agent_graph.create_image()

    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        history.append({"type": "human", "content": user_input})
        for event in agent_graph.stream(history):
            for value in event.values():
                print("Assistant:", value["messages"][-1].content)
                history.append({"type": "assistant", "content": value["messages"][-1].content})
