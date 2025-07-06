# CLAUDE.md

本ドキュメントは、本リポジトリでの開発作業におけるClaude Code (claude.ai/code) 向けのガイドラインです。

## プロジェクト概要

本プロジェクトは、Azureサービス上で構築されたLINE向けAIチャットボットであり、キャラクター型の会話AIエージェントを実現します。LangGraphによるエージェントオーケストレーションを採用し、必要に応じてWeb検索機能も提供します。以下の3つの主要コンポーネントがAzureサービスとしてデプロイされています。

1. **APIサービス** (`src/api/`) - FastAPIベースのLINE webhookハンドラおよびチャットボットエージェント
2. **Functionサービス** (`src/func/`) - AI Searchへ日記データを自動アップロードするAzure Functions
3. **MCPサービス** (`src/mcp/`) - Spotify連携用Model Context Protocolサーバー

## 開発コマンド

### APIサービス (src/api/)
- **依存関係インストール**: `cd src/api && uv sync`
- **ローカル実行**: `cd src/api && uvicorn chatbot.main:app --reload`
- **テスト実行**: `cd src/api && uv run pytest`
- **Lintチェック**: `cd src/api && uv run ruff check`
- **コード整形**: `cd src/api && uv run ruff format`

### Functionサービス (src/func/)
- **依存関係インストール**: `cd src/func && uv sync`
- **ローカル実行**: Azure Functions Core Toolsをご利用ください

### MCPサービス (src/mcp/)
- **依存関係インストール**: `cd src/mcp && uv sync`
- **テスト実行**: `cd src/mcp && uv run pytest`

### デプロイ
- **全サービスのデプロイ**: `azd up`
- **特定サービスのみデプロイ**: `azd deploy <service-name>`

## アーキテクチャに関する補足

### エージェントシステム
チャットボットはLangGraphを用いてAIエージェントを構築しており、以下のフローで動作します。
1. メッセージは`chatbot`ノードで処理されます
2. Web検索が必要な場合は`tools`ノード（Tavily）が呼び出されます
3. エージェントはchatbotとtools間で処理を繰り返し、最終的な応答を生成します

### データフロー
- LINEメッセージ → FastAPI webhook → エージェント処理 → LINE API経由で応答
- チャット履歴はAzure Cosmos DBに保存（直近10件、1時間保持）
- 日記ドキュメントは自動的にAzure AI Searchへアップロードされ、RAG用途で利用されます

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
- MCPサービスもpytestによるasync対応済み
- テストは`src/mcp/tests/`に配置
- MCPディレクトリで`pytest`コマンドによりテスト実行可能