# ADR-0001: Azure ネイティブなエージェント基盤への刷新

- ステータス: Proposed
- 日付: 2026-07-28

## サマリ

App Service 上の LangGraph アプリという現構成を捨て、**LINE ゲートウェイ（Azure Functions）+ Microsoft Foundry ホステッドエージェント + Cosmos DB** を軸にした構成へ全面的に移行する。あわせて、音声文字起こし・Google Drive 連携・LangGraph チェックポインター・日記登録ワークフローを廃止し、**テキスト入力を単一のエージェントがツールとスキルでさばく**形に単純化する。

本 ADR は「目指す最終形」の定義のみを扱う。移行手順・作業分割は別途扱う。

## コンテキスト

### 運用上の問題

- App Service の Free (F1) SKU で運用していたが、アプリの肥大化により起動時間が伸び、最終的に起動しなくなった。実質的にサービス停止している。
- 低コスト（月1,000円程度まで）で運用を継続したい。常時起動インスタンスを前提にした構成は取りたくない。

### 設計上の問題

- **入力経路が二重化している**: 音声メッセージは `diary_workflow`（LangGraph の固定グラフ）、テキストメッセージは `character_graph`（Deep Agent）と、まったく別の処理系を通る。同じ「日記を書く」という行為が2系統に分かれている。
- **音声文字起こしの前提が変わった**: スマートフォン側で、ユーザー辞書に沿った文字起こしと整形が完結するようになった。アプリ側で文字起こしを担う必然性が失われた。
- **チェックポインターが過剰**: 会話履歴のために LangGraph の PostgreSQL チェックポインター（外部 Postgres サービス）を運用しており、接続プールのアイドル切断対策など、本質的でないコードと外部依存を抱えている。
- **Google Drive 連携が構成を複雑にしている**: 日記の保存先が Drive であるために、OAuth 認可フロー・トークン暗号化・state 管理・フォルダ ID 登録という一連の仕組みが必要になっている。日記の検索用データは結局 Cosmos DB にも入っており、実体が二重管理になっている。

### このリポジトリの位置づけ

本リポジトリは個人用エージェントを育てる場であると同時に、**Azure における AI アプリケーション構築のキャッチアップの場**でもある。2026年前半に Foundry Agent Service・Microsoft Agent Framework・Foundry Observability が相次いで GA したことで、「いま Azure で AI アプリを作るならこう組む」という形が定まった。この構成に乗ることを、刷新の評価軸のひとつとして明示的に扱う。

## 決定

### 全体構成

```mermaid
flowchart LR
    LINE[LINE Platform] -->|webhook| GW[LINE Gateway<br/>Azure Functions Flex]
    GW -->|即 200 + キュー投入| Q[Storage Queue]
    Q --> W[Queue Worker<br/>同一 Functions アプリ]
    W -->|Responses protocol<br/>conversation id| HA[Hosted Agent<br/>Microsoft Agent Framework]
    W -->|reply / push| LINE
    HA -->|モデルを明示指定| M[Foundry Models<br/>オープンウェイトモデル]
    HA -->|MCP| TB[Foundry Toolbox<br/>Web Search]
    HA -->|Managed Identity| COS[(Cosmos DB<br/>users / diary)]
    RT[Foundry Routine<br/>毎月1日] -->|Responses protocol| HA
    BK[Timer Function] --> COS
    BK --> BLOB[(Blob Storage<br/>Markdown バックアップ)]
    UI[日記 Web UI<br/>ACA Express] --> COS
    GW & W & HA -->|OpenTelemetry| OBS[Foundry Observability<br/>Application Insights]
```

#### 利用者モデル

今回の構成は、環境変数 `DIARY_USER_ID` で指定した所有者1人だけが利用する**個人専用**とする。
LINE Gateway は所有者以外のイベントをキューへ投入せず、Agent と Web UI は所有者の
Cosmos DB パーティションだけを参照する。ユーザー別のパーティション構造は、将来の拡張余地として維持する。

