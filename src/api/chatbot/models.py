from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class Message(BaseModel):
    role: MessageRole
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    max_tokens: Optional[int] = None
    stream: bool = True
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = 0
    frequency_penalty: Optional[float] = 0
    user: Optional[str] = None


class ChatCompletionResponseMessage(BaseModel):
    role: str
    content: str


class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatCompletionResponseMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str = "chatbot-agent"
    choices: List[ChatCompletionResponseChoice]
    usage: Dict[str, int]


class ChatCompletionStreamResponseChoiceDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionStreamResponseChoice(BaseModel):
    index: int
    delta: ChatCompletionStreamResponseChoiceDelta
    finish_reason: Optional[str] = None


class ChatCompletionStreamResponse(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str = "chatbot-agent"
    choices: List[ChatCompletionStreamResponseChoice]
    usage: Optional[Dict[str, int]] = None
