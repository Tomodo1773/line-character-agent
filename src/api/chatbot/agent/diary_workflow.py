"""LangGraphベースの日記登録ワークフロー定義。"""

import os
from typing import Annotated, Any

from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langsmith import traceable
from typing_extensions import NotRequired, TypedDict

from chatbot.agent import ChatbotAgent
from chatbot.agent.character import ensure_google_settings_command
from chatbot.database.repositories import UserRepository
from chatbot.utils.agent_response import extract_agent_text
from chatbot.utils.config import create_logger
from chatbot.utils.diary_utils import generate_diary_digest, save_digest_to_drive, save_diary_to_drive
from chatbot.utils.google_auth import GoogleDriveOAuthManager
from chatbot.utils.google_drive import GoogleDriveHandler
from chatbot.utils.transcript import DiaryTranscription


class DiaryWorkflowState(TypedDict):
    messages: Annotated[list, add_messages]
    userid: str
    session_id: str
    audio: bytes | None
    diary_text: NotRequired[str | None]
    saved_filename: NotRequired[str | None]
    digest_text: NotRequired[str | None]
    digest_saved: NotRequired[bool]
    character_comment: NotRequired[str | None]
    drive_handler: NotRequired[GoogleDriveHandler | None]


logger = create_logger(__name__)


def _create_drive_handler(userid: str) -> GoogleDriveHandler | None:
    user_repository = UserRepository()
    credentials = GoogleDriveOAuthManager(user_repository).get_user_credentials(userid)
    folder_id = user_repository.fetch_drive_folder_id(userid)
    if not credentials or not folder_id:
        return None
    return GoogleDriveHandler(credentials=credentials, folder_id=folder_id)


def get_diary_workflow(agent_checkpointer: BaseCheckpointSaver | None = None) -> Any:
    graph_builder = StateGraph(DiaryWorkflowState)

    @traceable(run_type="tool", name="Ensure Google Settings")
    def ensure_google_settings_node(state: DiaryWorkflowState) -> Command[str]:
        logger.info("--- Diary Workflow: ensure_google_settings ---")
        return ensure_google_settings_command(
            userid=state["userid"], messages=state.get("messages", []), success_goto="transcribe_diary_node"
        )

    @traceable(run_type="tool", name="Transcribe Diary")
    def transcribe_diary_node(state: DiaryWorkflowState) -> Command[str]:
        logger.info("--- Diary Workflow: transcribe_diary ---")
        drive_handler = _create_drive_handler(state["userid"])
        audio = state.get("audio")

        if not drive_handler:
            message = AIMessage(content="Google Driveの設定が見つからなかったよ。もう一度確認してみて。")
            return Command(goto="__end__", update={"messages": [message]})

        if not audio:
            message = AIMessage(content="音声を受け取れなかったみたい。もう一度送ってね。")
            return Command(goto="__end__", update={"messages": [message]})

        diary_text = DiaryTranscription(drive_handler).invoke(audio)
        return Command(goto="save_diary_node", update={"drive_handler": drive_handler, "diary_text": diary_text})

    @traceable(run_type="tool", name="Save Diary")
    def save_diary_node(state: DiaryWorkflowState) -> Command[str]:
        logger.info("--- Diary Workflow: save_diary ---")
        diary_text = state.get("diary_text")
        drive_handler = state.get("drive_handler")

        if not diary_text or not drive_handler:
            message = AIMessage(content="日記の文字起こしに失敗しちゃった。もう一度試してね。")
            return Command(goto="__end__", update={"messages": [message]})

        saved_filename = save_diary_to_drive(diary_text, drive_handler)
        if saved_filename:
            message = AIMessage(content=f"日記を'{saved_filename}'に保存したわよ。")
        else:
            message = AIMessage(content="日記の保存に失敗しちゃった。もう一度試してね。")

        return Command(
            goto="generate_digest_node",
            update={"messages": [message], "saved_filename": saved_filename, "drive_handler": drive_handler},
        )

    @traceable(run_type="tool", name="Generate Digest")
    def generate_digest_node(state: DiaryWorkflowState) -> Command[str]:
        logger.info("--- Diary Workflow: generate_digest ---")
        diary_text = state.get("diary_text")
        saved_filename = state.get("saved_filename")
        drive_handler = state.get("drive_handler")

        if not diary_text or not saved_filename or not drive_handler:
            return Command(goto="invoke_character_comment_node")

        digest = generate_diary_digest(diary_text)
        digest_saved = False
        if digest:
            digest_saved = save_digest_to_drive(digest, saved_filename, drive_handler)

        update: dict[str, Any] = {"digest_text": digest or "", "digest_saved": digest_saved}
        if digest_saved:
            update["messages"] = [AIMessage(content="ダイジェストも保存しておいたよ。")]

        return Command(goto="invoke_character_comment_node", update=update)

    @traceable(run_type="tool", name="Invoke Character Comment")
    async def invoke_character_comment_node(state: DiaryWorkflowState) -> dict:
        logger.info("--- Diary Workflow: invoke_character_comment ---")
        diary_text = state.get("diary_text")
        if not diary_text:
            return {"messages": [AIMessage(content="日記の文字起こしが空だったからコメントは省略するね。")]}

        agent = ChatbotAgent(checkpointer=agent_checkpointer)
        reaction_prompt = """以下の日記に対して一言だけ感想を言って。
内容全部に対してコメントしなくていいから、一番印象に残った部分についてコメントして。
{diary_text}
""".strip().format(diary_text=diary_text)
        response = await agent.ainvoke(
            messages=[{"type": "human", "content": reaction_prompt}],
            userid=state["userid"],
            session_id=state["session_id"],
        )
        reaction, _ = extract_agent_text(response)
        return {"character_comment": reaction, "messages": [AIMessage(content=reaction)]}

    graph_builder.add_node("ensure_google_settings_node", ensure_google_settings_node)
    graph_builder.add_edge(START, "ensure_google_settings_node")
    graph_builder.add_node("transcribe_diary_node", transcribe_diary_node)
    graph_builder.add_node("save_diary_node", save_diary_node)
    graph_builder.add_node("generate_digest_node", generate_digest_node)
    graph_builder.add_node("invoke_character_comment_node", invoke_character_comment_node)
    graph_builder.add_edge("ensure_google_settings_node", "transcribe_diary_node")
    graph_builder.add_edge("transcribe_diary_node", "save_diary_node")
    graph_builder.add_edge("save_diary_node", "generate_digest_node")
    graph_builder.add_edge("generate_digest_node", "invoke_character_comment_node")

    return graph_builder.compile()


def create_diary_workflow_image(agent_checkpointer: BaseCheckpointSaver | None = None) -> None:
    graph = get_diary_workflow(agent_checkpointer=agent_checkpointer)

    images_dir = "images"
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)

    graph_image = graph.get_graph(xray=True).draw_mermaid_png()
    with open(os.path.join(images_dir, "diary_workflow_graph.png"), "wb") as f:
        f.write(graph_image)
