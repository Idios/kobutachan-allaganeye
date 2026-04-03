#!/usr/bin/env bash
# PostToolUse hook: git merge 後にファイル状態をリロードする
# Bash ツール使用後に実行され、マージが行われた場合に通知する
set -euo pipefail

# 直前の Bash コマンドが git merge を含んでいたかチェック
# （環境変数 CLAUDE_TOOL_INPUT から判定）
if [[ "${CLAUDE_TOOL_INPUT:-}" == *"git merge"* ]] || [[ "${CLAUDE_TOOL_INPUT:-}" == *"git pull"* ]]; then
    echo "git merge/pull を検出しました。CLAUDE.md およびドキュメントを再読み込みしてください。"
fi
