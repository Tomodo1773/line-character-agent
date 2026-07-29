#!/usr/bin/env bash
set -euo pipefail

echo "source /usr/share/bash-completion/completions/git" >> ~/.bashrc

# host .gitconfig を include で取り込む
HOST_GITCONFIG_PATH=${HOST_GITCONFIG_PATH:-"$HOME/.gitconfig_host"}
if [[ -f "$HOST_GITCONFIG_PATH" ]]; then
  existing_paths=$(git config --global --get-all include.path 2>/dev/null || true)
  if ! grep -Fxq "$HOST_GITCONFIG_PATH" <<<"$existing_paths"; then
    git config --global --add include.path "$HOST_GITCONFIG_PATH"
  fi
fi

git config --global devcontainers-theme.hide-status 1
git config --global codespaces-theme.hide-status 1

# 全サービスを Python 3.13 で揃える（Foundry Direct code deploy と Azure Functions
# Flex Consumption の双方が安定して使えるバージョン）。
uv python install 3.13

(cd src/agent && uv sync) || true
(cd src/func && uv sync) || true
(cd src/webui && uv sync) || true
uv tool install pre-commit
pre-commit install

npm install -g @anthropic-ai/claude-code
