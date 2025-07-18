import getpass
import os
import tempfile

from chatbot.utils.google_drive_utils import get_dictionary_from_drive
from chatbot.utils import remove_trailing_newline
from chatbot.utils.config import create_logger
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import OpenAI

logger = create_logger(__name__)

# ############################################
# 事前準備
# ############################################


def _set_if_undefined(var: str) -> None:
    # 環境変数が未設定の場合、ユーザーに入力を促す
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"Please provide your {var}")


# 必要な環境変数を設定
_set_if_undefined("OPENAI_API_KEY")

# Optional, add tracing in LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "LINE-AI-BOT"

system_prompt = """
# 命令文

以下の手順に従って、ユーザから提供される音声文字おこしされた日記のエントリを修正し、読みやすさを向上させてください。

1. 書き起こされた日記のテキストがユーザから提供されます:

2. 以下は日記に登場する可能性のある家族の名前の一覧です:

{user_dictionary}

3. 誤認された固有名詞の修正:
    - 書き起こされた日記のテキストを慎重に読みます。
    - 名前や潜在的な固有名詞を提供された家族の名前の一覧と比較します。
    - 誤認された名前や固有名詞が見つかった場合、それを提供された家族の名前と一致するように修正します。
    - コンテキストの手がかりに注意して、修正が適切であることを確認します。

4. 適切な改行の追加:
    - 日記の内容を分析し、異なる出来事、考え、または時期を特定します。
    - これらの異なるセクションの間に改行を挿入して、読みやすさを向上させます。
    - 関連する情報がまとまっていることを確認します。
    - 大きなテキストブロックを分割することと、統一された段落を維持するバランスを目指します。

5. 修正されたテキストの出力:
    - 必要な修正と改行の追加をすべて行った後、修正されたテキストを提供します。


# 制約

- 日記の原本の調子やスタイルを維持し、～です、～ます、～だ、～であるなどの口調は変えないでください。
- 指定された修正とフォーマット変更のみを行ってください。指定された範囲を超えて内容を追加または削除しないでください。

# 出力

修正およびフォーマットされた日記のテキストを提供してください。
余計な前置きなど日記の内容以外の情報は含めないでください。
"""


class DiaryTranscription:
    def __init__(self) -> None:
        self.chain = self._create_chain()

    def invoke(
        self,
        audio_content: bytes,
    ) -> str:
        try:
            return self.chain.invoke(audio_content)
        except Exception as e:
            logger.error(f"Generate diary transcription error: {e}")
            raise RuntimeError(f"Generate diary transcription error: {e}") from e

    def _create_chain(self):
        chat = ChatOpenAI(model="gpt-4o", temperature=0.2)
        # chat = ChatGoogleGenerativeAI(
        #     model="gemini-1.5-pro-latest",
        #     temperature=0.2,
        #     max_tokens=128000,
        # )
        # chat = ChatAnthropic(model="claude-3-5-sonnet-latest")
        template = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{transcribed_text}"),
            ]
        )
        prompt = template.partial(user_dictionary=self._read_dictionary())
        chain = self.transcription | prompt | chat | StrOutputParser() | remove_trailing_newline
        configured_chain = chain.with_config({"run_name": "DiaryTranscription"})
        return configured_chain

    def _read_dictionary(self) -> str:
        return get_dictionary_from_drive()

    def transcription(self, audio_file: bytes) -> str:
        file_path = self._save_audio(audio_file)
        with open(file_path, "rb") as f:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=f,
                response_format="text"
            )
        return {"transcribed_text": transcript}

    def _save_audio(self, audio_file: bytes) -> str:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, "temp.m4a")
        with open(file_path, "wb") as f:
            f.write(audio_file)
        return file_path
