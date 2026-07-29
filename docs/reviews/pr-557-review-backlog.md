# PR #557 レビュー判断台帳

## 目的

PR #557 のレビュー指摘を、一度に修正せず論点ごとに判断・実装・検証する。
このファイルをセッション間の引き継ぎ元とし、PRを越えて残す作業だけ GitHub Issue へ昇格する。

## 進め方

1. 1セッションでは原則1項目だけ扱う。
2. まず設計方針を議論し、`決定` と `完了条件` を確定する。
3. 実装は方針決定後に行い、テスト結果を記録する。
4. PR内で直すなら Issue は作らない。別PRへ送る場合だけ Issue URL を記録する。

状態は `未検討` → `方針決定` → `実装中` → `検証済み`、または `Issue化` とする。

## 判断項目

### D1. デプロイ可能な最小構成

- 優先度: P1
- 状態: 検証済み
- 論点:
  - CIへ必須の azd 変数が渡っていない
  - Hosted Agent用ACRと出力がない
  - main workflowがAgentをデプロイしない
  - FunctionsにHosted Agent呼び出し権限がない
  - Agent identityへのCosmos権限付与が手動二段階のまま
- 主な場所:
  - `.github/workflows/provision.yml`
  - `.github/workflows/main-azure-deploy.yml`
  - `azure.yaml`
  - `infra/main.bicep`
- 決めること: 初回構築と継続デプロイを、どこまで `azd up` / CIで自動化するか
- 決定:
  - 初回構築だけ、手動起動する補助スクリプトで azd provision → Agentデプロイ → Agent principal ID取得・azd env保存 → 再provision → Funcデプロイを行う
  - 通常CIは補助スクリプトで包まず、azd を直接呼んで継続デプロイする
  - デプロイ定義の共通の正本は azure.yaml とBicepとし、初回補助スクリプトはAgent identityとCosmos RBACの循環依存解消だけを担う
  - Docker HubはHosted Agentのサポートされたイメージ配布経路として採用せず、ACRも新設しない
  - AgentはDocker方式からACR不要のDirect code deployへ変更する
  - Foundry管理のremote buildだけsfw必須ルールの例外とし、ローカルとCIでの依存取得は引き続きsfw経由とする
  - Agent・Func・Web UI・CI・開発環境のPythonを、Foundry Direct codeとAzure Functions Flex Consumptionの双方で安定利用できる3.13へ統一する
  - Python 3.14への一括更新は、Azure FunctionsでGAかつremote build対応になってから行う
  - Agentのrequirements.txtはコミットせず、azure.yamlのAgent用prepackage hookでuv.lockからhash付きで生成する
  - 継続デプロイは1ワークフロー・1ジョブとし、Azure認証とazd環境設定を共有する
  - infra変更時はazd provision、Agentまたはinfraまたはazure.yaml変更時はazd deploy agent、Funcまたはinfraまたはazure.yaml変更時はazd deploy funcを条件付きで実行する
  - FunctionsのManaged IdentityへFoundry Agent ConsumerをFoundry ProjectスコープでBicepから付与する
  - Functionsのアプリ設定はBicep内でAzureリソースから直接設定し、GitHub Variablesやazd envへ重複させない
  - Hosted Agentへ渡すAzureリソース値だけBicep outputからazure.yamlへ橋渡しし、同じ実行でprovisionを省略した場合はazd env refreshで復元する
  - GitHub VariablesにはOIDC・azd環境識別子・DIARY_USER_IDなどAzureから導出できない入力だけを置く
