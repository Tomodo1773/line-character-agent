from langchain import hub
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from chatbot.utils import remove_trailing_newline

load_dotenv()


async def sentiment_tagging(question: str) -> str:
    prompt = hub.pull("tomodo1773/sentiment-tagging-prompt")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

    chain = (prompt | llm | StrOutputParser()).with_config({"run_name": "TaggingSentiment"}) | remove_trailing_newline

    sentiment = await chain.ainvoke({"question": question})

    return sentiment


if __name__ == "__main__":
    import asyncio

    response = asyncio.run(sentiment_tagging("今日はいい天気ですね。"))
    print(response)
