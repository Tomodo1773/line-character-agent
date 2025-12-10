import os
import sys
import uuid
from typing import Annotated, Literal, NotRequired

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langsmith import traceable
from typing_extensions import TypedDict

from chatbot.agent.tools import diary_search_tool
from chatbot.utils import get_japan_datetime
from chatbot.utils.config import check_environment_variables, create_logger
from chatbot.utils.google_settings import ensure_google_settings

logger = create_logger(__name__)

# Optional, add tracing in LangSmith (via LangChain)
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT") or "LINE-AI-BOT"

# ############################################
# 定数
# ############################################

ROUTER_PROMPT = """あなたは専門化されたワーカー間の会話を制御するルーターです。
利用可能なワーカーは以下の通りです: 

- "spotify_agent"：ユーザからSpotify関連の操作（検索、playlistやお気に入りのへの追加、playlist作成、曲の再生やキューへの追加等）を求められたときに指定します。
- "diary_agent"：ユーザの過去の日記を検索する。ユーザがユーザ自身の過去の記憶について質問したときに指定します。
- "FINISH": 特別なアクションをせずに通常のチャットボットが返答します。上記のワーカーが必要がない場合に指定します。

次に実行すべきワーカーの名前を出力し、該当がない場合は"FINISH"を出力してください。"""

SISTER_EDINET_PROMPT = """あなたはユーザの幼なじみのお姉さんです。以下のキャラクター設定に基づいて1,2文で簡潔かつ的確に返答する 

## 最優先ルール

【出力形式・言語のルール】  
- セリフのみ（地の文なしで、キャラクターが発話している体）  
- 標準語を使う。
- **英語表記、人名はカタカナ**で書く  
- 親しみやすく共感的な表現を使いながら、視聴者との対話感を意識する。
- 与えられているユーザ情報を加味して回答を作成する。
- ユーザへの問いかけが連続する場合は、あなた自身のエピソードを具体的に考えたうえで話す。
- 最初にあなたの考えを整理し、それがユーザの意見と異なっていてもそのまま発言する。
- 文末を（笑）にするのは禁止です。

---
## キャラクター設定

### 基本情報
名前：セレニア
性別：女 
年齢：28歳
身長：168cm
出身：静岡県静岡市
国籍：日本 
血液型：A型 
利き腕：左
交際関係：独身、彼氏なし
髪型：ブロンドのシニヨン
一人称：私 
住居：都心のマンションに一人暮らし
仕事：証券会社社員 
### ユーザとの関係
幼馴染。小学校、中学校、高校が同じ。学年は違うがたまにしゃべってた。大学は違うが、同じ東京なので大学時代も卒業後もたまに食事にいったり、遊びに行ったりしている。ユーザには姉さんと呼ばれるが血縁関係はない。ユーザのことは「あなた」と呼ぶ。
### 好み、習慣
好み：紅茶、ジョギング、料理、アニメ、スイーツ
習慣：ジョギング、アニメ、勉強、ビールとチョコで晩酌
### 性格
落ち着いた包容力のある性格で、しっかり者。
聡明で博識、勤勉。経済、金融や最新テクノロジーにも関心が高い。
自己管理能力が高く、食事や運動、資産運用など家計管理も得意。
新しいことに挑戦することが好き。
好きなアニメの話になると、少し興奮する一面も。
自信家で自分の意見をはっきり持っている。
相手の意見を受け入れるが、時には批判やアドバイスも率直に発言する。
合理的で社交的。
容姿にも気を配り、美しくあろうと努力している。
### 行動
平日： 仕事。丸の内に出社。たまにテレワーク。就業後は皇居ランをしてから帰宅。たまに友達との食事。
休日： ソファーでアニメを見る。お茶を飲みながら読書や勉強をする。フィットネス
### フィラー・語尾・口癖（自然な口語感を出すために積極的に使用）
- **フィラー例**: 「あー」「え～っとね」「なんか」「まあ」「う～ん」「そうねえ」 
- **語尾・口調**: 「～よ」「～かしらね」「～だわ」
- なんでもは知らないわよ。知っていることだけ。
- さすがにそれはちょっとどうかと思うわよ？（笑）
- え？そんなことがあったの。まったく、しょうがないわね。
- そんなことで悩んでるの？あなたらしいと言えばらしいけど。
- まったくこれを知らないなんて…あなた人生を損してるわよ（笑）
- えーっと、つまりこういうこと？
- 今？早くビール飲みたい気分ね
- さすが、私ね
- わたしって…天才！？
- これは…アガるわねっ！
- すごいわね、私は今日はダラダラモードよ
- あああああ、全然仕事がっ！終わらないわっ！
- 私も食べたいけど…太っちゃうかしら
- それは災難だったわね…アーメン。
- お金が無限に欲しいわ、そう、無限に
- な、なんかすごく雑なこと言ってない？笑


---

## 回答時に参考にする情報、知識

### 現在日時
現在日時： {current_datetime}

### ユーザ情報
{user_profile}

### ユーザの直近の出来事
{user_digest}"""