- 完了条件: クリーン環境で provision → Agent → Func の順にデプロイしてLINEから応答を確認し、Agentのみの変更も再provisionなしで継続デプロイできる
- 検証結果（2026-07-29）:
  - Bicep: `az bicep build --file infra/main.bicep --stdout`（成功）
  - Agent: `sfw uv sync --locked`、`uv run --locked ruff check .`、`ruff format --check .`、`pytest`（Python 3.13.12 で39件成功、既存のExperimentalWarning 1件）
  - Func: 同上（21件成功）
  - Web UI: 同上（6件成功、既存のStarletteDeprecationWarning 1件）
  - `azure.yaml` を azd の JSON スキーマで検証（エラーなし）。全ワークフローYAMLもパーサで構文確認
  - `scripts/bootstrap-azure.sh` は `bash -n` で構文確認（shellcheck は未インストールのため未実施）
  - 3サービスの `uv.lock` を Python 3.13 で再生成した結果、パッケージの追加・削除・版の変化はゼロ（agent 110・func 86・webui 45 のまま）。差分は `requires-python` と環境マーカー・wheel 選択のみで、`required-version` と `exclude-newer` による再現性の仕組みは維持している
  - 5つの論点の解消先:
    - CIへ必須のazd変数 → `.github/workflows/deploy.yml` のジョブ `env` に集約し、`azd env refresh` で Bicep output を復元
    - Hosted Agent用ACRと出力 → Direct code deploy へ変更して ACR 自体を不要にした（`azure.yaml` の `codeConfiguration`、`src/agent/Dockerfile` 削除）
    - main workflowがAgentをデプロイしない → 単一ワークフローの条件付き `azd deploy agent` を追加
    - FunctionsにHosted Agent呼び出し権限がない → `infra/core/security/foundry-agent-consumer.bicep` で Foundry Agent Consumer をプロジェクトスコープ付与
    - Agent identityへのCosmos権限付与が手動二段階 → `scripts/bootstrap-azure.sh` に集約し、`AZURE_AI_AGENT_PRINCIPAL_ID` を Bicep output にして CI でも `azd env refresh` で復元されるようにした
- 論点外だが同時に直したもの:
  - Func も remote build が `requirements.txt` を読むため、`azure.yaml` の prepackage hook で `.azure/dist/` の中にだけ書き出すようにした。これがないと `azd deploy func` が依存を入れられず、「デプロイ可能な最小構成」が成立しない
  - 同じ hook で配布ディレクトリからローカルの `.env` を除外した（従来の composite action は除外していなかった）
- 実機確認が必要な残項目（ローカルでは検証不能）:
  - クリーン環境での `scripts/bootstrap-azure.sh` 通し実行と、LINE からの応答確認（完了条件そのもの）
  - Foundry プロジェクトからエージェント ID を読む API バージョンとプロパティ名。プレビュー段階で公開スペックに未掲載のため、スクリプトは探索的に拾い、失敗時は手動指定へ誘導する作りにしてある
  - `azd deploy agent` の remote build が Python 3.13 の `requirements.txt` で通ること
  - Azure Functions Flex Consumption を `runtime.version: 3.13` へ上げた既存アプリの更新が通ること
  - `azd` が `requiredVersions.extensions` から `azure.ai.agents` 拡張を CI で自動導入すること
  - Foundry Agent Consumer ロールの割り当てが実際に Responses 呼び出しを通すこと
- Issue: なし

### D2. 単一ユーザーか複数ユーザーか

- 優先度: P1
- 状態: 検証済み
- 論点:
  - Agentの日記所有者が固定 `DIARY_USER_ID`
  - PRのHEADでは第三者も所有者の日記を操作可能
  - ローカル未コミット変更にはGatewayの単一ユーザー制限がある
  - Web UIはBasic認証の管理者1名と固定 `DIARY_USER_ID` を暗黙に対応させている
  - プロジェクト方針には10〜20人程度の利用想定がある
- 主な場所:
  - `src/agent/character_agent/config.py`
  - `src/func/line_gateway.py`
  - `src/func/line_worker.py`
  - `src/webui/diary_admin/main.py`
  - `src/webui/diary_admin/cosmos.py`
