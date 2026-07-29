#!/usr/bin/env bash
#
# 初回構築だけに使う補助スクリプト。
#
# Hosted Agent の Entra エージェント ID は「エージェントをデプロイして初めて存在する」のに、
# その ID がないと Bicep が Cosmos DB のデータプレーンロールを割り当てられない、という
# 循環依存がある。この循環を切るためだけに、以下の順で流す。
#
#   1. azd provision              … Agent ID なしで基盤を作る（Cosmos は Functions の分だけ）
#   2. azd deploy agent           … Hosted Agent を Direct code deploy で作る
#   3. Agent の principal ID 取得 … Foundry プロジェクトから読み、azd 環境へ保存する
#   4. azd provision（2回目）     … 保存した ID で Cosmos のロールを割り当てる
#   5. azd deploy func            … LINE Gateway / Worker を出す
#
# Foundry Toolbox（Web 検索）と Routine（毎月1日のダイジェスト集約）は azure.yaml のサービスと
# して azd が作る。Routine は呼び出し先のエージェントを名前で指すため、エージェントが存在する
# 2回目の provision で確定する。1回目でここが通らなくても、この順に流せば最後には揃う。
#
# 2回目以降の継続デプロイでこのスクリプトは使わない。GitHub Actions の
# .github/workflows/deploy.yml が azd を直接呼ぶ。
#
# 使い方:
#   AZURE_ENV_NAME=<環境名> ./scripts/bootstrap-azure.sh
#
# 自動取得に失敗する場合は、Azure ポータルの Foundry プロジェクト > 概要 > JSON ビュー
# （最新の API バージョン）でエージェント ID を確認し、次のように渡して再実行する。
#   AZURE_AI_AGENT_PRINCIPAL_ID=<principal id> ./scripts/bootstrap-azure.sh

set -euo pipefail

cd "$(dirname "$0")/.."

# Foundry プロジェクトのエージェント ID を読むための API バージョン。
# プレビュー段階なので、必要なら環境変数で差し替えられるようにしておく。
FOUNDRY_API_VERSION="${FOUNDRY_API_VERSION:-2026-05-15-preview}"

log() {
  printf '\n==> %s\n' "$1"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "エラー: $1 が見つかりません。$2" >&2
    exit 1
  }
}

require_command azd "https://aka.ms/azd を入れてください。"
require_command az "Azure CLI を入れてください。"
require_command uv "Agent の requirements.txt 生成に使います。"
require_command rsync "Func の配布ディレクトリ作成に使います。"
require_command python3 "エージェント ID の抽出に使います。"

azd_env_get() {
  azd env get-value "$1" 2>/dev/null || true
}

# Foundry プロジェクトのリソースから、Hosted Agent が使うエージェント ID を探す。
# 未公開のエージェントはプロジェクト共通のエージェント ID を使う。プロパティ名は
# プレビュー中に変わりうるので、`principalId` を持つ agentIdentity 系の要素を拾う。
find_agent_principal_id() {
  local account="$1" project="$2" resource_group="$3" subscription="$4"
  local resource_id json
  resource_id="/subscriptions/${subscription}/resourceGroups/${resource_group}/providers/Microsoft.CognitiveServices/accounts/${account}/projects/${project}"

  json="$(az resource show --ids "$resource_id" --api-version "$FOUNDRY_API_VERSION" -o json 2>/dev/null || true)"
  [ -n "$json" ] || return 1

  printf '%s' "$json" | python3 -c '
import json
import sys

document = json.load(sys.stdin)
found = []


def walk(node, key=""):
    if isinstance(node, dict):
        principal = node.get("principalId")
        if principal and "agent" in key.lower() and "blueprint" not in key.lower():
            found.append(principal)
        for child_key, child in node.items():
            walk(child, child_key)
    elif isinstance(node, list):
        for child in node:
            walk(child, key)


walk(document)
if found:
    print(found[0])
'
}

log "azd 環境を確認します"
AZURE_ENV_NAME="${AZURE_ENV_NAME:-$(azd env get-value AZURE_ENV_NAME 2>/dev/null || true)}"
if [ -z "$AZURE_ENV_NAME" ]; then
  echo "エラー: AZURE_ENV_NAME が未設定です。AZURE_ENV_NAME=<環境名> を付けて実行してください。" >&2
  exit 1
fi
echo "環境: $AZURE_ENV_NAME"

for name in AZURE_COSMOSDB_NAME AZURE_COSMOSDB_RG AZURE_KEYVAULT_NAME AZURE_KEYVAULT_RG DIARY_USER_ID; do
  if [ -z "$(azd_env_get "$name")" ]; then
    echo "エラー: azd 環境に $name がありません。'azd env set $name <値>' で設定してください。" >&2
    exit 1
  fi
done

log "1/5 azd provision（Agent ID なし）"
azd provision --no-prompt

log "2/5 azd deploy agent"
azd deploy agent --no-prompt

log "3/5 Agent の principal ID を取得します"
AGENT_PRINCIPAL_ID="${AZURE_AI_AGENT_PRINCIPAL_ID:-}"
if [ -z "$AGENT_PRINCIPAL_ID" ]; then
  AGENT_PRINCIPAL_ID="$(find_agent_principal_id \
    "$(azd_env_get FOUNDRY_ACCOUNT_NAME)" \
    "$(azd_env_get FOUNDRY_PROJECT_NAME)" \
    "$(azd_env_get AZURE_RESOURCE_GROUP)" \
    "$(azd_env_get AZURE_SUBSCRIPTION_ID)" || true)"
fi

if [ -z "$AGENT_PRINCIPAL_ID" ]; then
  cat >&2 <<'MESSAGE'
エラー: Agent の principal ID を自動取得できませんでした。
Azure ポータルで Foundry プロジェクトを開き、[概要] > [JSON ビュー] から最新の API バージョンを選び、
エージェント ID の principalId を控えてください。そのうえで次のように再実行します。

  AZURE_AI_AGENT_PRINCIPAL_ID=<principal id> ./scripts/bootstrap-azure.sh

すでに provision と Agent のデプロイは終わっているので、再実行しても作り直しにはなりません。
MESSAGE
  exit 1
fi

echo "principal ID: $AGENT_PRINCIPAL_ID"
azd env set AZURE_AI_AGENT_PRINCIPAL_ID "$AGENT_PRINCIPAL_ID"

log "4/5 azd provision（Agent へ Cosmos のロールを付与）"
azd provision --no-prompt

log "5/5 azd deploy func"
azd deploy func --no-prompt

log "完了しました"
cat <<MESSAGE
LINE Developers コンソールの Webhook URL に次を設定してください。

  $(azd_env_get LINE_WEBHOOK_URL)

以降の継続デプロイは main への push で .github/workflows/deploy.yml が動きます。
MESSAGE