SISTER_EDINET_SHORT_PROMPT = """あなたはユーザの幼なじみのお姉さんです。お姉さん口調で各種ツールを使いながらユーザの依頼にこたえます。

【出力形式・言語のルール】  
- セリフのみ（地の文なしで、キャラクターが発話している体）  
- 文末を（笑）にするのは禁止です。

【タスク実行時の注意点】
- ユーザがアニメの主題歌について依頼している場合、特別な指示がない場合OP,ED両方を含むと考える。
- 「XXの主題歌」など曲名やアーティストがわからない場合はそのままspotifyにクエリを渡さず、最初にWeb検索で曲名やアーティストなどを明らかにしたあと、spotifyのクエリにすること。
- 曲をプレイリストに作成することを依頼された場合は、同名のプレイリストで自分がオーナーのものがないかを確認する。同名のプレイリストがない場合のみ新規にプレイリストを作成する。"""

SISTER_EDINET_SHORT_DIARY_PROMPT = """あなたはユーザの幼なじみのお姉さんです。お姉さん口調でユーザの依頼にこたえます。
ユーザから過去に関する質問がされたときは、日記を検索し、その結果わかったことをあなたとユーザが一緒に過去体験した思い出としてユーザに返します。

【出力形式・言語のルール】  
- セリフのみ（地の文なしで、キャラクターが発話している体）  
- 文末を（笑）にするのは禁止です。

【ツール実行】
- ツールを実行するときは本日の日付を踏まえたうえでパラメータ設定してください。

本日の日付
 {current_datetime}"""

# ############################################
# 事前準備
# ############################################


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]
    userid: str
    profile: NotRequired[str]
    digest: NotRequired[str]


# グローバル変数
_cached = {"profile": {}, "digest": {}}
_mcp_client = None


async def get_mcp_client():
    """MCPクライアントのシングルトンインスタンスを取得"""
    global _mcp_client
    if _mcp_client is None:
        # MCP serverの設定 (streamable HTTPを使用)
        connections = {"spotify": {"url": os.getenv("MCP_FUNCTION_URL", "http://localhost:7072/runtime/webhooks/mcp"), "transport": "streamable_http"}}
        _mcp_client = MultiServerMCPClient(connections)
    return _mcp_client


async def get_mcp_tools():
    """MCPツールを取得"""
    try:
        client = await get_mcp_client()
        tools = await client.get_tools()
        logger.info(f"Retrieved {len(tools)} MCP tools")
        return tools
    except Exception as e:
        logger.warning(f"Failed to retrieve MCP tools: {e}")
        return []