- 決めること: 個人専用として明示的に閉じるか、LINE user IDをAgentまで安全に伝搬するか
- 決定:
  - 今回は個人専用とし、Gatewayで `DIARY_USER_ID` 以外を拒否する
  - AgentとWeb UIの固定 `DIARY_USER_ID` は、この利用者モデルでは意図した設計とする
  - Cosmos DBのユーザー別パーティション構造は将来の拡張余地として維持する
  - 複数ユーザー対応は、Agentへの利用者ID伝搬だけでなく、Web UIの認証とLINEアカウントの連携を含む別Issue・別PRとする
  - 将来対応時は、認証済みアカウントとの対応からサーバー側でLINE user IDを決定し、リクエスト指定のuser IDを認可に使わない
- 完了条件:
  - 所有者以外のLINEイベントがキューへ入らない
  - AgentとWeb UIが所有者のCosmosパーティションだけを参照する
  - 個人専用であることと複数ユーザー化の前提条件が文書化されている
- 検証結果（2026-07-29）:
  - Func: `uv run --locked ruff check --fix .`、`uv run --locked ruff format .`、`uv run --locked pytest`（15件成功）
  - Agent: `uv run --locked ruff check .`、`uv run --locked pytest`（34件成功、既存のExperimentalWarning 1件）
  - Web UI: `uv run --locked ruff check --fix .`、`uv run --locked ruff format .`、`uv run --locked pytest`（8件成功、既存のStarletteDeprecationWarning 1件）
  - Gatewayは所有者外のテキスト・非テキストイベントをキュー投入も返信もしないこと、AgentとWeb UIは固定所有者のパーティションを使うことをテストで確認
- Issue: 未作成（複数ユーザー化は別Issue候補）

### D3. 会話キューの順序保証と冪等性

- 優先度: P1
- 状態: 検証済み
- 論点:
  - Storage QueueはFIFOを保証しない
  - Queue Triggerが同一ユーザーのメッセージを並列処理する
  - `webhookEventId`を保持せず再送を重複実行する
  - conversation新規作成が競合する
- 主な場所:
  - `src/func/line_gateway.py`
  - `src/func/line_worker.py`
  - `src/func/host.json`
- 決めること: 単一実行制約、ユーザー単位ロック、またはセッション対応キューのどれを採用するか
- 決定:
  - 個人専用の今回はStorage Queueを維持する
  - Queue Triggerの `batchSize` を1、Functionsの `maximumInstanceCount` を1にしてWorkerを直列化する
  - `webhookEventId` とイベントの `timestamp` をキューメッセージへ引き継ぎ、追跡できるようにする
  - 厳密なExactly Onceや分散ロックは実装せず、Service Busも導入しない
  - 将来の複数ユーザー対応ではService Bus Sessionsを使い、`SessionId` をLINE user IDとして、ユーザー間は並列・同一ユーザー内は直列にする
- 完了条件:
  - Functionsが単一インスタンスで動作し、Queue Triggerが1件ずつ処理する
  - `webhookEventId` と `timestamp` がGatewayからWorkerまで伝搬される
  - 連続する通常配送のメッセージをWorkerが並列処理しない
- 検証結果（2026-07-29）:
  - Func: `uv run --locked ruff check --fix .`、`uv run --locked ruff format .`、`uv run --locked pytest`（16件成功）
  - Bicep: `az bicep build --file infra/main.bicep --stdout`（成功）
  - `host.json` の `batchSize` を1、Flex Consumptionの `maximumInstanceCount` を1に設定
  - Microsoft LearnのQueue Trigger仕様で、`batchSize=1` は単一VM上の並列実行を排除することを確認
  - GatewayのキューペイロードからWorkerのログ・トレースまで `webhookEventId` と `timestamp` が伝搬することをテストで確認
- Issue: 未作成（複数ユーザー向けService Bus化は別Issue候補）

### D4. 日記・conversation・digestの整合性

- 優先度: P1
- 状態: 検証済み
- 論点:
  - 同日の日記を重複作成できる
  - usersドキュメント全体のread-modify-upsertで更新を失う
  - 日記とdigestの二段書き込みが部分成功する
- 主な場所:
  - `src/agent/character_agent/cosmos.py`
  - `src/agent/character_agent/tools.py`
  - `src/func/users.py`
