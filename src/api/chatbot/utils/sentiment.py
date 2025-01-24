from langchain import hub
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from chatbot.utils import remove_trailing_newline
from typing import List, AsyncGenerator, Tuple
from langsmith import traceable

load_dotenv()


@traceable(run_type="tool", name="TaggingSentiment")
async def sentiment_tagging(question: str) -> str:
    prompt = hub.pull("tomodo1773/sentiment-tagging-prompt")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

    chain = prompt | llm | StrOutputParser() | remove_trailing_newline

    sentiment = await chain.ainvoke({"question": question})

    return sentiment


@traceable(name="TaggingSentiment")
async def tag_sentiments_stream(questions: List[str]) -> AsyncGenerator[Tuple[str, str], None]:
    for question in questions:
        sentiment = await sentiment_tagging(question)
        yield (question, sentiment)


if __name__ == "__main__":
    import asyncio
    import os

    # Optional, add tracing in LangSmith
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = "LINE-AI-BOT"

    async def main():
        questions = ["今日はいい天気ですね。", "明日は雨が降るかもしれません。"]
        async for message, sentiment in tag_sentiments_stream(questions):
            print(f"メッセージ: {message}, 感情: {sentiment}")

    asyncio.run(main())