複数ユーザー対応は別の設計変更として扱う。Agent への利用者ID伝搬だけでは認可にならないため、
Web UI の認証済みアカウントと LINE アカウントを連携し、その対応関係からサーバー側で LINE user ID を決定する。
リクエストで指定された user ID は認可判断に使わない。

### 1. 実行基盤: ゲートウェイとエージェントの分離

LINE の webhook 受信とエージェント実行を、**キューを挟んで完全に非同期化**する。

1. **Gateway（Azure Functions / Flex Consumption）**: webhook を受信し、署名検証のうえ Storage Queue に投入して即座に 200 を返す。
2. **Queue Worker（同一 Functions アプリ）**: ローディングアニメーションを表示し、ホステッドエージェントの Responses エンドポイントを呼ぶ。
3. **返信**: reply token（受信から1分間有効）での応答を優先し、間に合わなかった場合のみ push にフォールバックする。LINE 公式アカウントのフリープランでは push が月200通に制限される一方、reply は無料かつ無制限であるため、push はフォールバック専用とする。

この分離により、**Functions とホステッドエージェントで2回コールドスタートが発生しても LINE のタイムアウトとは無関係になる**。エージェント側のコールドスタートはローディングアニメーションの表示中に吸収される。ホステッドエージェントのセッションは15分アイドルで停止するため、遅延が体感されるのは久しぶりの初回メッセージのみとなる。

副次的な効果として、現行の `BackgroundTasks` + `asyncio.run_coroutine_threadsafe` によるイベントループ共有（`src/api/chatbot/main.py`）が不要になる。

### 2. エージェント: Microsoft Agent Framework によるシングルエージェント

- エージェント本体は **Microsoft Agent Framework (MAF) 1.0** で実装し、Foundry ホステッドエージェントへデプロイする。配布方式はコンテナイメージではなく **Direct code deploy**（ソースを ZIP で上げ、Foundry 側が `requirements.txt` から remote build する）とし、コンテナレジストリを持たない。
- 日記登録ワークフローのような固定グラフは持たない。**単一のエージェントがツールとスキルを使って再帰的に判断する**構成とする。「今から昨日の日記を書く」と宣言してから本文を送る、といった対話は、スキルに手順を記述してエージェントに判断させる。
- スキルは MAF の Agent Skills 機能を用いる。ディレクトリから `SKILL.md` を発見し、システムプロンプトに一覧を広告したうえで、`load_skill` / `read_skill_resource` / `run_skill_script` により必要時に読み込む（progressive disclosure）。現行の deepagents のスキル構成をほぼそのまま移植できる。
- ツールは日記操作の一式に整理する: `diary_create` / `diary_update` / `diary_delete` / `diary_rename` / `diary_search`（ベクトル検索）/ `digest_read` / `digest_save` / `read_profile`。
- **ツールの内側から生成 LLM や別のエージェントを呼び出さない。** 文章を作るのはスキルを読んだメインエージェントの仕事で、ツールは読み取りと、検証つきの書き込みに徹する。ダイジェスト集約もこの形に従い、`digest_read` が材料（日次要約と現在の月次・年次）を読み、`digest_save` が構造を検証して Cosmos DB へ書く。ベクトル索引に必要な埋め込み生成だけは機械的処理として例外とする。
- Web 検索は Foundry Toolbox の Web Search を MCP 経由で利用する。ホステッドエージェントはエージェント定義への直接のツール追加をサポートしないため、Foundry 側のツールは Toolbox の MCP エンドポイント経由で接続する。Toolbox は ARM のリソースではないため Bicep では作れず、`azure.yaml` の `azure.ai.toolbox` サービスとして宣言して azd に作らせる。
- ダイジェストの集約は手動専用にせず、**毎月1日に Foundry Routine がメインエージェントを Responses API で呼ぶ**。旧構成の Timer Function による自動 digest 再編を引き継ぐ位置づけで、Routine も `azure.yaml` の `azure.ai.routine` サービスとして宣言する。集約の規則は `digest-rollup` スキルに置き、Routine はそのスキルを読ませる指示だけを渡す。