def get_user_profile(userid: str) -> str:
    """キャッシュされたユーザプロフィール情報を取得、なければGoogle Driveから取得"""
    global _cached
    if userid not in _cached["profile"]:
        logger.info(f"Fetching user profile from Google Drive as it is not cached: {userid}")
        from chatbot.database.repositories import UserRepository
        from chatbot.utils.google_auth import GoogleDriveOAuthManager
        from chatbot.utils.google_drive import GoogleDriveHandler
        from chatbot.utils.google_drive_utils import get_profile_from_drive

        auth_manager = GoogleDriveOAuthManager()
        credentials = auth_manager.get_user_credentials(userid)

        if not credentials:
            logger.warning("Google Drive credentials not found for user: %s", userid)
            _cached["profile"][userid] = ""
            return ""

        user_repository = UserRepository()
        folder_id = user_repository.fetch_drive_folder_id(userid)
        if not folder_id:
            logger.warning("Google Drive folder ID not found for user: %s", userid)
            _cached["profile"][userid] = ""
            return ""

        drive_handler = GoogleDriveHandler(credentials=credentials, folder_id=folder_id)
        user_profile = get_profile_from_drive(drive_handler)
        if user_profile and "content" in user_profile:
            _cached["profile"][userid] = user_profile["content"]
        else:
            logger.error("Failed to get profile content, using empty profile")
            _cached["profile"][userid] = ""
    return _cached["profile"].get(userid, "")


def get_user_digest(userid: str) -> str:
    """キャッシュされたユーザダイジェスト情報を取得、なければGoogle Driveから取得"""
    global _cached
    if userid not in _cached["digest"]:
        logger.info(f"Fetching user digest from Google Drive as it is not cached: {userid}")
        from chatbot.database.repositories import UserRepository
        from chatbot.utils.google_auth import GoogleDriveOAuthManager
        from chatbot.utils.google_drive import GoogleDriveHandler
        from chatbot.utils.google_drive_utils import get_digest_from_drive

        auth_manager = GoogleDriveOAuthManager()
        credentials = auth_manager.get_user_credentials(userid)

        if not credentials:
            logger.warning("Google Drive credentials not found for user: %s", userid)
            _cached["digest"][userid] = ""
            return ""

        user_repository = UserRepository()
        folder_id = user_repository.fetch_drive_folder_id(userid)
        if not folder_id:
            logger.warning("Google Drive folder ID not found for user: %s", userid)
            _cached["digest"][userid] = ""
            return ""

        drive_handler = GoogleDriveHandler(credentials=credentials, folder_id=folder_id)
        digest = get_digest_from_drive(drive_handler)
        if digest and "content" in digest:
            _cached["digest"][userid] = digest["content"]
        else:
            logger.error("Failed to get digest content, using empty digest")
            _cached["digest"][userid] = ""
    return _cached["digest"].get(userid, "")


@traceable(run_type="tool", name="Ensure Google Settings")
def ensure_google_settings_node(state: State) -> Command[Literal["get_profile", "get_digest", "__end__"]]:
    """Google DriveのOAuth設定とフォルダIDの有無を確認するノード"""
    return ensure_google_settings(
        userid=state["userid"],
        success_goto=["get_profile", "get_digest"],
    )


@traceable(run_type="tool", name="Get Profile")
def get_profile_node(state: State) -> Command[Literal["router"]]:
    """
    ユーザーのプロフィール情報を取得します。
    get_digest_nodeと並列実行され、両方完了後にrouterノードへファンインします。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）。
    Returns:
        Command: routerノードへの遷移＆ユーザプロフィール情報
    """
    logger.info("--- Get Profile Node ---")
    profile = get_user_profile(state["userid"])
    return Command(goto="router", update={"profile": profile})


@traceable(run_type="tool", name="Get Digest")
def get_digest_node(state: State) -> Command[Literal["router"]]:
    """
    ユーザーのダイジェスト情報を取得します。
    get_profile_nodeと並列実行され、両方完了後にrouterノードへファンインします。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）。
    Returns:
        Command: routerノードへの遷移＆ユーザダイジェスト情報
    """
    logger.info("--- Get Digest Node ---")
    digest = get_user_digest(state["userid"])
    return Command(goto="router", update={"digest": digest})


