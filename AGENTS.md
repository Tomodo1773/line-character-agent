# Repository Guidelines

## 目的と背景

このリポジトリは「キャラクター性のあるパーソナルエージェント」を自分用に育てることを第一目的としている。同時にエンジニアとして幅広い技術スタック（API設計、サーバーレス、MCP、RAG、インフラ自動化など）を体系的に学び、ベストプラクティスへ寄せていくための実験場でもある。動けばいいわけではなく、人の見られて恥ずかしくない「よいコードを書く」ことを重視する。

ユーザは作者1名だが、学習用に10~20人程度のユーザのアプリと想定する。

## 設計思想 / 技術的ゴール

よいコードかつシンプルなコードを書く。よいコードには以下の要素が含まれる。

- シンプルでこのプロジェクトを知らない人が見ても、処理を理解しやすいコード
- ベストプラクティス準拠。要件を満たすためにベストプラクティスに外れた特殊仕様をつくるときは一度思いとどまる。
- 変更容易性があるコード
- テスト容易性: 副作用を境界に押し出し、純粋関数を中心に最小構成でpytest可能。

学習として過剰設計・過剰抽象化にならないよう注意してください。複雑なコードを上述の思想に沿ってより短いコードに変えることは大歓迎です。

## コード実装時のふるまい

- 不明な仕様に対応するために、推測で分岐を増やさない。仕様がわからない場合はまずweb検索で仕様を確認し、最小限のコード量で要件を満たすことを目指す。
- 大規模な変更を行う場合でも段階的移行は不要。恐れずあるべき姿に一気に変える
- 過剰な条件分岐は複雑さの温床。必要最小限の分岐で書く。

## プロジェクト構成とモジュール

- `src/api/` FastAPI アプリ（LINE webhook、エージェント）。テストは `src/api/tests/`。
- `src/func/` Azure Functions（日記アップロード/RAG）。テストは `src/func/tests/`。
- `src/mcp/` MCP サーバー（Spotify/OpenAI 連携）。テストは `src/mcp/tests/`。
- `infra/` Bicep、`images/` 図版、`tools/` 開発ユーティリティ。

## ビルド・テスト・開発コマンド

各サービスで `uv sync` 後に以下を実行。環境変数は各 `.env.sample` を参照。

| サービス | 起動 | テスト |
|----------|------|--------|
| API | `cd src/api && uv run fastapi dev chatbot.main:app --host 0.0.0.0 --port 3100` | `uv run pytest` |
| Func | Azure Functions Core Tools を使用 | `uv run pytest` |
| MCP | Azure Functions Core Tools を使用 | `uv run pytest` |

### Python 実行時の注意

常に `uv run` を前置する。例: `uv run pytest` / `uv run python scripts/foo.py`。避ける: `python -m pytest`。理由: ロックに基づく一時環境で依存差異を吸収し再現性を確保するため。

## コーディング規約と命名

- Python 3.11、インデント4スペース、行長127（ruff 設定)。
- 命名: ファイル/関数/変数は `snake_case`、クラスは `PascalCase`。
- import 順: 標準 → サードパーティ → ローカル。原則として絶対インポート。
- 整形/Lint: ruff を使用（`pre-commit` 対応）。push 前に `pre-commit run -a`。

### Format/Lint

全サービス（api, func, mcp）で ruff によるformat/lintが利用可能。**コード修正後は必ず実行すること。**

```bash
# 各サービスディレクトリで実行
uv run ruff check --fix .  # Lint（自動修正）
uv run ruff format .       # Format
```

CI やレビューで ruff エラーがあると merge できないため、commit 前に必ず確認する。

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
