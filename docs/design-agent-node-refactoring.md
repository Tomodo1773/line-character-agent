# エージェントノード再設計計画

## 背景と課題

現在、LangGraph のノード内部で `create_user_repository()` をグローバルキャッシュ経由で呼び出している箇所が5箇所ある。これは「図（グラフ画像）で処理を可視化したい」という動機で OAuth 設定やデータ取得をすべてノード化した結果、ノードが FastAPI の DI コンテキスト外にあるために生まれた構造的な問題である。

### 現状の問題点

1. **ノード内でのインフラ依存の自己生成**: agent ノードが `create_user_repository()` を引数なしで呼び、グローバル変数 `_users_container` に依存している。テスト困難・暗黙の結合・初期化順序の罠を生む
2. **diary_workflow での不要な interrupt**: 音声メッセージ受信時は Google Drive 保存が確定しているため、OAuth/フォルダ設定はワークフロー開始前に確認すべき。LangGraph の interrupt を使う必然性がない
3. **データ取得ノードの不要なノード化**: `get_profile` / `get_digest` は分岐も中断もなく、ノードである意味がない

### 対象ファイルと `create_user_repository()` 呼び出し箇所

| # | ファイル | 関数 | 用途 |
|---|---------|------|------|
| 1 | `agent/character_graph/nodes.py:90` | `get_user_profile()` | OAuth 認証情報 + フォルダ ID 取得 → Google Drive からプロフィール取得 |
| 2 | `agent/character_graph/nodes.py:127` | `get_user_digest()` | OAuth 認証情報 + フォルダ ID 取得 → Google Drive からダイジェスト取得 |
| 3 | `agent/services/google_settings.py:44` | `ensure_oauth_settings()` | OAuth 認証情報の有無確認 → 未設定なら interrupt |
| 4 | `agent/services/google_settings.py:83` | `ensure_folder_id_settings()` | フォルダ ID の有無確認 → 未設定なら interrupt |
| 5 | `agent/diary_workflow/workflow.py:61` | `_create_drive_handler()` | OAuth 認証情報 + フォルダ ID → GoogleDriveHandler 生成 |

---

## 現在のグラフ構造

### character_graph（テキストメッセージ）

```
START
  → ensure_oauth_settings        ← interrupt あり（ノードであるべき）
  → ensure_folder_id_settings    ← interrupt あり（ノードであるべき）
  → [get_profile, get_digest]    ← 分岐なし（ノードである必要なし）
  → router                       ← 分岐あり（ノードであるべき）
  → chatbot / spotify_agent / diary_agent → __end__
```

### diary_workflow（音声メッセージ）

```
START
  → ensure_oauth_settings_node        ← interrupt（ノードである必要なし ※後述）
  → ensure_folder_id_settings_node    ← interrupt（ノードである必要なし ※後述）
  → transcribe_diary_node
  → save_diary_node
  → generate_digest_node
  → invoke_character_comment_node → __end__
```

---

## 設計方針

### 原則: ノードにすべきもの / すべきでないもの

| ノードにすべき | ノードにすべきでない |
|--------------|-------------------|
| LangGraph の分岐・中断（interrupt）・再開（resume）に関わる処理 | 分岐も中断もない単純なデータ取得・設定チェック |
| LLM 呼び出し・ツール実行 | インフラ層（DB クライアント等）の生成 |
| グラフの可視化で意味のある処理単位 | 呼び出し元で事前に済ませられる前提条件チェック |

---

## 変更計画

### 変更 1: UserRepository を config 経由でノードに渡す

呼び出し元（`handle_text_async` / `handle_audio_async`）で生成済みの `UserRepository` を LangGraph の config に載せてノードに渡す。

**呼び出し元（main.py）:**

```python
user_repository = create_user_repository(app.state.users_container)
session = user_repository.ensure_session(userid)

# config に UserRepository を含めて渡す
response = await agent.ainvoke(
    messages=messages,
    userid=userid,
    session_id=session.session_id,
    user_repository=user_repository,
)
```

**ChatbotAgent（graph.py）:**

```python
async def ainvoke(self, messages, userid, session_id, user_repository):
    config = {
        "recursion_limit": self.RECURSION_LIMIT,
        "configurable": {
            "thread_id": session_id,
            "user_repository": user_repository,
        },
    }
    return await self.graph.ainvoke(
        {"messages": messages, "userid": userid}, config
    )
```