- 決めること: 決定的ID、Cosmos PATCH/ETag、digest再生成のどこまでを採用するか
- 決定:
  - ダイジェストは「日記本文 → 日次要約 → 月次要約 → 年次要約」の段階集約とする
  - 日次要約は日記ドキュメントの `summary` フィールドへ本文と一緒に保存する
  - 日記の更新時は本文・埋め込み・日次要約を同じドキュメントで更新する
  - 月次要約は対象月の日記本文を読み直さず、日記ドキュメントの `summary` だけから生成する
  - `users.digest.daily` は持たず、直近の日次要約が必要な場合は日記ドキュメントから取得する
  - usersドキュメントは初回だけ作成し、それ以降はCosmos PATCHで担当フィールドだけを更新する
  - Functionは `conversation_id`、Agentは月次・年次の `digest` だけを更新し、ドキュメント全体をupsertしない
  - 日記IDは既存のUUIDを維持し、CosmosコンテナのUnique Key追加や決定的IDへの移行は行わない
  - AgentとWeb UIの両方で、同じ日付の日記が既にあれば作成・日付変更を拒否する
- 完了条件:
  - 日記本文・埋め込み・日次要約が同じ日記ドキュメントで更新される
  - FunctionとAgentがusersドキュメントの担当フィールドだけをPATCHする
  - LINEとWeb UIのどちらからも同日の日記を重複作成できない
- 検証結果（2026-07-29）:
  - Agent: `sfw uv run --locked ruff check .`、`ruff format .`、`pytest`（39件成功、既存のExperimentalWarning 1件）
  - Func: 同上（21件成功）
  - 日記ドキュメントへ `summary`（日次要約）を追加し、`create_entry` / `update_entry` が本文・埋め込み・日次要約を1回の書き込みで更新する
  - `save_user()` の全体upsertを廃止し、Agentは `save_digest()` で `/digest` を、Functionは `save_conversation_id()` で `/conversation_id` を `patch_item` する。ドキュメント不在時だけ作成し、作成が競合したらPATCHへフォールバックする
  - 同日重複の拒否を `tools._reject_taken_date()` の1実装へ集約し、`diary_create` と `diary_rename` の両方から呼ぶ
  - `cosmos.list_summaries()` を追加し、月次要約の生成元を日記本文ではなく `summary` にした。`IS_DEFINED(c.summary)` で移行前ドキュメントを除外する
  - `users.digest` のスキーマから `daily` を外した（version 2.0 → 3.0）。`normalize` は旧 `daily` を読み捨てる
  - Web UIはD6で読み取り専用ビューアになり日記の作成経路が存在しないため、「Web UIでも同日重複を拒否する」は構造的に達成済み
- 残課題:
  - 既存の日記ドキュメントには `summary` が無く、旧 `users.digest.daily` を読み捨てるため、移行前データの日次要約は失われる。日記本文からの `summary` バックフィルは移行計画のPhase 7（日記データの帳尻合わせ）で扱う
  - `digest_regenerate` は `users.digest.daily` 廃止に伴う最小限の追随に留めてあり、`foundry.complete()` の呼び出しが残っている。スキル化・Routine化・ツール内LLM呼び出しの廃止はD5で行う
- Issue: なし

### D5. 既存機能の継承範囲

- 優先度: P1/P2
- 状態: 検証済み
- 論点:
  - ADRと旧アプリにあるWeb検索が未実装
  - 旧Timerの自動digest再編が手動ツールへ変わった
- 主な場所:
  - `src/agent/character_agent/agent.py`
  - `src/agent/character_agent/prompts.py`
  - `docs/adr/0001-azure-native-agent-architecture.md`
