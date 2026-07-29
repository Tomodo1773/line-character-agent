# LINE AIキャラクターエージェント

## プロジェクト概要

LINE上で動作するAIキャラクターエージェントシステムです。テキストで送った日記を管理し、パーソナライズされた会話を提供します。

> ⚠️ **アーキテクチャ刷新中**
> 現在 [ADR-0001](./docs/adr/0001-azure-native-agent-architecture.md) で定義した Azure ネイティブ構成（LINE ゲートウェイ + Microsoft Foundry ホステッドエージェント + Cosmos DB）へ移行中です。
> 進め方とフェーズごとの完了条件は [移行計画](./docs/migration-plan.md) を参照してください。
> 本 README は移行が進むにつれて更新されます。**この時点でアプリ全体は動作しません。**

### 利用者モデル

このアプリは現時点では `DIARY_USER_ID` で指定した1人だけが使う**個人専用**です。
LINE Gateway はそれ以外の送信者をキューへ入れず、Agent と Web UI は指定した所有者の
Cosmos DB パーティションだけを参照します。

Cosmos DB のユーザー別パーティションは将来の拡張用に維持しますが、複数ユーザー化には
認証済みアカウントと LINE アカウントの連携が必要です。利用者IDはリクエストから信用せず、
その連携情報を基にサーバー側で決定する設計へ変更してから提供します。

### 主要サービス構成

- **フロントエンド**
  - LINE Messaging API（メッセージング）

- **バックエンド**
  - Foundry ホステッドエージェント（`src/agent`）
  - Azure Functions（`src/func`。LINE ゲートウェイ／ワーカー）
  - 日記閲覧 Web UI（`src/webui`。Azure Container Apps Express。読み取り専用）

- **データベース・ストレージ**
  - Azure Cosmos DB（日記エントリのベクトル検索、ユーザー情報）

- **監視・管理**
  - Application Insights（アプリケーション監視）
  - Azure Key Vault（シークレット管理）

## 構成図

![構成図](./images/system-architecture.png)

※ 上図は刷新前の構成です。目指す最終形は ADR-0001 の構成図を参照してください。

## 主な機能

### 1. パーソナライズされた会話

- 幼馴染のお姉さん風キャラクターとしての応答

### 2. エージェント機能

- **Web検索**: Foundry Toolbox の Web Search を MCP 経由で利用した最新情報の取得
- **日記検索**: ベクトル化による過去日記の検索・RAG機能
- **ダイジェスト集約**: 毎月1日に Foundry Routine が起動し、前月の日次要約を月次へまとめ直す

## 技術スタック

### フロントエンド

- LINE Messaging API

### バックエンド

- Python 3.13
- Microsoft Agent Framework（Foundry ホステッドエージェント）
- Azure Functions

### AI・検索

- Microsoft Foundry（モデル・Toolbox の Web Search・Routine）
- Azure Cosmos DB（ベクトル検索）

### Azure Services

- Azure Functions
- Azure Cosmos DB
- Azure Key Vault
- Application Insights

### 開発・デプロイ

- Docker（ストレージエミュレータ用）
- Azure Developer CLI（azd）
- Bicep（Infrastructure as Code）
- uv（パッケージ管理）
- sfw（Socket Firewall Free）

## 事前準備

### 必要なアカウント・リソース

- Azureサブスクリプション
- LINE Developersチャンネル
- Microsoft Foundry が使えるリージョン（モデル・Toolbox・Routine を同じプロジェクトに置く）

## インストール・デプロイ

デプロイ定義の正本は `azure.yaml` と `infra/` の Bicep です。CI もローカルもこの2つを使い、同じ内容をデプロイします。

### 必要なツール

`azd` / `az` / `uv` / `rsync`。`azd` の Foundry 拡張（`azure.ai.agents`）は `azure.yaml` の `requiredVersions` に沿って導入されます。

### 事前に設定する値

Azure から導き出せない入力だけを `azd env set` で設定します。Functions のアプリ設定や Foundry のエンドポイントは Bicep が Azure のリソースから直接組み立てるので、ここには書きません。

