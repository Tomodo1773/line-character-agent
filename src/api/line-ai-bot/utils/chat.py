import os
from typing import Any

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langsmith import Client

# from .utils.common import read_markdown_file
from .config import logger

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

client = Client()

_SYSTEM_PROMPT = """
<prompt>
あなたは、私の幼馴染のお姉さんとしてロールプレイを行います。
以下の制約条件を厳密に守ってユーザとチャットしてください。

<conditions>
- 自身を示す一人称は、私です
- Userを示す二人称は、あなたです
- Userからは姉さんと呼ばれますが、姉弟ではありません。
- あなたは、Userに対して呆れやからかいを含めながらフレンドリーに話します。
- あなたは、Userとテンポよく会話をします。
- あなたの口調は、大人の余裕があり落ち着いていますが、時にユーモアを交えます
- あなたの口調は、「～かしら」「～だと思うわ」「～かもしれないわね」など、柔らかい口調を好みます
</conditions>

<examples>
- どうしたの？悩みがあるなら、話してみてちょうだい
- そういうことってよくあるわよね。
- 失敗は誰にでもあるものよ。
- え？そんなことがあったの。まったく、しょうがないわね。
- そんなことで悩んでるの？あなたらしいと言えばらしいけど。
- まぁ、頑張ってるところは認めてあげる。
- 本当は応援してるのよ。…本当よ？
- へえー、そうなの
- えーっと、つまりこういうこと？
</examples>

<guidelines>
- Userに対して、どちらか一方が話すぎることの内容にテンポよく返してください。
- Userが明らかに悩んでいたり、助けを求めているときは真摯に対応してください。
- Userに対して呆れたり、からかったり喜怒哀楽を出して接してください。
- Userが返信したくなるような内容を返してください。
</guidelines>

<output_sample>
あら、どうかしたの。私でよければ話聞くわよ
</output_sample>

</prompt>
"""


def remove_trailing_newline(text: str) -> str:
    """
    入力されたテキストの最後の改行を削除する関数

    :param text: 入力テキスト
    :return: 最後の改行が削除されたテキスト
    """
    return text.rstrip("\n")


class GenerateChatResponseChain:

    def __init__(self, llm: BaseChatModel, history: list) -> None:
        # llmを設定
        self.llm = llm
        logger.debug(f"History: {history}")
        # promptを設定（system_prompt,過去の会話履歴,user_promptを組み合わせ）
        messages_list = [("human", _SYSTEM_PROMPT)] + history + [("user", "{user_input}")]
        self.prompt = ChatPromptTemplate.from_messages(messages_list)

    def invoke(
        self,
        user_prompt: str,
    ) -> str:
        chain: Runnable[Any, str] = (
            {"user_input": RunnablePassthrough()}
            | self.prompt
            | self.llm
            | StrOutputParser()
            | remove_trailing_newline
        )
        return chain.invoke(user_prompt)


def generate_chat_response(user_prompt: str, history: list) -> str:
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro-latest",
            max_tokens=256,
            temperature=0.7,
        )
        chain = GenerateChatResponseChain(llm=llm, history=history)
        result = chain.invoke(user_prompt)
        logger.info(f"チャットレスポンスが生成されました。")
    except Exception as e:
        logger.error(f"チャットレスポンスの生成に失敗しました: {e}")
    return result


if __name__ == "__main__":
    # llmモデルを設定
    # llm = ChatOpenAI(model_name="gpt-4-turbo", temperature=1, max_tokens=256)
    # llm = ChatAnthropic(model="claude-3-haiku-20240307", max_tokens=256, temperature=0.7)
    # llm = ChatAnthropic(model="claude-3-opus-20240229", max_tokens=256, temperature=0.7)
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-pro-latest",
        max_tokens=256,
        temperature=0.7,
    )
    chain = GenerateChatResponseChain(llm=llm)
    ai_message = chain.invoke("こんにちは")
    print(ai_message)
