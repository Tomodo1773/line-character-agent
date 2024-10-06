import getpass
import os
import tempfile

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from openai import OpenAI
from chatbot.database import NameCosmosDB
from chatbot.agent.prompt import get_character_prompt
from chatbot.utils import remove_trailing_newline

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

reaction_prompt = """以下の日記に対して一言だけ感想を言って。
内容全部に対してコメントしなくていいから、一番印象に残った部分についてコメントして。
{diary_content}
"""


class DiaryTranscription:
    def __init__(self) -> None:
        self.chain = self._create_chain()

    def invoke(
        self,
        audio_content: bytes,
    ) -> str:
        return self.chain.invoke(audio_content)

    def _create_chain(self):
        # chat = ChatOpenAI(model="gpt-4o-mini", temperature=0.4)
        chat = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro-latest",
            temperature=0.2,
        )
        template = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{transcribed_text}"),
            ]
        )
        prompt = template.partial(user_dictionary=self._read_dictionary())
        chain = self._transcription | prompt | chat | StrOutputParser() | remove_trailing_newline
        return chain

    def _read_dictionary(self) -> str:
        cosmos = NameCosmosDB()
        return cosmos.fetch_names()

    def _transcription(self, audio_file: bytes) -> str:
        file_path = self._save_audio(audio_file)

        with open(file_path, "rb") as audio_file:
            # transcript = openai.audio.transcriptions.create(
            #     model="whisper-1",
            #     file=audio_file,
            # )
            groq = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
            transcript = groq.audio.transcriptions.create(
                model="whisper-large-v3", file=audio_file, response_format="text"
            )
        return {"transcribed_text": transcript}

    def _save_audio(self, audio_file: bytes) -> str:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, "temp.m4a")
        with open(file_path, "wb") as f:
            f.write(audio_file)
        return file_path


class DiaryReaction:
    def __init__(self) -> None:
        self.chain = self._create_chain()

    def invoke(
        self,
        diary_content: str,
    ) -> str:
        return self.chain.invoke({"diary_content": diary_content})

    def _create_chain(self):
        # chat = ChatOpenAI(model="gpt-4o-mini", temperature=0.4)
        chat = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro-latest",
            temperature=0.7,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", get_character_prompt()),
                ("human", reaction_prompt),
            ]
        )
        chain = prompt | chat | StrOutputParser() | remove_trailing_newline
        return chain

if __name__ == "__main__":
    diary ="""
今日は海に行った。\n\n
海岸で、たくさんの貝殻を拾った。
夕方には、美しい夕焼けを見ることができた。
明日も海に行きたい。
"""

    # diary="今日はAzure Users Groupのイベントに行く日。\n\n朝はいつも通りに起きてみんなで支度して過ごしてた。僕は相変わらずお尻の状態がそれほど良くもなくて、休み休み何とか準備してた。11時くらいになったら家を出た。一回家を出て靴下が靴ずれしそうだから戻って、その後財布を忘れたことに気づいてもう一回戻ってって、なかなかドタバタな感じだった。なんか抜けてるな。\n\n移動時間はなんか胃の調子が悪いから胃薬を買って飲んで、会場にギリギリに着いた。本当にギリギリだったから、ずっと着くかどうかハラハラしてた。ただ着いてからは前回来たとこと同じ場所だから落ち着いて冷蔵庫からドリンクを選んで電源を確保してパソコンを立ち上げて、ゆったりセミナーを聞けた。\n\nセミナーは今日は特に興味のあるものがない時間帯も多かったから、逆に今まで知らない技術も聞くことができた。「.NET Aspire」とか、エントラIDの機能とか、Service。\n\n今日も懇親会まで参加した。懇親会はなんだか時間が短く感じる。今日は、顔でSAPを主に常室でやっている人と、R&Dでセキュリティ関連のことをやっているスピリチュアル系のお姉さんとお話をした。あと、マイクロソフトのソリューションアーキテクトの人とも話した。色々話したけど、今日はちゃんとXのアカウントの交換までいけて、僕もやってみようかなって思った。\n\n7時くらいに終わって、急いで帰ったらうみちゃんに会えるかもしれないと思ったから、あつどんへのマカロンを買って急いで帰った。ただ急いで帰ったけど結局うみちゃんはもう寝ちゃってて残念だったけど、でもあつこさんはマカロンすごく喜んでくれて嬉しかった。\n\n僕は久しぶりの外出でちょっと気が晴れた。お尻の調子が良ければもうちょっとマシだったんだけどな。でもやっぱりこうやってちまちまコミュニティに顔を出して知り合いを増やしていって、Xでのつながりも増やしていけば、いつかマイクロソフトMVPへの道とかも開けるような気がして、ちょっとずつ頑張っていこうってまた少しやる気が出た日だった。 "

    chain = DiaryReaction()
    reaction = chain.invoke(diary)

    print(reaction)