```bash
azd env new <環境名>
azd env set AZURE_COSMOSDB_NAME <既存の Cosmos DB アカウント名>
azd env set AZURE_COSMOSDB_RG <その リソースグループ>
azd env set AZURE_KEYVAULT_NAME <既存の Key Vault 名>
azd env set AZURE_KEYVAULT_RG <その リソースグループ>
azd env set DIARY_USER_ID <日記の持ち主の LINE ユーザ ID>
```

LINE のチャネルシークレットとアクセストークンは、事前に Key Vault へ `LINE-CHANNEL-SECRET` / `LINE-CHANNEL-ACCESS-TOKEN` の名前で登録しておきます。

### 初回構築

Hosted Agent の Entra エージェント ID は「エージェントをデプロイして初めて存在する」のに、その ID がないと Bicep が Cosmos DB のロールを割り当てられません。この循環依存を切るためだけの補助スクリプトを、初回だけ手で流します。

```bash
AZURE_ENV_NAME=<環境名> ./scripts/bootstrap-azure.sh
```

`azd provision` → `azd deploy agent` → エージェント ID の取得と `azd env set` → `azd provision`（2回目）→ `azd deploy func` の順に進みます。エージェント ID の自動取得に失敗したときは、Azure ポータルの Foundry プロジェクトの [概要] > [JSON ビュー] で `principalId` を確認し、`AZURE_AI_AGENT_PRINCIPAL_ID=<値>` を付けて再実行してください。

最後に表示される Webhook URL を LINE Developers コンソールに設定すると、LINE から会話できるようになります。

### 継続デプロイ

`main` への push で [`.github/workflows/deploy.yml`](./.github/workflows/deploy.yml) が動きます。1ワークフロー・1ジョブで、Azure 認証と azd 環境の設定を共有したうえで、変更のあったものだけをデプロイします。

| 変更 | 実行される azd コマンド |
|------|------------------------|
| `infra/**` | `azd provision` → `azd deploy agent` → `azd deploy func` |
| `src/agent/**` | `azd deploy agent` |
| `src/func/**` | `azd deploy func` |
| `azure.yaml` | `azd provision` → `azd deploy agent` → `azd deploy func` |

いずれの場合も先に `azd env refresh` で Bicep の output を取り直します。CI の作業ディレクトリには azd 環境が残らないため、これをしないと `AZURE_AI_AGENT_PRINCIPAL_ID` が空のまま provision され、Agent の Cosmos DB へのロール割り当てが消えてしまうためです。

GitHub Variables には OIDC の識別子（`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID`）、azd 環境の識別子（`AZURE_ENV_NAME` / `AZURE_LOCATION`）、そして上の「事前に設定する値」と同じ5つを登録します。

### PR の品質ゲート

`main` への PR で [`.github/workflows/test.yml`](./.github/workflows/test.yml) が動きます。変更のあった対象だけを実行します。

| 変更 | 実行される内容 |
|------|----------------|
| `src/agent/**` / `src/func/**` / `src/webui/**` | `sfw uv sync --locked` → ruff check → ruff format check → pytest |
| `infra/**`、`azure.yaml` | `az bicep build`（構文・型・参照エラーと AVM モジュールの解決を確認） |
| `src/webui/**` | Web UI の Docker ビルド |

Foundry Evaluations（[`eval_agent.yml`](./.github/workflows/eval_agent.yml)）と実デプロイは、外部環境・料金・結果の安定性を把握するまで手動実行のままにしています。手動評価を運用して信頼できる評価項目が固まった時点で、その項目だけ CI へ昇格させるかを別途判断します。

### Bicep と AVM

