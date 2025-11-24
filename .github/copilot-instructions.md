# line-character-agent の Copilot インストラクション

## プロジェクト概要

本リポジトリは、Azureサービス上で構築されたLINE連携AIキャラクターエージェントシステムです。主な機能は以下の通りです：
- マルチチャネル対応（LINE Messaging API、OpenAI互換API）
- AI音声認識による音声日記機能
- LangGraphベースのマルチエージェントオーケストレーション
- Spotify（MCP経由）、Google Drive、Cosmos DBとの連携

### サービスアーキテクチャ

本プロジェクトは、Azure上にデプロイされる3つの主要コンポーネントで構成されています：
1. **APIサービス** (`src/api/`) - FastAPIベースのLINE webhookハンドラおよびチャットボットエージェント
2. **Functionサービス** (`src/func/`) - Cosmos DBへ日記データをアップロードするAzure Functions
3. **MCPサービス** (`src/mcp/`) - Spotify連携用Model Context Protocolサーバー

## 技術スタック

- **言語**: Python 3.11
- **Webフレームワーク**: FastAPI with uvicorn
- **AI/ML**: LangChain, LangGraph, OpenAI
- **パッケージマネージャー**: uv（pipではありません）
- **テスト**: pytest with pytest-asyncio
- **リント/フォーマット**: ruff
- **インフラストラクチャ**: Azure（App Service、Functions、Cosmos DB、Key Vault）
- **IaC**: `infra/` 内のBicepテンプレート

## 開発コマンド

### APIサービス（`src/api/`）
```bash
cd src/api
uv sync                           # 依存関係インストール
uv add <パッケージ名>              # パッケージ追加
uvicorn chatbot.main:app --reload # ローカル実行
uv run pytest                     # テスト実行
uv run ruff check                 # リント実行
uv run ruff format                # フォーマット実行
```

### Functionサービス（`src/func/`）
```bash
cd src/func
uv sync                           # 依存関係インストール
uv add <パッケージ名>              # パッケージ追加
# ローカル実行にはAzure Functions Core Toolsを使用
uv run pytest                     # テスト実行
uv run ruff check                 # リント実行
uv run ruff format                # フォーマット実行
```

### MCPサービス（`src/mcp/`）
```bash
cd src/mcp
uv sync                           # 依存関係インストール
uv add <パッケージ名>              # パッケージ追加
uv run pytest                     # テスト実行
uv run ruff check                 # リント実行
uv run ruff format                # フォーマット実行
```

## コーディング規約

### 基本ルール
- **Pythonバージョン**: 3.11
- **インデント**: 4スペース
- **行の長さ**: 127文字（ruff設定済み）
- **命名規則**:
  - ファイル/関数/変数: `snake_case`
  - クラス: `PascalCase`
- **インポート順序**: 標準ライブラリ → サードパーティ → ローカル
- **インポートスタイル**: 絶対インポートを優先

### コード品質
- push前に `pre-commit run -a` を実行
- すべてのコードは `ruff check` および `ruff format` を通過すること
- 単一責任の原則に従う
- グローバルステートを避け、依存関係を明示的にする
- 可能な限り純粋関数を保つ

## テストガイドライン

- **フレームワーク**: pytest with pytest-asyncio
- **配置場所**: `src/*/tests/` ディレクトリ
- **命名規則**: ファイル: `test_*.py`、関数: `test_*`
- **実行方法**: 各サービスディレクトリで `uv run pytest` を実行
- **外部依存**: 必須の環境変数がない場合は `pytest.skip` を使用
- 小さく独立したユニットテストを重視

## 環境変数

### 新しい環境変数の追加
新しい環境変数を追加する際は、以下の4ステップに従ってください：
1. 設定モジュールで定義（例: `src/api/chatbot/utils/config.py`）
2. サービスディレクトリの `.env.sample` に追加
3. `infra/main.bicep` の該当サービスの `appSettings` に追加
4. PRの説明に目的を記載

### Key Vaultシークレット
- まずAzure Key Vaultにシークレットを登録
- `main.bicep` では `@Microsoft.KeyVault(SecretUri=...)` を使用して参照
- シークレットをリポジトリにコミットしない
- ローカルでは `.env` ファイル、Azureでは Key Vault を使用