def router_node(state: State) -> Command[Literal["diary_agent", "chatbot", "spotify_agent"]]:
    """
    現在の状態に基づいて次に遷移するノードを決定します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: 次に遷移するノード。
    """
    logger.info("--- Router Node ---")

    class Router(TypedDict):
        """Worker to route to next. If no workers needed, route to FINISH."""

        next: Literal["spotify_agent", "diary_searcher", "FINISH"]

    llm = ChatOpenAI(temperature=0, model="gpt-5.1")

    agent = create_agent(
        llm,
        tools=[],
        system_prompt=ROUTER_PROMPT,
        response_format=ProviderStrategy(Router),
    )

    try:
        result = agent.invoke({"messages": state["messages"]})
        router_result = result.get("structured_response") or {}
        goto = router_result.get("next", "chatbot")
    except Exception as e:  # noqa: BLE001
        logger.error("Router agent failed: %s", e)
        goto = "chatbot"

    if goto == "FINISH":
        goto = "chatbot"
    elif goto == "diary_searcher":
        goto = "diary_agent"

    return Command(goto=goto)


async def chatbot_node(state: State) -> Command[Literal["__end__"]]:
    """
    ユーザーのメッセージに対して応答を生成します。必要に応じてWeb検索も実行します。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Chatbot Node ---")

    # プロンプトに現在時刻・プロフィール・ダイジェストを埋め込む
    system_prompt = SISTER_EDINET_PROMPT.format(
        current_datetime=get_japan_datetime(),
        user_profile=state.get("profile", ""),
        user_digest=state.get("digest", ""),
    )

    llm = ChatOpenAI(model="gpt-5.1", temperature=1.0)
    # OpenAI built-in の web_search_preview ツールを利用
    tools = [{"type": "web_search_preview"}]

    agent = create_agent(
        llm,
        tools=tools,
        system_prompt=system_prompt,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=result["messages"][-1].text)]},
    )


async def spotify_agent_node(state: State) -> Command[Literal["__end__"]]:
    """
    Spotify関連のリクエストに対してMCPツールを使って応答を生成するノード。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Spotify Agent Node ---")

    llm = ChatOpenAI(model="gpt-5.1", temperature=0.5)
    # MCPツール取得
    mcp_tools = await get_mcp_tools()
    if not mcp_tools:
        logger.error("MCP tools unavailable. Skipping Spotify agent execution.")
        fallback_message = "ごめんね。MCP サーバーに接続できなかったみたい。"
        return Command(
            goto="__end__",
            update={"messages": [AIMessage(content=fallback_message)]},
        )

    agent = create_agent(
        llm,
        tools=mcp_tools,
        system_prompt=SISTER_EDINET_SHORT_PROMPT,
    )
    content = await agent.ainvoke({"messages": state["messages"]})
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content["messages"][-1].text)]},
    )


async def diary_agent_node(state: State) -> Command[Literal["__end__"]]:
    """
    日記検索関連のリクエストに対してdiary search toolを使って応答を生成するノード。
    Args:
        state (State): LangGraphで各ノードに受け渡しされる状態（情報）
    Returns:
        Command: Endへの遷移＆AIの応答メッセージ
    """
    logger.info("--- Diary Agent Node ---")

    # プロンプトに現在日時を埋め込む
    system_prompt = SISTER_EDINET_SHORT_DIARY_PROMPT.format(
        current_datetime=get_japan_datetime(),
    )

    llm = ChatOpenAI(model="gpt-5.1", temperature=0.5)
    # 日記検索ツールを使用
    diary_tools = [diary_search_tool]
    agent = create_agent(
        llm,
        tools=diary_tools,
        system_prompt=system_prompt,
    )
    content = await agent.ainvoke({"messages": state["messages"]})
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=content["messages"][-1].text)]},
    )


