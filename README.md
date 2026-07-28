# LINE AIキャラクターエージェント

## プロジェクト概要

LINE上で動作するAIキャラクターエージェントシステムです。テキストで送った日記を管理し、パーソナライズされた会話を提供します。

> ⚠️ **アーキテクチャ刷新中**
> 現在 [ADR-0001](./docs/adr/0001-azure-native-agent-architecture.md) で定義した Azure ネイティブ構成（LINE ゲートウェイ + Microsoft Foundry ホステッドエージェント + Cosmos DB）へ移行中です。
> 進め方とフェーズごとの完了条件は [移行計画](./docs/migration-plan.md) を参照してください。
> 本 README は移行が進むにつれて更新されます。**この時点でアプリ全体は動作しません。**

### 主要サービス構成

- **フロントエンド**
  - LINE Messaging API（メッセージング）

- **バックエンド**
  - Foundry ホステッドエージェント（`src/agent`）
  - Azure Functions（`src/func`。LINE ゲートウェイ／ワーカー）

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

- **Web検索**: OpenAI APIによる最新情報取得
- **日記検索**: ベクトル化による過去日記の検索・RAG機能

## 技術スタック

### フロントエンド

- LINE Messaging API

### バックエンド

- Python 3.11
- FastAPI
- LangGraph / deepagents（Microsoft Agent Framework へ移行予定）
- Azure Functions

### AI・検索

- OpenAI（Web検索含む）
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
- OpenAI APIまたはAzure OpenAI

## インストール・デプロイ

> ⚠️ **注意**: アーキテクチャ刷新中のため、インストール・デプロイ手順は整備されていません。

### 開発者向け情報

開発に参加される方は、以下のドキュメントを参照してください：

- [CLAUDE.md](./CLAUDE.md) - 開発コマンドと環境構築
- [ADR-0001](./docs/adr/0001-azure-native-agent-architecture.md) - 目指す最終形
- [移行計画](./docs/migration-plan.md) - フェーズ分割と完了条件

## 開発環境のセットアップ

### ローカル開発環境

各サービス（api、func）はローカルで直接起動します。ストレージエミュレータのみDocker Composeで実行します。

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
cp src/api/.env.sample src/api/.env
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

#### API Service（`src/api/`）

LINE 経路は `src/func` へ移りました。ここに残っているのは Phase 5 でホステッドエージェントへ
移植する日記検索ツールだけで、起動するアプリはありません。

```bash
cd src/api
sfw uv sync                  # 依存関係インストール
uv run pytest                # テスト実行
uv run ruff check            # リント
uv run ruff format           # フォーマット
```

#### Function Service（`src/func/`）

```bash
cd src/func
sfw uv sync                  # 依存関係インストール
# Azure Functions Core Tools でローカル実行
```

## プロジェクト構造

```text
line-character-agent/
├── src/
│   ├── api/              # FastAPI アプリケーション（LINE webhook、チャットボット）
│   │   ├── chatbot/      # エージェント実装
│   │   └── tests/        # テストコード
│   └── func/             # Azure Functions
├── docs/                 # ADR・移行計画
├── infra/                # Bicep インフラコード
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
  "tags": [],                  // タグ配列
  "metadata": {
    "source": "2025年07月11日(金).md"
  }
}
```

### Cosmos DB - ユーザー情報（main/users）

```json
{
  "id": "line-user-id",        // ユーザーID（パーティションキー）
  "date": "2025-07-13T15:30:00+09:00", // 作成・更新日時（ISO形式）
  "userid": "line-user-id",    // LINEユーザーID
  "session_id": "hex",         // 会話セッションID
  "last_accessed": "2025-07-13T15:30:00+09:00" // 最終アクセス日時
}
```

## リファレンス

- [Azure Developer CLI](https://learn.microsoft.com/ja-jp/azure/developer/azure-developer-cli/)
- [LINE Messaging API](https://developers.line.biz/ja/docs/messaging-api/)

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。
