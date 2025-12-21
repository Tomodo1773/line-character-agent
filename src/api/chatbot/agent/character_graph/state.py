"""LangGraph State definitions for character graph."""

from typing import Annotated, NotRequired

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class State(TypedDict):
    """State for the chatbot agent graph.

    Messages have the type "list". The `add_messages` function
    in the annotation defines how this state key should be updated
    (in this case, it appends messages to the list, rather than overwriting them)
    """

    messages: Annotated[list, add_messages]
    userid: str
    profile: NotRequired[str]
    digest: NotRequired[str]
    resume_value: NotRequired[str]  # aresumeで渡された値を保持
