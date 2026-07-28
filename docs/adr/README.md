# Architecture Decision Records (ADR)

このディレクトリには、アーキテクチャ上の意思決定とその背景を記録する。

## 運用ルール

- ファイル名は `NNNN-英語のkebab-case.md`（例: `0001-azure-native-agent-architecture.md`）。番号は連番で採番する。
- 一度マージした ADR は書き換えず、決定を覆す場合は新しい ADR を起票して旧 ADR のステータスを `Superseded by ADR-NNNN` に更新する。
- ステータスは `Proposed` / `Accepted` / `Superseded` / `Deprecated` のいずれか。
- 「なぜそう決めたか」と「なぜ他を選ばなかったか」を残すことを目的とする。実装手順書ではない。

## 一覧

| No. | タイトル | ステータス |
|-----|----------|-----------|
| [0001](./0001-azure-native-agent-architecture.md) | Azure ネイティブなエージェント基盤への刷新 | Proposed |
