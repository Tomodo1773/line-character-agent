# CLAUDE.md

本ドキュメントは、本リポジトリでの開発作業におけるClaude Code (claude.ai/code) 向けのガイドラインです。

## プロジェクト概要

本プロジェクトは、Azureサービス上で構築されたLINE向けAIチャットボットであり、キャラクター型の会話AIエージェントを実現します。LangGraphによるエージェントオーケストレーションを採用し、必要に応じてWeb検索機能も提供します。以下の3つの主要コンポーネントがAzureサービスとしてデプロイされています。

1. **APIサービス** (`src/api/`) - FastAPIベースのLINE webhookハンドラおよびチャットボットエージェント
2. **Functionサービス** (`src/func/`) - Cosmos DBへ日記データを自動アップロードするAzure Functions
3. **MCPサービス** (`src/mcp/`) - Spotify連携用Model Context Protocolサーバー

## 開発コマンド

### APIサービス (src/api/)

- **依存関係インストール**: `cd src/api && uv sync`
- **パッケージ追加**: `cd src/api && uv add <パッケージ名>`
- **ローカル実行**: `cd src/api && uv run fastapi run chatbot.main:app --host 0.0.0.0 --port 3100 --reload`
- **テスト実行**: `cd src/api && uv run pytest`
- **Lintチェック**: `cd src/api && uv run ruff check`
- **コード整形**: `cd src/api && uv run ruff format`

### Functionサービス (src/func/)

- **依存関係インストール**: `cd src/func && uv sync`
- **パッケージ追加**: `cd src/func && uv add <パッケージ名>`
- **ローカル実行**: Azure Functions Core Toolsをご利用ください
- **テスト実行**: `cd src/func && uv run pytest`
- **Lintチェック**: `cd src/func && uv run ruff check`
- **コード整形**: `cd src/func && uv run ruff format`

### MCPサービス (src/mcp/)

- **依存関係インストール**: `cd src/mcp && uv sync`
- **パッケージ追加**: `cd src/mcp && uv add <パッケージ名>`
- **テスト実行**: `cd src/mcp && uv run pytest`
- **Lintチェック**: `cd src/mcp && uv run ruff check`
- **コード整形**: `cd src/mcp && uv run ruff format`

### デプロイ

- **全サービスのデプロイ**: `azd up`
- **特定サービスのみデプロイ**: `azd deploy <service-name>`

## アーキテクチャに関する補足

### エージェントシステム

チャットボットはLangGraphを用いてAIエージェントを構築しており、以下のフローで動作します。

1. メッセージは`router`ノードで処理され、適切なエージェントにルーティングされます
2. Spotify操作が必要な場合は`spotify_agent`ノードが呼び出されます
3. 日記検索が必要な場合は`diary_search`ノードでRAG検索が実行されます
4. 通常の会話は`chatbot`ノードで処理され、必要に応じてWeb検索も実行されます

### データフロー

- LINEメッセージ → FastAPI webhook → エージェント処理 → LINE API経由で応答
- チャット履歴はAzure Cosmos DBに保存（直近10件、1時間保持）
- 日記ドキュメントはベクトル化されてAzure Cosmos DBに保存され、RAG検索で利用されます

### 主な構成要素

- **ChatbotAgent** (`src/api/chatbot/agent/`) - LangGraphベースのエージェント実装
- **データベース層** (`src/api/chatbot/database/`) - Cosmos DBリポジトリおよびモデル
- **LINE連携** (`src/api/chatbot/utils/line.py`) - LINE Messaging APIラッパー
- **認証** (`src/api/chatbot/utils/auth.py`) - OpenAI互換エンドポイント用APIキー認証

### 環境構成

- すべてのサービスでuvによる依存関係管理を採用
- APIサービスはローカル開発時に.envファイルを利用
- Azureへのデプロイは`infra/`ディレクトリ内のbicepテンプレートを使用

### テスト

- APIサービスはpytestによるasync対応済み
- テストは`src/api/tests/`に配置
- APIディレクトリで`pytest`コマンドによりテスト実行可能
- Functionサービスもpytestによるasync対応済み
- テストは`src/func/tests/`に配置
- Functionディレクトリで`pytest`コマンドによりテスト実行可能
- MCPサービスもpytestによるasync対応済み
- テストは`src/mcp/tests/`に配置
- MCPディレクトリで`pytest`コマンドによりテスト実行可能
