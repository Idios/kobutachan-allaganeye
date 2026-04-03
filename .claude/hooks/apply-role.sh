#!/usr/bin/env bash
# SessionStart hook: ROLE ファイルがあればロールを適用する
set -euo pipefail

ROLE_FILE="${CLAUDE_PROJECT_DIR}/ROLE"

if [[ -f "$ROLE_FILE" ]]; then
    ROLE=$(cat "$ROLE_FILE")
    echo "ROLE ファイルを検出: ${ROLE}"
    echo "次のコマンドを実行してロールを適用してください: /assume-role ${ROLE}"
fi