**ノード側（google_settings.py 等）:**

```python
def ensure_oauth_settings(state, config):
    user_repository = config["configurable"]["user_repository"]
    # グローバルキャッシュ不要
```

**効果:**
- `dependencies.py` の `_users_container` グローバルキャッシュ、`initialize_users_container()` が不要になる
- `create_user_repository()` の引数なし呼び出しが全廃される
- ノードのテストが容易になる（config にモックを渡すだけ）

### 変更 2: diary_workflow から OAuth/フォルダ設定ノードを外出し

音声受信時は Google Drive 保存が前提のため、`handle_audio_async` の冒頭で OAuth/フォルダ ID を確認する。不足していれば LINE にメッセージを返してワークフローを開始しない。

**変更前（diary_workflow 内で interrupt）:**

```
handle_audio_async
  → workflow.ainvoke(audio)
    → ensure_oauth_settings_node  ← interrupt でユーザー待ち
    → ensure_folder_id_settings_node ← interrupt でユーザー待ち
    → transcribe_diary_node
    → ...
```

**変更後（ワークフロー前にチェック）:**

```
handle_audio_async
  → OAuth 認証情報チェック（なければ LINE にメッセージ返して return）
  → フォルダ ID チェック（なければ LINE にメッセージ返して return）
  → workflow.ainvoke(audio, drive_handler)
    → transcribe_diary_node
    → save_diary_node
    → generate_digest_node
    → invoke_character_comment_node → __end__
```

**効果:**
- diary_workflow から ensure_oauth / ensure_folder_id ノードが消える
- diary_workflow が interrupt を使わなくなり、checkpointer が不要になる可能性がある（invoke_character_comment_node が内部で ChatbotAgent を呼ぶためそこは要確認）
- `_create_drive_handler()` も `handle_audio_async` 側に移動可能

**注意:**
- character_graph 側の `ensure_oauth_settings` / `ensure_folder_id_settings` はテキスト会話フロー内で interrupt → resume が必要なのでノードのまま残す
- `google_settings.py` の関数自体は character_graph 用に残るが、UserRepository は config 経由で受け取る形に変わる

### 変更 3: get_profile / get_digest をノードから外出し

`get_profile` と `get_digest` は分岐も中断もない単純なデータ取得。`router` ノードの冒頭で実行するか、`ainvoke` 前に取得して State の初期値として渡す。

**案 A: router ノードの冒頭で実行（推奨）**

```python
def router_node(state):
    userid = state["userid"]
    profile = get_user_profile(userid, config)  # ノードではなく普通の関数呼び出し
    digest = get_user_digest(userid, config)
    # ... router ロジック
```

**案 B: ainvoke 前に取得して State に渡す**

```python
profile = get_user_profile(userid, user_repository)
digest = get_user_digest(userid, user_repository)
response = await agent.ainvoke(
    messages=messages, userid=userid, profile=profile, digest=digest, ...
)
```

**効果:**
- ノード数が減りグラフがシンプルになる
- 並列実行の制御が不要になる（現状 `ensure_folder_id_settings` が `get_profile` と `get_digest` を並列で起動している）

---

## 変更後のグラフ構造（想定）

### character_graph

```
START
  → ensure_oauth_settings     ← interrupt あり（残す）
  → ensure_folder_id_settings ← interrupt あり（残す）
  → router                    ← profile/digest 取得を内包
  → chatbot / spotify_agent / diary_agent → __end__
```

### diary_workflow

```
START
  → transcribe_diary_node
  → save_diary_node
  → generate_digest_node
  → invoke_character_comment_node → __end__
```

（OAuth/フォルダチェックは handle_audio_async で実施済み）

---

## 実施順序（案）

1. **UserRepository の config 渡し** — 全ノードから `create_user_repository()` 引数なし呼び出しを除去。グローバルキャッシュ廃止
2. **diary_workflow から OAuth/フォルダノード外出し** — `handle_audio_async` に事前チェックを移動
3. **get_profile / get_digest のノード外出し** — router ノードに統合

各ステップで `uv run pytest` が通ることを確認しながら進める。