#### モデル選定

**Azure がホストするオープンウェイトモデルを使う。** 選定条件は次の3つ。

1. オープンウェイトであること
2. **従量課金（Pay-per-token）で利用できること** — 専有スループット（PTU）や Managed Compute は月額が本構成の前提を超えるため、モデルの性能によらず選定対象外とする
3. ツール呼び出しに対応していること

- 既定モデルは **`Kimi-K2.6`**（Moonshot AI、オープンウェイト、262k コンテキスト、ツール呼び出し対応のエージェント志向モデル）とする。Azure が直接販売しており、従量課金で利用できる。
- **モデルは用途ごとに明示的に指定し、プラットフォームによる自動選択は使わない。** 同じ入力に対して同じモデルが応答する状態を保ち、キャラクター応答の品質を評価・調整できることを優先する。
- **パートナー（Fireworks）経由のモデルより、Azure が直接販売するモデルを優先する。** 理由は3点。
  1. **従量課金の提供が短期で終了しうる**。Fireworks 経由の従量課金は15日前通知で終了する規定があり、実際に `FW-GPT-OSS-120B` / `FW-DeepSeek-V3.2` / `FW-Kimi-K2.5` / `FW-GLM-5` の従量課金は提供終了済み、`FW-GLM-5.1` と `FW-MiniMax-M2.5` も2026年8月7日に終了予定である。
  2. **リージョンが米国のみ**（Data Zone Standard の対応は East US / East US 2 / Central US / North Central US / West US / West US 3）。
  3. **Microsoft と Fireworks の間でデータが共有される**。日記という個人的な内容を扱う以上、経路に入る事業者は少ないほうがよい。
- 代替候補は `DeepSeek-V4-Pro`（Azure 直販、従量課金）。Fireworks 経由となるが `GLM-5.2`（1M コンテキスト、従量課金）も候補とし、上記のライフサイクルとデータ共有の前提を許容できる場合に限る。
- **入れ替えの判断は Foundry Evaluations の結果に基づいて行い、感覚で切り替えない。**
- **埋め込みモデルは例外**とし、現行の `text-embedding-3-small` を Foundry 経由で継続利用する。オープンウェイトの埋め込みモデルは Managed Compute（専有 GPU）が前提となりコスト条件に合わず、変更すると日記全件の再ベクトル化が発生するため、ここは実利を取る。

### 3. 状態管理: 会話履歴はプラットフォーム、アプリデータは Cosmos DB

責務を明確に分離する。

| 対象 | 保存場所 | 備考 |
|------|----------|------|
| 会話履歴 | Foundry（Responses プロトコルの conversation） | プラットフォーム管理。アプリ側に実装なし |
| ユーザー情報・現在の conversation ID・プロフィール | Cosmos DB `users` | 現行の `session_id` を conversation ID に置き換える |
| 日記本文・埋め込みベクトル | Cosmos DB `diary/entries` | 現行スキーマを踏襲 |

**LangGraph / MAF のチェックポインターは使用しない。** Responses プロトコルでホストされたエージェントは、チェックポインターを持たない場合に過去のレスポンス履歴をランタイムから注入される。会話の継続はクライアント（Worker）が conversation ID を渡すことで成立するため、アプリ側で会話状態を永続化する必要がない。これに伴い外部 Postgres サービスは解約する。

「閑話休題」による履歴リセットは、新しい conversation を作成して `users` ドキュメントの conversation ID を差し替えるだけの処理となる。

Foundry Agent Service の **Standard セットアップ（BYO Thread Storage）は採用しない**（理由は「採用しなかった選択肢」を参照）。Basic セットアップを前提とする。

### 4. データ: Cosmos DB への一本化と Google Drive の廃止

