"""ChatbotAgent class definition - Deep Agent based chatbot."""

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from chatbot.agent.character_graph.prompts import DEEP_AGENT_PROMPT
from chatbot.agent.tools import diary_search_tool
from chatbot.utils import get_japan_datetime
from chatbot.utils.config import create_logger

logger = create_logger(__name__)


class ChatbotAgent:
    def __init__(self, agent) -> None:
        self.agent = agent

    @classmethod
    async def create(cls) -> "ChatbotAgent":
        """Deep Agent を構築して ChatbotAgent を返す async factory。"""
        logger.info("ChatbotAgent.create: initializing Deep Agent")

        all_tools = [
            diary_search_tool,
            {"type": "web_search_preview"},
        ]

        system_prompt = DEEP_AGENT_PROMPT.format(current_datetime=get_japan_datetime())

        llm = ChatOpenAI(model="gpt-5.6-terra", reasoning_effort="low")
        agent = create_deep_agent(model=llm, tools=all_tools, system_prompt=system_prompt)
        return cls(agent)

    async def ainvoke(self, messages: list, userid: str, session_id: str) -> dict:
        """エージェントを実行し、最終ステートを返す。"""
        logger.info("ChatbotAgent.ainvoke: userid=%s, session_id=%s", userid, session_id)
        config = {"configurable": {"thread_id": session_id, "userid": userid}}
        return await self.agent.ainvoke({"messages": messages}, config)