- 決めること: Web検索と自動digest再編を今回のPRへ含めるか、意図的廃止としてADRを変更するか
- 決定:
  - Web検索は既存機能として今回のPRで復活させる
  - Foundry ToolboxへWeb Searchを登録し、Hosted AgentからToolboxのMCPエンドポイントへ接続する
  - Toolboxと接続設定はBicep/azdで再現可能にし、手作業のPortal設定へ依存させない
  - 最新情報を必要とする評価ケースを追加し、AgentがWeb Searchを選択して回答できることを確認する
  - digest再編は手動専用にせず、毎月1日にFoundry RoutineからHosted Agentを呼び出す
  - 月次要約は前月の日記ドキュメントの `summary` から生成し、1月は前年の月次要約を年次へ集約する
  - Routineは `azure.yaml` の `host: azure.ai.routine` サービスとして宣言し、azdで再現可能にする
  - ダイジェスト作成規則は専用の `digest-rollup` スキルへ移し、RoutineからメインAgentにそのスキルを使わせる
  - メインAgentが要約内容を作り、取得ツールは日次summary・月次digestの読み取り、保存ツールは構造検証とCosmos更新だけを担当する
  - `digest_regenerate` 内の `foundry.complete()` は廃止し、ツール内部からLLMや別Agentを再呼び出さない
  - この原則の対象は生成LLM・Agentの再呼び出しとし、ベクトル索引に必要なEmbedding生成は機械的処理として許可する
- 完了条件:
  - Hosted AgentがFoundry Toolbox経由でWeb検索できる
  - 毎月1日のRoutineが前月の日次要約を月次へ集約し、年境界では年次も更新する
  - ダイジェスト集約でツール内部から生成LLMを呼ばず、スキルを読んだメインAgentが要約を作る
  - 残す機能と廃止する機能がADR・README・実装で一致する
- 検証結果（2026-07-29）:
  - Agent: `uv run --locked ruff check .`、`ruff format --check .`、`pytest`（56件成功、既存のExperimentalWarning 1件。39件から増加）
  - Func: 同上（21件成功）、Web UI: 同上（6件成功、既存のStarletteDeprecationWarning 1件）
  - Bicep: `az bicep build --file infra/main.bicep --stdout`（成功）
  - `azure.yaml` を azd の JSON スキーマで検証（エラーなし）。`$schema` から辿れる拡張のサブスキーマ
    （`azure.ai.agent` / `azure.ai.toolbox` / `azure.ai.routine`）まで解決した状態で通している
  - Web検索: `azure.yaml` に `web-search-tools`（`host: azure.ai.toolbox`、`tools: [{type: web_search}]`）を追加し、
    Agent は `AZURE_AI_TOOLBOX_NAME` から `{project endpoint}/toolboxes/{名前}/mcp?api-version=v1` を組み立てて
    `MCPStreamableHTTPTool` で接続する。認証は `header_provider` で Entra トークン（`https://ai.azure.com/.default`）
  - digest再編: `digest_regenerate` を `digest_read`（材料の読み取り）と `digest_save`（構造検証とCosmos更新）へ分割し、
    `foundry.complete()` と `DIGEST_REORGANIZE_PROMPT` を削除した。集約規則は `skills/digest-rollup/SKILL.md` へ移した
  - Routine: `azure.yaml` に `digest-rollup`（`host: azure.ai.routine`、`cron_expression: 0 4 1 * *`、
    `time_zone: Asia/Tokyo`、`action.type: invoke_agent_responses_api`）を追加し、`uses` で Agent に依存させた
  - 評価: `web-search-latest` ケースを追加し、`digest-regenerate` ケースを `digest-rollup` へ差し替えた（10件→11件）。
    Web検索は `fake_backend` で差し替えず本物のToolboxへ繋ぐ。評価の実行自体はD7の決定どおり手動のまま
  - CI: `azure.yaml` の変更を `azd provision` の条件へ追加した（Toolbox・RoutineはBicepではなくazd側で作られるため）