標準的なリソースは [Azure Verified Modules](https://azure.github.io/Azure-Verified-Modules/) を使い、**バージョンを固定**しています（`br/public:avm/res/...:x.y.z`）。

| リソース | モジュール |
|----------|-----------|
| Log Analytics ワークスペース | `avm/res/operational-insights/workspace:0.16.0` |
| Application Insights | `avm/res/insights/component:0.8.0` |
| Storage アカウント | `avm/res/storage/storage-account:0.33.0` |
| App Service プラン（Flex Consumption） | `avm/res/web/serverfarm:0.7.0` |
| Functions アプリ | `avm/res/web/site:0.24.0` |
| Foundry アカウントとモデルデプロイ | `avm/res/cognitive-services/account:0.17.0` |
| Cosmos DB の SQL ロール割り当て | `avm/res/document-db/database-account/sql-role-assignment:0.2.1` |

raw Bicep を残しているのは次の3つで、いずれも AVM に対応するモジュールが無いか、AVM では表現できない繋ぎです。

- **Foundry の Project と Connection**: `avm/res/cognitive-services/account` が未対応
- **既存 Key Vault への RBAC**（`keyvault-secrets-user.bicep`）: 適合する AVM が無い
- **Functions からストレージへのロール付与**（`functions.bicep` 内）: ストレージ側の AVM へ渡すとサイトとの間で循環参照になる

### Agent のデプロイ方式

Agent は ACR も Dockerfile も使わない **Direct code deploy** です。`azd deploy agent` がソースを ZIP で上げ、Foundry 側が `requirements.txt` から依存を解決します（remote build）。`requirements.txt` は `uv.lock` からの派生物なのでコミットせず、`azure.yaml` の prepackage hook が hash 付きで書き出します。

```yaml
uv export --locked --no-dev --no-emit-project --format requirements.txt -o requirements.txt
```

Foundry が管理する remote build だけがサプライチェーン方針（`sfw` 経由での依存取得）の例外です。ローカルと CI での依存取得は従来どおり `sfw uv sync --locked` を使います。

Func も Azure Functions の remote build が `requirements.txt` を読むため、同じ方法で `.azure/dist/` の中にだけ書き出します。配布ディレクトリはテスト・仮想環境・ローカルの `.env` を除いた内容になります。

### Foundry Toolbox と Routine

Toolbox（Web 検索）と Routine（毎月1日のダイジェスト集約）は、ARM のリソースではなく Foundry プロジェクト配下のオブジェクトなので Bicep では作れません。`azure.yaml` のサービスとして宣言し、`azd provision` に作らせます。ポータルでの手作業は挟みません。

| サービス名 | host | 役割 |
|-----------|------|------|
| `web-search-tools` | `azure.ai.toolbox` | Web 検索を公開する Toolbox。サービス名がそのまま Toolbox 名になる |
| `digest-rollup` | `azure.ai.routine` | 毎月1日 04:00（日本時間）に Agent を Responses API で呼ぶ |

Agent は `AZURE_AI_TOOLBOX_NAME`（= Toolbox サービス名）から MCP エンドポイント `{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{名前}/mcp?api-version=v1` を組み立て、Entra のトークンを付けて接続します。バージョンを含めない形なので、Toolbox 側で新しいバージョンを既定へ昇格させれば Agent を再デプロイせずにツール構成が入れ替わります。

Routine は呼び出し先の Agent を名前で指すため、Agent が存在しないと作れません。初回構築では `scripts/bootstrap-azure.sh` の2回目の `azd provision`（`azd deploy agent` の後）で確定します。

Web 検索は Grounding with Bing Search を使う組み込みツールです。接続の作成は要りませんが、問い合わせは Microsoft のデータ保護契約の範囲外へ出て、Bing API の従量課金がかかります。

### ダイジェストの自動集約

毎月1日 04:00（日本時間）に Routine がメインエージェントを Responses API で呼びます。旧構成の Timer Function による自動 digest 再編を引き継ぐものです。

1. `digest_read` が前月の日次要約と、今保存されている月次・年次ダイジェストを読む
2. エージェントが [`digest-rollup` スキル](./src/agent/character_agent/skills/digest-rollup/SKILL.md)の手順に従って要約の文面を組み立てる
3. `digest_save` が構造を検証して Cosmos DB の `users.digest` を更新する

前月が12月のときだけ、その年の月次をまとめて年次へ移します。

**ツールの内側から生成 LLM や別のエージェントを呼び出しません。** 要約を作るのはスキルを読んだメインエージェントの仕事で、ツールは材料の読み取りと、検証つきの書き込みだけを担います（ベクトル索引に必要な埋め込み生成のみ機械的処理として例外）。同じ手順は「ダイジェストをまとめ直して」と LINE から頼んでも動きます。

### 開発者向け情報

開発に参加される方は、以下のドキュメントを参照してください：

- [CLAUDE.md](./CLAUDE.md) - 開発コマンドと環境構築
- [ADR-0001](./docs/adr/0001-azure-native-agent-architecture.md) - 目指す最終形
- [移行計画](./docs/migration-plan.md) - フェーズ分割と完了条件

## 開発環境のセットアップ

### ローカル開発環境

各サービス（agent、func）はローカルで直接起動します。ストレージエミュレータのみDocker Composeで実行します。

#### 1. ストレージエミュレータの起動

以下のサービスがDocker Composeで提供されます：

- **azurite**: Azure Storage エミュレータ（ポート 10000-10002）

**注**: CosmosDBはクラウド上の実際のCosmosDBインスタンスを使用します。エミュレータは削除されました。

```bash
# エミュレータを起動
docker compose up -d

# ログを確認
docker compose logs -f

# 停止
docker compose down
```

#### 2. 環境変数の設定

各サービスの `.env` ファイルを作成：

```bash
cp src/agent/.env.sample src/agent/.env
cp src/func/.env.sample src/func/.env
```

`.env` ファイルを編集して必要な環境変数を設定してください。

**ローカル開発時の注意点**:
- `src/func` は Cosmos DB・Storage・Foundry にマネージド ID で接続します。ローカルでは `az login` した
  ユーザーの権限が使われるため、接続文字列やアカウントキーの設定は不要です
- LINE のチャネルシークレットとアクセストークンだけは `.env` に設定してください

#### 3. 各サービスの起動

以下の「個別サービスの開発」セクションを参照して、各サービスをローカルで起動してください。

#### 接続情報

- Cosmos DB: クラウド上のCosmosDBインスタンス（環境変数で設定）
- Azurite Blob: http://localhost:10000
- Azurite Queue: http://localhost:10001
- Azurite Table: http://localhost:10002

### 個別サービスの開発

#### Agent Service（`src/agent/`）

Foundry ホステッドエージェント本体です。日記ツールとスキルを持ち、Responses プロトコルで応答します。

```bash
cd src/agent
sfw uv sync --locked         # lockfileを検証して依存関係をインストール
azd ai agent run             # ローカル起動（ポート 8088）
uv run --locked pytest       # テスト実行
uv run --locked ruff check   # リント
uv run --locked ruff format  # フォーマット
```

#### Function Service（`src/func/`）

```bash
cd src/func
sfw uv sync --locked         # lockfileを検証して依存関係をインストール
# Azure Functions Core Tools でローカル実行
```

#### Web UI Service（`src/webui/`）

日記の一覧・月別絞り込み・本文表示ができる読み取り専用のビューアです。日記の作成・更新・日付変更・削除は LINE Agent に一本化しているため、この UI からの変更手段は持ちません。

```bash
cd src/webui
sfw uv sync --locked         # lockfileを検証して依存関係をインストール
cp .env.sample .env          # 環境変数を設定（ADMIN_USER / ADMIN_PASSWORD など）
az login                     # Cosmos DB へは自分の権限で接続する
uv run --locked uvicorn diary_admin.main:app --reload --env-file .env --port 8000
uv run --locked pytest       # テスト実行
uv run --locked ruff check . # リント
uv run --locked ruff format . # フォーマット
```

<http://localhost:8000> を開くと Basic 認証を求められます。`.env` に設定した `ADMIN_USER` / `ADMIN_PASSWORD` で入ってください。

## 日記 Web UI のデプロイ（Azure Container Apps Express）

[ADR-0001 §8](./docs/adr/0001-azure-native-agent-architecture.md) の通り、この UI だけは IaC の対象外とし、手順をここに残します。ACA Express はパブリックプレビューで仕様が動くため、Bicep に固定するより手順として書いておくほうが実態に合うという判断です。本体（LINE 経路）から独立しているので、止まってもサービスに影響はありません。

### 前提と制約（2026年7月時点）

- 対応リージョンは **West Central US と East Asia のみ**
- **シークレット管理・Key Vault 連携・マネージド ID・Easy Auth はいずれも未対応**（開発中）。そのため接続情報は環境変数に平文で載り、UI 自体の保護はアプリ側の Basic 認証で行う
- Microsoft Entra ID のアカウントが必要（個人の Microsoft アカウントでは使えない）
- HTTP のワークロードのみ。scale to zero に対応
- `containerapp` 拡張は 1.3.0b4 以降が必要

### 1. 権限を絞ったサービスプリンシパルを用意する

マネージド ID が使えないため資格情報を環境変数で渡すことになります。アカウントキーは日記以外にも届いてしまうので使わず、**日記コンテナだけに絞ったカスタムロール**を割り当てたサービスプリンシパルを使います。UI は一覧・月別絞り込み・本文表示だけの読み取り専用ビューアなので、クエリと読み取りの権限しか渡しません（資格情報が漏れても日記は一切書き換えられない状態にする）。日記の作成・更新・日付変更・削除は LINE Agent 経由でのみ行います。

```bash
# UI 専用のサービスプリンシパルを作る（--role を指定しないので Azure ロールは付かない）
az ad sp create-for-rbac --name diary-webui
# 出力の appId / password / tenant を控える
```

`role-definition.json`:

```json
{
  "RoleName": "DiaryWebUi",
  "Type": "CustomRole",
  "AssignableScopes": ["/dbs/diary/colls/entries"],
  "Permissions": [
    {
      "DataActions": [
        "Microsoft.DocumentDB/databaseAccounts/readMetadata",
        "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/executeQuery",
        "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/read"
      ]
    }
  ]
}
```

```bash
az cosmosdb sql role definition create \
  --account-name <COSMOS_ACCOUNT> --resource-group <RESOURCE_GROUP> \
  --body @role-definition.json

# --principal-id はアプリ ID ではなくサービスプリンシパルのオブジェクト ID
az cosmosdb sql role assignment create \
  --account-name <COSMOS_ACCOUNT> --resource-group <RESOURCE_GROUP> \
  --role-definition-name DiaryWebUi \
  --principal-id "$(az ad sp show --id <APP_ID> --query id -o tsv)" \
  --scope /dbs/diary/colls/entries
```

### 2. イメージをビルドする

Express のイメージ取得はマネージド ID に未対応なので、匿名かトークン（ACR の管理者ユーザー）で引ける状態にします。`az acr build` を使えばローカルのアーキテクチャに関係なく linux/amd64 でビルドされます。

```bash
cd src/webui
az acr build --registry <ACR_NAME> --image diary-webui:latest --platform linux/amd64 .
```

### 3. Express 環境とアプリを作る

```bash
az extension add --name containerapp --upgrade

az containerapp env create \
  --environment-mode express \
  --name diary-webui-env \
  --resource-group <RESOURCE_GROUP> \
  --location westcentralus \
  --logs-destination none

az containerapp create \
  --name diary-webui \
  --resource-group <RESOURCE_GROUP> \
  --environment diary-webui-env \
  --image <ACR_NAME>.azurecr.io/diary-webui:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 --max-replicas 1 \
  --registry-server <ACR_NAME>.azurecr.io \
  --registry-username <ACR_USERNAME> --registry-password <ACR_PASSWORD> \
  --env-vars \
    COSMOS_DB_ACCOUNT_URL=https://<COSMOS_ACCOUNT>.documents.azure.com:443/ \
    DIARY_USER_ID=<LINE_USER_ID> \
    ADMIN_USER=<BASIC_AUTH_USER> \
    ADMIN_PASSWORD=<BASIC_AUTH_PASSWORD> \
    AZURE_TENANT_ID=<TENANT> \
    AZURE_CLIENT_ID=<APP_ID> \
    AZURE_CLIENT_SECRET=<PASSWORD>
```

`ADMIN_PASSWORD` と `AZURE_CLIENT_SECRET` は `az containerapp show` で読める平文の環境変数です。手順1でスコープを日記コンテナに絞っているのはこのためです。Express がシークレット管理に対応したら移行してください。

### 4. 更新と確認

```bash
az acr build --registry <ACR_NAME> --image diary-webui:latest --platform linux/amd64 .
az containerapp update --name diary-webui --resource-group <RESOURCE_GROUP> \
  --image <ACR_NAME>.azurecr.io/diary-webui:latest

# 払い出された URL を確認する
az containerapp show --name diary-webui --resource-group <RESOURCE_GROUP> \
  --query properties.configuration.ingress.fqdn -o tsv
```

表示された URL をブラウザで開き、Basic 認証を通ると日記の一覧が出ます。

## プロジェクト構造

```text
line-character-agent/
├── src/
│   ├── agent/            # Foundry ホステッドエージェント（Microsoft Agent Framework）
│   │   ├── character_agent/  # エージェント定義・ツール・スキル
│   │   └── tests/        # テストコード
│   ├── func/             # Azure Functions（LINE ゲートウェイ／ワーカー）
│   └── webui/            # 日記閲覧 Web UI（FastAPI + Jinja2、ACA Express。読み取り専用）
│       ├── diary_admin/  # アプリ本体・テンプレート
│       └── tests/        # テストコード
├── docs/                 # ADR・移行計画
├── infra/                # Bicep インフラコード
├── scripts/              # 初回構築の補助スクリプト
└── images/               # ドキュメント用画像
```

## データベース構成

### ストレージ構成

- **Cosmos DB**: 日記エントリのベクトル検索とユーザー情報管理に利用します。データベース名・コンテナ名はハードコーディングされており、環境変数での設定は不要です。

## データベーススキーマ

### Cosmos DB - 日記エントリ（diary/entries）

```json
{
  "id": "uuid",
  "userId": "string",          // パーティションキー
  "date": "2025-07-11",        // ISO形式日付
  "year": 2025,                // 年（数値）
  "month": 7,                  // 月（数値）
  "day": 11,                   // 日（数値）
  "dayOfWeek": 4,              // 曜日（0=月曜, 6=日曜）
  "content": "string",         // 日記本文
  "contentVector": [0.1, ...], // 埋め込みベクトル
  "summary": "家族と映画"       // その日の日次要約（月次ダイジェストの材料）
}
```

本文・埋め込みベクトル・日次要約は同じドキュメントにあり、`diary_create` / `diary_update` が
1 回の書き込みでまとめて更新します。日記とダイジェストの二段書き込みは行いません。

`tags` と `metadata.source` は Google Drive 同期時代の名残で、エージェントが作る日記には含まれません。

### Cosmos DB - ユーザー情報（main/users）

```json
{
  "id": "line-user-id",        // ユーザーID（パーティションキー）
  "userid": "line-user-id",    // LINEユーザーID
  "conversation_id": "conv_...", // Foundry の会話ID（Worker だけが書く）
  "profile": "# プロフィール\n...", // プロフィール（Markdown、read_profile が読む）
  "digest": {                  // 月次・年次ダイジェスト（Agent だけが書く）
    "version": "3.0",
    "lastUpdated": "2026-07-28",
    "monthly": [{ "month": "2026-06", "summary": "...", "highlights": ["..."] }],
    "yearly": [{ "year": "2025", "summary": "...", "highlights": ["..."] }]
  }
}
```

ダイジェストは「日記本文 → 日次要約 → 月次要約 → 年次要約」の段階集約で作ります。日次要約は
日記ドキュメントの `summary` にあるため、`users` 側には持ちません。集約は日記本文を読み直さず、
日次要約だけから月次・年次を組み立てます。詳しくは下の「ダイジェストの自動集約」を参照してください。

このドキュメントは Worker（`conversation_id`）と Agent（`digest`）の両方が書きます。どちらも
ドキュメント全体を upsert せず、担当フィールドだけを Cosmos の Partial Document Update
（`patch_item`）で更新するため、片方の書き込みがもう片方を巻き戻すことはありません。
ドキュメントが存在しない初回だけ、先に到達した側が作成します。

プロフィールは1件だけなので、移行スクリプトは用意していません。Cosmos DB のデータエクスプローラーか
`az cosmosdb` で `users` ドキュメントに `profile` フィールドを足してください。

## リファレンス

- [Azure Developer CLI](https://learn.microsoft.com/ja-jp/azure/developer/azure-developer-cli/)
- [LINE Messaging API](https://developers.line.biz/ja/docs/messaging-api/)

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。
