"""ChatbotAgent class definition - Deep Agent based chatbot."""

from deepagents import create_deep_agent
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_openai import ChatOpenAI

from chatbot.agent.character_graph.prompts import DEEP_AGENT_PROMPT
from chatbot.agent.tools import (
    diary_create_tool,
    diary_drive_tool,
    diary_search_tool,
    diary_update_tool,
    read_digest,
    read_profile,
)
from chatbot.utils import get_japan_datetime
from chatbot.utils.config import create_logger

logger = create_logger(__name__)


class ChatbotAgent:
    def __init__(self, agent, checkpointer: BaseCheckpointSaver | None = None) -> None:
        self.agent = agent
        self.checkpointer = checkpointer

    @classmethod
    async def create(cls, checkpointer: BaseCheckpointSaver | None = None):
        """Deep Agent を構築して ChatbotAgent を返す async factory。"""
        logger.info("ChatbotAgent.create: initializing Deep Agent")

        all_tools = [
            read_profile,
            read_digest,
            diary_search_tool,
            diary_drive_tool,
            diary_create_tool,
            diary_update_tool,
            {"type": "web_search_preview"},
        ]

        system_prompt = DEEP_AGENT_PROMPT.format(current_datetime=get_japan_datetime())

        llm = ChatOpenAI(model="gpt-5.2", temperature=1.0)
        agent = create_deep_agent(
            model=llm,
            tools=all_tools,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
        )

        return cls(agent, checkpointer)

    def _config(self, session_id: str, userid: str, user_repository=None) -> dict:
        return {
            "configurable": {
                "thread_id": session_id,
                "userid": userid,
                "user_repository": user_repository,
            },
        }

    async def ainvoke(self, messages: list, userid: str, session_id: str, user_repository=None):
        config = self._config(session_id, userid, user_repository)
        async for chunk in self.agent.astream(
            {"messages": messages},
            config,
            stream_mode="updates",
        ):
            for node_name, state_update in chunk.items():
                if node_name == "__start__":
                    continue
                if node_name == "tools":
                    tool_messages = [m for m in state_update.get("messages", []) if hasattr(m, "name")]
                    tool_names = [m.name for m in tool_messages]
                    logger.info(f"Agent node [{node_name}]: tools={tool_names}")
                else:
                    logger.info(f"Agent node [{node_name}]")
        state = await self.agent.aget_state(config)
        return state.values