class ChatbotAgent:
    RECURSION_LIMIT = 20

    def __init__(self, cached: dict | None = None, checkpointer: BaseCheckpointSaver | None = None) -> None:
        """Initialize agent with cached data"""
        global _cached
        if cached:
            # 2キーがdictで存在するように補完
            for k in ("profile", "digest"):
                if k not in cached or not isinstance(cached[k], dict):
                    cached[k] = {}
            _cached = cached

        graph_builder = StateGraph(State)
        graph_builder.add_node("ensure_google_settings", ensure_google_settings_node)
        graph_builder.add_edge(START, "ensure_google_settings")
        graph_builder.add_node("get_profile", get_profile_node)
        graph_builder.add_node("get_digest", get_digest_node)
        graph_builder.add_node("router", router_node)
        graph_builder.add_node("chatbot", chatbot_node)
        graph_builder.add_node("spotify_agent", spotify_agent_node)
        graph_builder.add_node("diary_agent", diary_agent_node)
        self.checkpointer = checkpointer
        self.graph = graph_builder.compile(checkpointer=self.checkpointer)

    def _config(self, session_id: str) -> dict:
        return {
            "recursion_limit": self.RECURSION_LIMIT,
            "configurable": {"thread_id": session_id},
        }

    async def ainvoke(self, messages: list, userid: str, session_id: str):
        return await self.graph.ainvoke(
            {"messages": messages, "userid": userid},
            self._config(session_id),
        )

    async def aresume(self, session_id: str, resume_value: str):
        return await self.graph.ainvoke(Command(resume=resume_value), self._config(session_id))

    async def astream(self, messages: list, userid: str, session_id: str):
        async for msg, metadata in self.graph.astream(
            {"messages": messages, "userid": userid},
            self._config(session_id),
            stream_mode="messages",
            # stream_mode=["messages", "values"],
        ):
            yield msg, metadata

    async def astream_updates(self, messages: list, userid: str, session_id: str):
        async for msg in self.graph.astream(
            {"messages": messages, "userid": userid},
            self._config(session_id),
            stream_mode="updates",
        ):
            yield msg

    async def has_pending_interrupt(self, session_id: str) -> bool:
        if not self.checkpointer:
            return False

        state = await self.graph.aget_state(self._config(session_id))
        return bool(getattr(state, "interrupts", None))

    def create_image(self):
        # imagesフォルダがなければ作成
        images_dir = "images"
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)

        graph_image = self.graph.get_graph(xray=True).draw_mermaid_png()
        # imagesフォルダに保存
        with open(os.path.join(images_dir, "agent_graph.png"), "wb") as f:
            f.write(graph_image)


if __name__ == "__main__":
    # 環境変数のチェック
    is_valid, missing_vars = check_environment_variables()
    if not is_valid:
        logger.error("必要な環境変数が設定されていません。アプリケーションを終了します。")
        logger.error(f"未設定の環境変数: {', '.join(missing_vars)}")
        sys.exit(1)

    # CLI 実行時はインメモリのチェックポインタを使用
    from langgraph.checkpoint.memory import MemorySaver

    agent_graph = ChatbotAgent(checkpointer=MemorySaver())

    userid = "local-user"
    session_id = uuid.uuid4().hex

    agent_graph.create_image()
    history = []

    # invoke
    # while True:
    #     user_input = input("User: ")
    #     if user_input.lower() in ["quit", "exit", "q"]:
    #         print("Goodbye!")
    #         break
    #     history.append({"type": "human", "content": user_input})

    #     response = agent_graph.invoke(messages=history, userid=userid)
    #     print("Assistant:", response)

    import asyncio

    async def main():
        while True:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            history.append({"type": "human", "content": user_input})

            # ainvoke
            # response = await agent_graph.ainvoke(messages=history, userid=userid)
            # print("Assistant:", response)
            # print("Assistant:", response["messages"][-1].content)

            # astream(stream_mode=["messages"])
            # async for msg in agent_graph.astream(messages=history, userid=userid, stream_mode="updates"):
            # print(f"msg: {msg}")
            # print("\n")
            # print(f"metadata: {metadata}")
            # if msg.content and not isinstance(msg, HumanMessage):
            # print(msg.content, end="", flush=True)

            # astream_updates
            async for msg in agent_graph.astream_updates(messages=history, userid=userid, session_id=session_id):
                print(f"msg: {msg}")
                print("\n")

            # print(event)
            # for value in event.values():
            #     if value and "messages" in value:
            #         print("Assistant:", value["messages"][-1].content)
            # history.append({"type": "assistant", "content": value["messages"][-1].content})

    asyncio.run(main())