- 日記の正は Cosmos DB とする。Google Drive への保存は廃止する。
- これに伴い、**Google OAuth 関連の仕組みを全廃する**: 認可フロー、トークン暗号化、`oauth_states` コンテナ、OAuth コールバックエンドポイント、フォルダ ID 登録の対話。ユーザーは友だち追加のみで利用開始できる状態になる。
- プロフィール（現 `profile.md`）は Cosmos DB に移す。ユーザー辞書（`dictionary.md`）は音声文字起こしの廃止に伴い不要となる。
- **バックアップ**: Timer Function により、日記コンテナの内容を日次で Markdown ファイルとして Blob Storage にエクスポートする。Cosmos DB の定期バックアップに加え、人間が直接読める形式の退避先を確保する。

### 5. 可観測性: Foundry Observability への統合

- トレースは **OpenTelemetry ベースの Foundry Observability** に統一し、LangSmith の利用を終了する。
- ホステッドエージェントには Application Insights の接続文字列が自動で注入され、プロトコルライブラリが既定で OTel トレース（モデル呼び出し、ツール実行、トークン使用量）を送出する。
- Gateway / Worker（Functions）側も同一の Application Insights に接続し、W3C Trace Context により **LINE 受信からツール実行までを1本の分散トレースとして追跡できる**状態にする。
- **Foundry Evaluations** を導入する。エージェント向け評価器（intent resolution / tool call accuracy / task adherence）により「日記登録の依頼に対して正しいツールを呼べているか」を評価し、本番トレースのサンプリングによる継続評価と、CI での小規模な評価セット実行を行う。

### 6. 認証: シークレットの最小化

- ホステッドエージェントに自動発行される **Entra Agent ID** を利用し、Cosmos DB へは RBAC（マネージド ID）で接続する。アカウントキーを廃止する。
- モデル呼び出しは Foundry プロジェクトエンドポイント経由の Entra 認証とし、`OPENAI_API_KEY` を廃止する。
- 結果として Key Vault で管理するシークレットは **LINE のチャネルシークレットとアクセストークンのみ**となる。

### 7. 日記 Web UI

日記の一覧・月別絞り込み・本文表示だけを行う小規模な**読み取り専用ビューア**を用意し、**Azure Container Apps Express** にデプロイする。日記の作成・更新・日付変更・削除は LINE Agent に一本化し、UI からの変更経路は設けない。UI に渡す資格情報も日記コンテナのクエリ・読み取りだけに絞り、書き込み権限を持たせない。本体（LINE 経路）から独立しており停止しても影響がないため、プレビュー段階のサービスを試す場として適切と判断する。Express は現時点でシークレット管理が未対応のため、権限を絞った接続情報の利用と、UI 自体への簡易認証を必須とする。

### 8. IaC の方針

| 対象 | 管理方法 |
|------|----------|
| Foundry アカウント / プロジェクト / モデルデプロイ、Cosmos DB、Functions、Storage、Key Vault、Application Insights | Bicep |
| ホステッドエージェントのビルドとデプロイ、Foundry Toolbox、Foundry Routine | `azd` の AI agent 拡張（`azure.yaml`）。いずれも ARM のリソースではなく Foundry プロジェクト配下のオブジェクトのため Bicep では作れない。ポータルでの手作業には依存させない |
| 日記 Web UI（ACA Express） | IaC 対象外。手順を README に記載 |

Bicep では、標準的なリソースは **Azure Verified Modules をバージョン固定で使う**。raw Bicep を残すのは、AVM が未対応の Foundry の Project と Connection、適合するモジュールが無い既存 Key Vault への RBAC、そして AVM 同士では循環参照になる Functions からストレージへのロール付与の3つに限る。

App Service および同 Free プランは削除する。

### 廃止するもの

