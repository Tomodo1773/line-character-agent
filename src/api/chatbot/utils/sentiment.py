from langchain import hub
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser

load_dotenv()


async def sentiment_tagging(question: str) -> str:
    prompt = hub.pull("tomodo1773/sentiment-tagging-prompt")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

    chain = prompt | llm | StrOutputParser()

    sentiment = await chain.ainvoke({"question": question})

    return sentiment


if __name__ == "__main__":
    import asyncio

    response = asyncio.run(sentiment_tagging("今日はいい天気ですね。"))
    print(response)
