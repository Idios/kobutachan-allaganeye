#!/usr/bin/env bash
# Local markdownlint check, mirroring CI (.github/workflows/markdownlint.yml).
#
# Usage:
#   bash scripts/check-markdownlint.sh         # check all *.md
#   bash scripts/check-markdownlint.sh --fix   # auto-fix where possible (limited rule support)
#
# CI bundles markdownlint-cli2 v0.22.1 (markdownlint v0.40.0) via
# DavidAnson/markdownlint-cli2-action@v23. このスクリプトは npx で同じ version を
# 取得して走らせるため、ローカル結果が CI と一致する。
#
# Requirements: Node.js (npx). Network access on first run (npx caches afterwards).

set -euo pipefail

# Repo root regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

CLI2_VERSION="0.22.1"  # CI のバンドル version と揃える。CI 側を更新したら同期する

if [[ "${1:-}" == "--fix" ]]; then
  exec npx --yes "markdownlint-cli2@${CLI2_VERSION}" --fix "**/*.md"
fi

exec npx --yes "markdownlint-cli2@${CLI2_VERSION}" "**/*.md"