| 廃止対象 | 理由 |
|----------|------|
| App Service + F1 プラン（`infra/app/api.bicep`） | ホステッドエージェント + Functions へ移行 |
| LangGraph PostgreSQL チェックポインターと外部 Postgres | Responses プロトコルの履歴管理へ移行 |
| Google Drive 連携一式（`google_auth.py` / `crypto.py` / `google_drive*.py` / `drive_folder.py` / OAuth コールバック / `oauth_states` コンテナ） | Cosmos DB へ一本化 |
| 日記登録ワークフロー（`agent/diary_workflow/`） | シングルエージェント + スキルへ統合 |
| digest 再編用のツール内モデル呼び出し（旧 `digest_reorganizer` / `foundry.complete()`） | 要約を作るのはスキルを読んだメインエージェントの仕事とし、ツールは読み書きに徹する |
| 音声文字起こし（`utils/transcript.py`、音声メッセージハンドラ） | スマートフォン側へ移譲。音声受信時は案内を返すのみ |
| Drive から Cosmos DB への同期 Function | 同期元が消滅 |
| LangSmith 連携（`@traceable`、`LANGSMITH_API_KEY`） | Foundry Observability へ移行 |
| `docker-compose.yml` の postgres | チェックポインター廃止に伴い不要 |

## 採用しなかった選択肢

| 選択肢 | 不採用の理由 |
|--------|-------------|
| **Foundry Agent Service の Standard セットアップ（BYO Thread Storage）** | 会話履歴を自前の Cosmos DB に保持できるが、`enterprise_memory` データベースに専用コンテナを3つ作成し、それぞれ 1000 RU/s・合計 3000 RU/s を要求する。Cosmos DB 無料枠（1000 RU/s）では成立せず、データ主権要件を持たない個人アプリで採用する理由がない |
| **ACA Express を LINE 経路の本線に置く** | パブリックプレビューであり、対応リージョンが West Central US / East Asia のみ（日本リージョンなし）、シークレット管理・Key Vault 連携・課金体系が未整備。読み取り専用ビューアの置き場としてのみ採用する |
| **LangGraph / deepagents の継続利用** | 技術的には成立し、ホステッドエージェントもフレームワーク非依存である。ただし Azure のキャッチアップという目的に対して MAF の方が適合する。今回必要なのはシングルエージェント + ツール + スキルのみであり、deepagents のプランニングやサブエージェントは過剰装備だった |
| **Model Router によるモデルの自動選択** | 入力に応じてプラットフォームがモデルを選ぶため、同じ入力に対する応答の再現性が下がり、キャラクター応答の評価と調整がしにくくなる。コスト最適化の効果より、どのモデルで動いているかを自分で決められることを優先する。またオープンウェイトモデルを使う場合、単価が十分に低くルーティングによる節約の意義が小さい |
| **Foundry 経由で OpenAI などのプロプライエタリモデルを使う** | 動作はするが、それ自体は既存構成と変わらず学習上の新規性がない。Azure がホストするオープンウェイトモデルを選ぶことで、モデル選定・評価まで含めて Azure 上で完結させる |
| **`Qwen` シリーズ** | オープンウェイトとしては最有力の系列だが、Foundry では Qwen3 / Qwen3.5 / Qwen3.6 のいずれも **PTU（専有スループット）のみの提供**で従量課金の選択肢がない。モデルの良し悪し以前にコスト前提と両立しないため採用できない。従量課金が提供された時点で再評価する |
| **`gpt-oss-120b`** | 当初の既定候補としていたが撤回した。単価と可用性以外に積極的な選定理由がなく、英語偏重で日本語のキャラクター応答に不利。Foundry でも Fireworks 経由の従量課金提供は既に終了しており、現在のオープンウェイトの選択肢として妥当でない |
| **webhook を同期処理して直接エージェントを呼ぶ** | ゲートウェイとエージェントで2回のコールドスタートが直列し、reply token の1分制限を超えるリスクがある |
| **音声文字起こしの継続** | スマートフォン側で辞書適用込みの文字起こしが完結するようになり、アプリ側で担う価値がなくなった。入力経路を2系統に保つコストに見合わない |
| **Foundry IQ によるマネージド RAG** | Azure AI Search が前提でコストが跳ねる。日記のベクトル検索は Cosmos DB 無料枠で完結しているため現状維持とする。RAG を深掘りする際の将来テーマとして残す |
| **Voice Live / WebSocket プロトコル** | 音声入力を廃止する方針と整合しない |

