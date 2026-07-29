# 評価セット

想定発話10件に対して、**ツール呼び出しの正確さ**と**キャラクター応答**を採点する。目的は合否判定ではなく、
**既定モデルと代替候補を同じ物差しで比べ、モデル入れ替えの判断材料にすること**（ADR-0001 §5・モデル選定）。

## 何を測るか

| 採点 | 実行場所 | 内容 |
|------|----------|------|
| Foundry Evaluations | Foundry（クラウド） | 組み込みのエージェント評価器 `intent_resolution` / `tool_call_accuracy` / `task_adherence` をジャッジモデルで実行する。結果は Foundry ポータルにも残る |
| ローカル照合 | ローカル | `dataset.jsonl` に書いた期待ツールと実際の呼び出しを突き合わせる。LLM を使わないのでぶれない。あわせて、期待していない書き込み系ツール（`diary_create` / `diary_update` / `diary_delete` / `diary_rename` / `digest_regenerate`）を呼んでいないかを見る |
| キャラクター応答 | ジャッジモデル | システムプロンプトを判定基準として渡し、口調・日本語の自然さ・応答としての成立を 1-5 で採点する |

## ファイル

| ファイル | 役割 |
|----------|------|
| `dataset.jsonl` | 評価データセット（1行1ケース） |
| `dataset.py` | データセットの読み込み |
| `run_eval.py` | 実行と採点のエントリポイント |
| `character.py` | キャラクター応答のジャッジ（採点基準はここ） |
| `fake_backend.py` | 評価中だけ Cosmos DB と埋め込みを差し替えるメモリ実装 |

## 準備

追加の依存はない（`sfw uv sync --locked` で入る `agent-framework-foundry` に評価機能が含まれる）。必要なのは次の3つ。

1. **Foundry プロジェクト**と、評価したいモデルのデプロイ（例: `Kimi-K2.6`、`DeepSeek-V4-Pro`）
2. **ジャッジ用のモデルデプロイ**。組み込み評価器とキャラクター採点の両方が使う。評価される側と別系統のモデル
   （例: `gpt-4.1-mini` などの推論品質が安定したモデル）を選ぶ。自己採点になるとモデル比較の意味が薄れるため、
   **比較の間はジャッジを固定する**。構造化出力（JSON Schema）に対応したモデルであること
3. **Entra 認証**。ローカルは `az login`、CI は `azd auth login`（OIDC）。`DefaultAzureCredential` がどちらも拾う

### 環境変数

| 変数 | 用途 |
|------|------|
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry プロジェクトのエンドポイント（`.env.sample` と同じ値） |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | 評価するモデル。`--model` で上書きできる |
| `EVAL_JUDGE_DEPLOYMENT_NAME` | ジャッジモデル。`--judge-model` で上書きできる |

`COSMOS_DB_ACCOUNT_URL` と `AZURE_AI_EMBEDDING_DEPLOYMENT_NAME` は評価では使わない（下記「Cosmos DB に繋がない理由」）
ため、未設定でよい。

## 実行

```bash
cd src/agent
uv run python -m evals.run_eval --judge-model gpt-4.1-mini
```

### モデルを比較する

同じデータセットに対して `--model` だけを変え、2回実行して並べる。

```bash
uv run python -m evals.run_eval --model Kimi-K2.6        --judge-model gpt-4.1-mini
uv run python -m evals.run_eval --model DeepSeek-V4-Pro  --judge-model gpt-4.1-mini
```

LLM ジャッジの点数は実行ごとに揺れるため、**1点差程度は差と見なさない**。判断が割れるときは同じコマンドを
数回流し、傾向で見る。

## 結果の見方

実行の最後にまとめが出る。

```
=== character-agent eval (Kimi-K2.6) / 10 ケース ===

[ローカル照合]
  tool_call_args_match: 8/10 合格
  no_unexpected_write: 10/10 合格
  × diary-rename: tool_call_args_match — Tool call args match: 0/1 ...

[Foundry Evaluations] status=completed
  intent_resolution: 9/10 合格
  tool_call_accuracy: 8/10 合格
  task_adherence: 9/10 合格
  レポート: https://ai.azure.com/...

[キャラクター応答] 平均 4.10 / 5.00（3 点未満 1 件）
  chat-no-tool: 3 — 丁寧すぎる言い回しが混ざる
```

- **ローカル照合**が落ちる = 期待したツールを呼んでいない、または引数が違う。ケース名から `dataset.jsonl` を引く
- **`no_unexpected_write`** が落ちる = 曖昧な依頼に対して勝手に日記を書き換えた。プロンプトかスキルの修正対象
- **Foundry Evaluations** のレポート URL から、ポータルでケースごとの判定理由を読める
- **キャラクター応答**の平均が、日本語品質の懸念（ADR-0001 リスク節）に対する数字。理由文が改善のとっかかり

## データセット

`dataset.jsonl` は1行1ケース。

```json
{"id": "diary-delete", "description": "日付を指定した削除", "turns": ["2026年7月22日の日記は消しておいて"], "expected_tools": [{"name": "diary_delete", "arguments": {"date": "2026-07-22"}}]}
```

- `turns`: 利用者の発話を順に並べる。2件あれば「宣言してから本文を送る」複数ターンの会話になり、**最後の発話への応答**が採点対象になる
- `expected_tools`: 会話全体で呼ばれてほしいツール。`arguments` は省略でき、省略すると呼ばれたことだけを見る。
  空リストは「ツールを使わずに答えるべきケース」を表す
- 日付を名指しするケースは `fake_backend.py` の固定日記（2026-07-20 〜 22）に合わせる。相対日付（「昨日」）は
  実行日に依存するため `arguments` を書かない

ケースを増やしたら `uv run pytest` を流す。ツール名の打ち間違いや ID の重複は `tests/test_evals_dataset.py` が拾う。

## Cosmos DB に繋がない理由

評価で見たいのは「依頼に対してどのツールをどう呼ぶか」であって Cosmos DB の挙動ではない。実データに向けて
走らせると削除や日付の付け替えがそのまま反映されてしまうため、`fake_backend.py` がツールの実体
（`character_agent.cosmos` / `character_agent.foundry`）だけをメモリ実装に差し替える。エージェント定義・
プロンプト・スキル・ツールのシグネチャは本番と同一のものを評価している。

固定データにすることで、モデルを入れ替えてもツールが返す内容が変わらず、**差分をモデルに帰属できる**という
効果もある。Cosmos DB そのものの動作は `tests/test_cosmos.py` の担当。

## CI

`.github/workflows/eval_agent.yml`（`Eval AGENT`）を手動実行（workflow_dispatch）する。Foundry への接続が要るため
PR では動かさない。実行時に評価するモデルとジャッジモデルを指定する。リポジトリ変数
`FOUNDRY_PROJECT_ENDPOINT` / `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` が必要で、欠けていれば起動時に失敗する。

## 補足

- 本番トレースのサンプリングによる継続評価（ADR-0001 §5）は、同じ組み込み評価器を使う
  `agent_framework.foundry.evaluate_traces` で実現できる。まずは本セットを整えることを優先し、未着手とする
- Agent Framework の評価 API は experimental であり、実行時に `ExperimentalWarning` が出る
