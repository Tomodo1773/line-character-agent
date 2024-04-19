import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langsmith import Client

from utils.common import read_markdown_file

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

client = Client()


def generate_chat_response(user_prompt):

    parser = StrOutputParser()

    # プロンプトを設定
    system_prompt = read_markdown_file("prompts/system_prompt.md")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "{user_input}"),
        ],
    )

    # chatモデルを設定
    chat = ChatOpenAI(model_name="gpt-4-turbo", temperature=1, max_tokens=512)

    # chainを設定
    chain = prompt | chat | parser
    result = chain.invoke({"user_input": user_prompt})

    return result


if __name__ == "__main__":
    generate_chat_response("こんにちは")
