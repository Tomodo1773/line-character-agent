# Repository Guidelines

## プロジェクト構成とモジュール

- `src/api/` FastAPI アプリ（LINE webhook、エージェント）。テストは `src/api/tests/`。
- `src/func/` Azure Functions（日記アップロード/RAG）。テストは `src/func/tests/`。
- `src/mcp/` MCP サーバー（Spotify/Perplexity 連携）。テストは `src/mcp/tests/`。
- `infra/` Bicep、`images/` 図版、`tools/` 開発ユーティリティ。

## ビルド・テスト・開発コマンド

- API: `cd src/api && uv sync && uvicorn chatbot.main:app --reload`
- API テスト/静的解析: `uv run pytest`、`uv run ruff check`、`uv run ruff format`
- Func: `cd src/func && uv sync`（実行は Azure Functions Core Tools を使用）
- MCP: `cd src/mcp && uv sync && uv run pytest`
- 共通: 各サービスで `uv sync`。環境変数は各 `.env.sample` を参照。

## コーディング規約と命名

- Python 3.11、インデント4スペース、行長127（ruff 設定）。
- 命名: ファイル/関数/変数は `snake_case`、クラスは `PascalCase`。
- import 順: 標準 → サードパーティ → ローカル。原則として絶対インポート。
- 整形/Lint: ruff を使用（`pre-commit` 対応）。push 前に `pre-commit run -a`。

## テスト方針

- フレームワーク: pytest（必要に応じて pytest-asyncio）。
- 置き場/命名: `src/*/tests/`、ファイルは `test_*.py`、関数は `test_*`。
- 外部依存: 必須環境変数が無い場合は `pytest.skip` を使用（MCP テスト参照）。
- 実行: 各サービスディレクトリで `uv run pytest`。小さく独立したユニットテストを重視。

## コミット・PR ガイドライン

- コミット: Conventional Commits（例: `feat(api): add diary route`、`fix(func): handle 404`）。
- PR: 簡潔なタイトル、変更概要、関連 Issue（例: `Closes #123`）、テスト証跡（ログ/コマンド等）、必要に応じてドキュメント更新。ruff/テスト/pre-commit を通過させること。

## セキュリティと構成

- 秘密情報はコミットしない。ローカルは `.env`、クラウドは Azure Key Vault を使用。
- 必要サービス: LINE、Cosmos DB、Google Drive、Spotify、OpenAI/Azure OpenAI（詳細は `README.md`）。
- 環境変数は各サービスの `.env.sample` で確認。

## エージェント固有の注意

- 入口: `src/api/chatbot/main.py`。エージェントグラフは `src/api/chatbot/agent/`。
- ルータ/ツールは小さく分割し、型付けした純粋関数を優先。