### 重要な注意事項
- コード全体に `os.environ.get()` の呼び出しを散在させない
- 環境変数の検証は設定モジュールに集約する
- `main.bicep` への追加漏れは本番環境で503エラーの原因となる
- Cosmos/Storageの接続文字列はサービスモジュールが自動注入する

## アーキテクチャノート

### エージェントシステム（LangGraph）
チャットボットはLangGraphを使用してエージェントを構成しています：
1. `router` ノード: メッセージを適切なエージェントにルーティング
2. `spotify_agent` ノード: 音楽関連の操作を処理（MCP経由）
3. `diary_search` ノード: 過去の日記エントリに対するRAG検索
4. `chatbot` ノード: メイン会話ハンドラ（Web検索機能付き）

### データフロー
- LINEメッセージ → FastAPI webhook → エージェント処理 → LINE APIレスポンス
- チャット履歴はCosmos DBに保存（直近10件、1時間保持）
- 日記ドキュメントはベクトル化されてCosmos DBに保存され、RAGに使用

### 主要コンポーネント
- **ChatbotAgent** (`src/api/chatbot/agent/`) - LangGraphベースのエージェント実装
- **データベース層** (`src/api/chatbot/database/`) - Cosmos DBリポジトリとモデル
- **LINE連携** (`src/api/chatbot/utils/line.py`) - LINE Messaging APIラッパー
- **認証** (`src/api/chatbot/utils/auth.py`) - OpenAI互換エンドポイント用APIキー認証

## コミットとPRのガイドライン

### コミットメッセージ
Conventional Commits形式を使用：
- `feat(api): add diary route`
- `fix(func): handle 404 errors`
- `refactor(mcp): simplify spotify client`
- `test(api): add agent integration tests`
- `docs: update README with new features`

### プルリクエスト
- 明確で簡潔なタイトル
- 変更内容の要約
- 関連するIssueをリンク（例: `Closes #123`）
- テストの証跡を含める（ログ/コマンド）
- 必要に応じてドキュメントを更新
- すべてのチェックが通過することを確認（ruff、pytest、pre-commit）

## セキュリティのベストプラクティス

- シークレットや認証情報をコミットしない
- 本番環境のシークレットはAzure Key Vaultを使用
- `.env` ファイルはローカルに保持し、`.gitignore` に追加
- 外部入力（LINE webhook、APIリクエスト）を検証・サニタイズ
- サービスアカウントには最小権限の原則を適用

## 設計思想

本リポジトリは以下を優先します：
- **ベストプラクティスの遵守**: 明確な依存関係、単一責任、疎結合
- **可読性**: 1ファイル・1責務、暗黙のグローバルステートを排除
- **変更容易性**: 機能追加時に既存コードの広範な改変を避ける
- **テスト容易性**: 副作用を境界に押し出し、純粋関数を中心に
- **移植性**: 認証情報と外部依存の明示的な分離

### 変更戦略
本プロジェクトは単一ユーザーのため、レガシー互換性よりも学習価値と構造最適化を優先します。必要であれば包括的なリファクタリング（ディレクトリ再編成、インターフェース刷新、ストレージ層の置き換えなど）を躊躇しないでください。一時的なハックや互換性ブリッジは避け、一度でクリーンな解決策に移行してください。

## モジュール別ガイダンス

### APIサービス
- エントリーポイント: `src/api/chatbot/main.py`
- 設定: `src/api/chatbot/utils/config.py`
- データベースモデル: `src/api/chatbot/database/models.py`
- リポジトリパターン: `src/api/chatbot/database/repositories.py`

### Functionサービス
- Cosmos DBへの日記データアップロードを処理
- Azure Functionsランタイム
- pytestで非同期対応済み

### MCPサービス
- Spotify/OpenAI連携用Model Context Protocolサーバー
- APIサービスのエージェントから呼び出される
- 必須環境変数がない場合、テストはスキップされる可能性あり

## 言語とコミュニケーション

コードレビューを実行する際は、日本語で応答してください。