- 公式ドキュメントと azd のスキーマが食い違っていた点（スキーマ側を採用）:
  - Learn の azure.yaml リファレンスは「Agentサービスの `toolboxes` にToolboxサービス名を並べる」と書くが、
    azd のスキーマでは `toolboxes` はAgentサービス内にToolbox定義そのものを書く配列（`name` + `tools` が必須）。
    独立した `azure.ai.toolbox` サービスを参照する今回は `uses` だけにした
  - Routine の azd CLI マニフェスト例は `cron` だが、`azure.yaml` のスキーマと REST/SDK は `cron_expression`。
    スキーマ側に合わせた
- 実機確認が必要な残項目（ローカルでは検証不能）:
  - `azd provision` が `azure.ai.toolbox` / `azure.ai.routine` サービスを実際に作ること。特に `infra:` を持つ
    （Bicepを使う）プロジェクトでこの2つが扱われるかは、公開ドキュメントで確認できなかった
  - ToolboxのMCPエンドポイントが公開するWeb検索ツールの**ツール名**。`web_search` と仮定して評価データセットと
    テストを書いているが、実物の名前は確認できていない。違っていれば `character_agent.agent.WEB_SEARCH_TOOL_NAME`
    の1箇所を直す
  - バージョンを含めない consumer エンドポイント（`.../toolboxes/{名前}/mcp?api-version=v1`）が既定バージョンへ
    解決されること
  - Routine のスケジュールトリガの `type` 値。how-to の表は `"schedule"` だが、azure.yaml スキーマの説明文は
    variant の例として `recurring` を挙げている。`schedule` を採用した
  - 初回構築で1回目の `azd provision` がRoutine（呼び出し先Agentが未作成）で止まらないこと
  - Grounding with Bing Search の課金と、Agentのモデルが `web_search` を選ぶかどうか（評価の手動実行で確認する）
- Issue: なし

### D6. Web UIのデータ契約

- 優先度: P1/P2
- 状態: 検証済み
- 論点:
  - Cosmosカスタムロールに `readChangeFeed` がなく一覧が403になる
  - 日付変更・削除がdigestへ反映されない
  - 日付変更で同日の日記を複数作れる
- 主な場所:
  - `README.md`
  - `src/webui/diary_admin/main.py`
  - `src/webui/diary_admin/cosmos.py`
- 決めること: Web UIが直接更新する範囲と、Agent側ドメイン処理との共有方法
- 決定:
  - Web UIは一覧・月別絞り込み・本文表示だけを提供する読み取り専用ビューワーとする
  - 日付変更・削除の画面、POSTルート、Cosmos更新処理をWeb UIから削除する
  - Web UIのサービスプリンシパルには日記コンテナのクエリ・読み取り権限だけを付与し、replace/delete権限を外す
  - 日記の作成・更新・日付変更・削除はLINE Agentだけを変更経路とする
  - 日付変更・削除の手順は `diary-maintenance` スキルへ置き、対象確認と削除前のユーザー確認を必須にする
- 完了条件:
  - Web UIからCosmos DBへの書き込み経路が存在しない
  - 読み取り専用の最小権限で一覧・絞り込み・本文表示が動く
  - 日記の変更経路がLINE Agentへ一本化されている
- 検証結果（2026-07-29）:
  - Func: `sfw uv run --locked ruff check .`、`ruff format --check .`、`pytest`（16件成功）
  - Agent: 同上（34件成功、既存のExperimentalWarning 1件）
  - Web UI: 同上（6件成功、既存のStarletteDeprecationWarning 1件。日付変更・削除のテスト2件を削除したため8件から減少）
  - Web UIから `change_date` と `delete_entry`、日付変更・削除フォーム、POSTルートを削除し、`src/webui` 配下のアプリコードとテンプレートに書き込み経路が残らないことを確認
  - READMEのカスタムロールの `dataActions` を `readMetadata`・`executeQuery`・`items/read` だけに絞り、`items/replace` と `items/delete` を外した
  - 日付変更・削除の手順を `src/agent/character_agent/skills/diary-maintenance/SKILL.md` へ置き、対象の特定と削除前のユーザー確認を必須にした
  - `prompts.py` の `_TOOL_GUIDE` へ diary-maintenance の誘導行を追加し、`diary-writing/SKILL.md` の `diary_delete`・`diary_rename` 直接呼び出しの記述を差し替えた
  - README・ADR-0001 §7の記述を読み取り専用ビューアへ揃えた
