#!/usr/bin/env bash
# Stop hook: セッション終了時に .claude/worktrees/ の残骸を sweep する (Refs #477)。
#
# scripts/cleanup-worktrees.sh を --apply モードで実行。rmdir のみを使う
# (非空ディレクトリは触らない) ため、アクティブな worktree / 作業中ファイルが
# 残っている dir は誤って削除されない。
#
# stderr 出力は Claude Code のログにのみ残る。exit は常に 0 — セッション終了を
# 妨げないようエラーも swallow する。

set -u

# `$CLAUDE_PROJECT_DIR` は Claude Code が設定する。未定義の環境 (手動テスト等)
# ではフォールバックとして hook ファイル位置から辿る。
REPO_ROOT="${CLAUDE_PROJECT_DIR:-"$(cd "$(dirname "$0")/../.." && pwd)"}"
SCRIPT="$REPO_ROOT/scripts/cleanup-worktrees.sh"

if [[ -x "$SCRIPT" ]] || [[ -f "$SCRIPT" ]]; then
  bash "$SCRIPT" --apply >&2 || true
fi

exit 0