## 結果

### 期待する効果

- **コード量が大幅に減る**: OAuth 一式、チェックポインター周辺、音声処理、固定ワークフローが消え、残るのは Gateway / Worker、エージェント、ツール群、バックアップのみとなる。
- **外部依存が減る**: Google Drive、外部 Postgres、LangSmith の3つの外部サービスから解放される。
- **入力経路が1本になる**: すべてテキストとしてエージェントに渡り、処理の分岐がエージェントの判断に集約される。
- **Azure の現行スタックを一通り実践できる**: MAF、ホステッドエージェント、Azure がホストするオープンウェイトモデル、Toolbox、OTel 分散トレース、継続評価、キーレス認証。

### コスト（概算・月額）

| 項目 | 概算 |
|------|------|
| ホステッドエージェント（scale-to-zero、1日数時間の稼働想定） | 数百円程度 |
| モデル利用（`Kimi-K2.6`、従量課金） | 数十〜数百円程度 |
| Azure Functions（Flex Consumption） | 無料枠内 |
| Cosmos DB | 無料枠内 |
| Blob Storage / Queue | 数十円 |

合計で月1,000円前後を見込む。あわせて外部 Postgres と LangSmith の費用が不要になる。ホステッドエージェントは稼働セッション数と割り当てリソースに比例して課金されるため、サンドボックスサイズは実測に基づき最小構成から始める。

### リスクと許容範囲

- **ホステッドエージェントは新しいサービスであり仕様変更の可能性がある**。ただしフレームワーク非依存であるため、最悪の場合は同じソースをコンテナ化して標準の Container Apps に載せ替えられる。その場合は会話履歴の管理のみ自前実装が必要になる。
- **会話セッションは30日間の非アクティブで削除される**。永続すべきデータをサンドボックスの `$HOME` に置かず、Cosmos DB に保持する設計を守ることで影響を受けない。
- **オープンウェイトモデルの日本語品質は未検証である**。キャラクター応答の自然さが最大の懸念点となる。代替候補（`DeepSeek-V4-Pro`、`GLM-5.2`）への切り替えは容易であり、判断材料を Foundry Evaluations で用意することを前提とする。品質がどうしても要件に届かない場合に限り、プロプライエタリモデルへの回帰を検討する。
- **オープンウェイトモデルの提供形態は変動が速い**。従量課金の提供終了やモデルの入れ替わりが数か月単位で起きるため、既定モデルは固定資産ではなく差し替え前提の設定値として扱う。モデル名をコードに散在させず、環境変数1か所で切り替えられる状態を維持する。
- **push メッセージの月200通制限**。reply 優先・push フォールバックの設計を維持する。バックアップ失敗通知などの能動的な通知もこの枠を消費する点に留意する。
- **ACA Express のプレビュー起因の不安定さ**。本体経路から切り離しているため、停止してもサービス影響はない。

### 実験枠として扱うもの

以下はプレビュー段階であり、本線とは切り離して並行検証する。

- **Foundry Agent Service の Memory（user / session / procedural）**: 現在プロフィールとダイジェストで手作りしている「ユーザーを記憶している状態」をプラットフォームに委ねられる可能性がある。プロフィールの Cosmos DB 移行を本線としたうえで、置き換え可能性を検証する。

## 参考

- [Hosted agents in Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Set up standard agent resources for Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/standard-agent-setup)
- [Agent Skills（Microsoft Agent Framework）](https://learn.microsoft.com/en-us/agent-framework/agents/skills)
- [Observability in Generative AI](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability)
- [Foundry Models sold directly by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
- [Understanding deployment types in Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types)
- [Fireworks models on Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models)（提供モデル一覧と従量課金の提供終了予定）
- [Azure Container Apps Express Overview (preview)](https://learn.microsoft.com/en-us/azure/container-apps/express-overview)
- [Receive messages (webhook) - LINE Developers](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)