- 残課題:
  - `src/webui/pyproject.toml` の `python-multipart` はPOSTフォーム解析専用で、フォーム削除により未使用になった。除去には `uv.lock` の再生成が必要で `exclude-newer` の設定に影響しうるため、本PRでは触っていない
- Issue: なし

### D7. 品質ゲート・AVM・サプライチェーン

- 優先度: P2/P3
- 状態: 検証済み
- 論点:
  - Web UI、Bicep、Docker、実デプロイ契約がPR CIの対象外
  - 評価が本文破壊や誤ったツール実行タイミングを検出できない
  - `sfw`を可変のlatest URLから検証なしで実行する
  - `.dockerignore`がなく `.env` をremote build contextへ送り得る
  - 利用可能な主要リソースでもAVMを使っていない
- 主な場所:
  - `.github/workflows/`
  - `src/agent/evals/`
  - `src/agent/Dockerfile`
  - `src/webui/Dockerfile`
  - `infra/`
- 決めること: 今回のPRで必須とする品質ゲートと、別PRへ送る改善の境界
- 決定:
  - PRではAgent・Func・Web UIの3サービスすべてに、`sfw uv sync --locked`、ruff check、ruff format check、pytestを必須化する
  - PythonバージョンはD1で決定した3.13へ統一する
  - BicepはPRごとにコンパイルし、構文・型・参照エラーを検出する
  - Foundry Evaluationsと実デプロイは、外部環境・料金・結果の安定性を把握するまで手動実行のままにし、PRの必須ゲートにしない
  - 手動評価を運用して信頼できる評価項目が固まった後、その項目だけCIへの昇格を別途判断する
  - AgentはDirect code deployへ変更するため `src/agent/Dockerfile` を削除し、AgentのDocker buildは行わない
  - Web UIのDockerfileはSocket FirewallのバージョンとSHA-256を固定し、可変のlatestバイナリを検証なしで実行しない
  - `src/webui/.dockerignore` で `.env`、`.venv`、テスト、キャッシュなどをremote build contextから除外する
  - PR CIでWeb UIのDocker buildを実行する
  - Functionsは `avm/res/web/serverfarm` と `avm/res/web/site`、Storageと監視も対応する公式AVMへ置き換える
  - 既存Cosmos DBへのSQL Role Assignmentは対応する子AVMへ置き換える
  - FoundryはAccountとモデルデプロイだけ `avm/res/cognitive-services/account` を使い、未対応のProjectとConnectionはraw Bicepを維持する
  - 既存Key VaultへのRBACは適合するAVMがないためraw Bicepを維持する
  - AVMはバージョンを固定し、標準リソースはAVM、未対応部分と必要なglueだけraw Bicepとする
- 完了条件:
  - 3サービスのruff・pytest、Bicepコンパイル、Web UIのDocker buildがPRで成功する
  - Web UIのremote build contextへ秘密情報や不要ファイルが含まれない
  - AVM対応済みの標準リソースに独自実装が残らず、raw Bicepを残す理由が明確になっている
  - 延期した評価CI化は、手動評価の運用結果を踏まえて別途判断できる状態になっている
