"""ChatbotAgent class definition - LangGraph-based chatbot agent."""

import asyncio
import os
import uuid

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph

from chatbot.agent.character_graph.nodes import (
    chatbot_node,
    diary_agent_node,
    router_node,
    set_cached,
    spotify_agent_node,
)
from chatbot.agent.character_graph.state import State
from chatbot.utils.config import create_logger

logger = create_logger(__name__)


class ChatbotAgent:
    RECURSION_LIMIT = 20

    def __init__(self, cached: dict | None = None, checkpointer: BaseCheckpointSaver | None = None) -> None:
        """Initialize agent with cached data"""
        if cached:
            set_cached(cached)

        graph_builder = StateGraph(State)
        graph_builder.add_node("router", router_node)
        graph_builder.add_edge(START, "router")
        graph_builder.add_node("chatbot", chatbot_node)
        graph_builder.add_node("spotify_agent", spotify_agent_node)
        graph_builder.add_node("diary_agent", diary_agent_node)
        self.checkpointer = checkpointer
        self.graph = graph_builder.compile(checkpointer=self.checkpointer)

    def _config(self, session_id: str, user_repository=None) -> dict:
        return {
            "recursion_limit": self.RECURSION_LIMIT,
            "configurable": {"thread_id": session_id, "user_repository": user_repository},
        }

    async def ainvoke(self, messages: list, userid: str, session_id: str, user_repository=None):
        return await self.graph.ainvoke(
            {"messages": messages, "userid": userid},
            self._config(session_id, user_repository),
        )

    async def astream(self, messages: list, userid: str, session_id: str, user_repository=None):
        async for msg, metadata in self.graph.astream(
            {"messages": messages, "userid": userid},
            self._config(session_id, user_repository),
            stream_mode="messages",
        ):
            yield msg, metadata

    async def astream_updates(self, messages: list, userid: str, session_id: str, user_repository=None):
        async for msg in self.graph.astream(
            {"messages": messages, "userid": userid},
            self._config(session_id, user_repository),
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
    # CLI 実行時はインメモリのチェックポインタを使用
    from langgraph.checkpoint.memory import MemorySaver

    agent_graph = ChatbotAgent(checkpointer=MemorySaver())

    userid = "local-user"
    session_id = uuid.uuid4().hex

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
            async for msg in agent_graph.astream_updates(messages=history, userid=userid, session_id=session_id):
                print(f"msg: {msg}")
                print("\n")

            # print(event)
            # for value in event.values():
            #     if value and "messages" in value:
            #         print("Assistant:", value["messages"][-1].content)
            # history.append({"type": "assistant", "content": value["messages"][-1].content})

    asyncio.run(main())
