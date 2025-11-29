# Repository Guidelines

## 目的と背景

このリポジトリは「キャラクター性のあるパーソナルエージェント」を自分用に育てることを第一目的としている。同時にエンジニアとして幅広い技術スタック（API設計、サーバーレス、MCP、RAG、インフラ自動化など）を体系的に学び、ベストプラクティスへ寄せていくための実験場でもある。単なる個人スクリプトではなく、将来的に複数ユーザーへ公開しても破綻しない水準の構成・分離・抽象化を意識している。

## 設計思想 / 技術的ゴール

- ベストプラクティス準拠: 冗長/スパゲッティ回避、依存方向の明確化、単一責任、疎結合。
- 可読性: 1ファイル・1責務を徹底し、暗黙のグローバル状態を排除。
- 変更容易性: 機能追加時に既存コードの広範な改変を避け、境界（インターフェース）を明示。
- テスト容易性: 副作用を境界に押し出し、純粋関数を中心に最小構成でpytest可能。
- 移植性/多ユーザー対応: 環境変数・資格情報・外部サービス依存を明示的に分離し、横展開時の再利用性確保。

## 変更戦略

現状の実利用者は作者1名であり、レガシー互換性維持よりも学習価値と構造最適化を優先する。必要であれば抜本的リファクタリング（ディレクトリ再編成、インターフェース刷新、ストレージ層差し替え等）を躊躇しない。段階的遷移のための場当たり的ラッパや互換ブリッジは極力作らず、一度でクリーンな方向へ移す。過渡期の一時的ハックはPRコメントで明示し短期間で除去する方針。

## プロジェクト構成とモジュール

- `src/api/` FastAPI アプリ（LINE webhook、エージェント）。テストは `src/api/tests/`。
- `src/func/` Azure Functions（日記アップロード/RAG）。テストは `src/func/tests/`。
- `src/mcp/` MCP サーバー（Spotify/OpenAI 連携）。テストは `src/mcp/tests/`。
- `infra/` Bicep、`images/` 図版、`tools/` 開発ユーティリティ。

## ビルド・テスト・開発コマンド

- API: `cd src/api && uv sync && uvicorn chatbot.main:app --reload`
- API テスト/静的解析: `uv run pytest`、`uv run ruff check`、`uv run ruff format`
- Func: `cd src/func && uv sync`（実行は Azure Functions Core Tools を使用）
- MCP: `cd src/mcp && uv sync && uv run pytest`
- 共通: 各サービスで `uv sync`。環境変数は各 `.env.sample` を参照。

### Python 実行時の注意

常に `uv run` を前置する。例: `uv run pytest` / `uv run python scripts/foo.py`。避ける: `python -m pytest`。理由: ロックに基づく一時環境で依存差異を吸収し再現性を確保するため。

## コーディング規約と命名

- Python 3.11、インデント4スペース、行長127（ruff 設定)。
- 命名: ファイル/関数/変数は `snake_case`、クラスは `PascalCase`。
- import 順: 標準 → サードパーティ → ローカル。原則として絶対インポート。
- 整形/Lint: ruff を使用（`pre-commit` 対応）。push 前に `pre-commit run -a`。

## 実装方針

- 仕様を確認してから実装する。推測で分岐を増やさない。
- 変更する時は新しい方法に完全移行する。「失敗したら古い方法」のようなフォールバックは書かない。
- 過剰な条件分岐は複雑さの温床。必要最小限の分岐で書く。

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

## 環境変数追加時の注意

- 追加時は「設定モジュール定義」→「`.env.sample` 追記」→「`infra/main.bicep` の該当サービス `appSettings` へキー追加」→「PR に用途記載」の4ステップ。
- Key Vault シークレットは事前登録の上 `@Microsoft.KeyVault(SecretUri=...)` 形式で main.bicep に書く。Cosmos/Storage の接続情報は各 service module が自動 union するため重複定義しない。
- ランタイム側で散発的に `os.environ.get` を書かず集中ファイル（API は `utils/config.py`）で一括検証する方針。Functions/MCP は今後統合予定。
- main.bicep への追加漏れは本番起動時クラッシュ (503) に直結するので PR レビューで `main.bicep` と `.env.sample` の両方を必ず確認する。

例: 新しい OAuth シークレット追加なら Key Vault 登録 → main.bicep appSettings に参照式 → config 定義 → `.env.sample` 追記 → PR に "env: XXX 追加"。