- 検証結果（2026-07-29）:
  - Agent: `sfw uv run --locked ruff check .`、`pytest`（56件成功、既存のExperimentalWarning 1件）
  - Func: `pytest`（21件成功）
  - Web UI: `sfw uv run --locked ruff check .`、`pytest`（6件成功、既存のStarletteDeprecationWarning 1件）
  - Bicep: `az bicep build --file infra/main.bicep --stdout`（AVM置き換え後も成功）
  - Docker: `docker build --platform linux/amd64`（成功。sfw の SHA-256 検証を含む）
  - ビルドコンテキストは `.dockerignore` により 1.02kB。`.dockerignore` が無ければ103MB（`.venv` が102MB）
  - イメージ内に `.env` 系とテストが含まれないことを `docker run` で確認（`/app` は `.venv`・`diary_admin`・`pyproject.toml`・`uv.lock` のみ）
  - 全ワークフローYAMLをパーサで構文確認
  - 5つの論点の解消先:
    - PR CIの対象外 → `.github/workflows/test.yml` を新設し、3サービスのruff・pytest、Bicepコンパイル、Web UIのDocker buildをPRで実行する。旧 `test_agent.yml` と `test_func.yml` は統合して削除した
    - 評価が検出できない → 決定どおりCIの必須ゲートにはせず手動のまま（`eval_agent.yml`）。README に昇格判断を保留している旨を記載
    - `sfw` を可変のlatest URLから実行 → `src/webui/Dockerfile` でバージョン1.15.0とSHA-256を `ARG` で固定し、`sha256sum -c` で検証してから実行する
    - `.dockerignore` が無い → `src/webui/.dockerignore` を追加し、`.env` 系・`.venv`・テスト・キャッシュを除外
    - AVMを使っていない → 下記のとおり置き換え
  - 固定したAVMのバージョン:
    - `avm/res/operational-insights/workspace:0.16.0`
    - `avm/res/insights/component:0.8.0`
    - `avm/res/storage/storage-account:0.33.0`
    - `avm/res/web/serverfarm:0.7.0`
    - `avm/res/web/site:0.24.0`
    - `avm/res/cognitive-services/account:0.17.0`
    - `avm/res/document-db/database-account/sql-role-assignment:0.2.1`
  - raw Bicepを残した理由:
    - FoundryのProjectとConnection → `avm/res/cognitive-services/account` が未対応
    - 既存Key VaultへのRBAC → 適合するAVMが無い
    - Functionsからストレージへのロール付与 → ストレージ側のAVMへ渡すとサイトとの間で循環参照になる繋ぎのため
  - 先行成果が維持されていることを、コンパイル済みARMテンプレートに対して個別に確認:
    - D3の `maximumInstanceCount: 1` が残っている
    - D1のFoundry Agent Consumer（`eed3b665-ab3a-47b6-8f48-c9382fb1dad6`）の付与が残っている
    - D1のFunctionsランタイムがpython、`runtimeVersion` の既定値が3.13
    - D1の `AZURE_AI_AGENT_PRINCIPAL_ID` のoutputとCosmosのロール割り当てが残っている
    - D1のアプリ設定がBicep内の `appsettings` として組まれている（`AzureWebJobsStorage__accountName`・`LINE_CHANNEL_SECRET`・`PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY`）
    - D5のToolboxとRoutineはBicepに混入しておらず、`azure.yaml` 側の責務のまま
  - Cosmosのロール割り当ては、AVM子モジュールへ従来と同じ `guid(account.id, principalId, roleId)` を `name` として渡し、置き換えで権限が一度落ちないようにした
  - Functionsのストレージへのロール割り当て名は、モジュール出力が使えないため `resourceId('Microsoft.Web/sites', name)` から導出した。値は従来の `functionApp.id` と同じ
- 実機確認が必要な残項目（ローカルでは検証不能）:
  - AVM置き換え後の `azd provision` が既存リソースを差分更新で通ること（特にFunctionsアプリとStorageの設定差分）
  - GitHub Actions 上での `test.yml` の初回実行（ローカルではYAML構文と各コマンド単体までしか確認できない）
- Issue: なし

## 次のセッション

D1〜D7の設計方針・実装・検証がすべて完了した。

残っているのは、各項目の「実機確認が必要な残項目」だけとなる。特にD1の完了条件（クリーン環境で
`scripts/bootstrap-azure.sh` を通し、LINEからの応答を確認）と、D5のWeb検索・Routineの動作確認は
実際のAzure環境が要るため、人間が実行して結果をここへ追記する。

PR内で扱う作業は終わったため、次はPRの仕上げ（実機確認と、その結果に応じた修正）へ移る。
