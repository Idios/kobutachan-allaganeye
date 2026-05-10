#!/usr/bin/env bash
# Stop hook: セッション終了時に .claude/worktrees/ の残骸を sweep する (Refs #477)。
#
# scripts/cleanup-worktrees.sh を --apply モードで実行。rmdir のみを使う
# (非空ディレクトリは触らない) ため、アクティブな worktree / 作業中ファイルが
# 残っている dir は誤って削除されない。
#
# 診断ログ: hook 自体の発火と cleanup-worktrees.sh の出力 / exit code を
# `.claude/state/stop-hook.log` に追記する。「hook が発火しているか」と
# 「発火しているが何かで silent fail しているか」の切り分け用。`.claude/state/`
# は .gitignore 済 (= ログファイルも commit されない)。
#
# stderr 出力は Claude Code のログにのみ残る。exit は常に 0 — セッション終了を
# 妨げないようエラーも swallow する。

set -u

# `$CLAUDE_PROJECT_DIR` は Claude Code が設定する。未定義の環境 (手動テスト等)
# ではフォールバックとして hook ファイル位置から辿る。
REPO_ROOT="${CLAUDE_PROJECT_DIR:-"$(cd "$(dirname "$0")/../.." && pwd)"}"
SCRIPT="$REPO_ROOT/scripts/cleanup-worktrees.sh"
LOG="$REPO_ROOT/.claude/state/stop-hook.log"

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true

{
  echo "===== $(date -Iseconds 2>/dev/null || date) stop.sh invoked ====="
  echo "  CLAUDE_PROJECT_DIR=${CLAUDE_PROJECT_DIR:-<unset>}"
  echo "  REPO_ROOT=$REPO_ROOT"
  echo "  PWD=$(pwd)"
  echo "  hook=$0"

  if [[ -x "$SCRIPT" ]] || [[ -f "$SCRIPT" ]]; then
    echo "  cleanup-worktrees.sh: present"
    output=$(bash "$SCRIPT" --apply 2>&1) || true
    rc=$?
    echo "  cleanup exit=$rc"
    echo "  --- cleanup output ---"
    printf '%s\n' "$output"
    echo "  --- end output ---"
    # 既存契約: cleanup 出力は stderr にも流して Claude Code 側のログに残す
    printf '%s\n' "$output" >&2
  else
    echo "  cleanup-worktrees.sh: NOT FOUND at $SCRIPT"
  fi
  echo ""
} >>"$LOG" 2>/dev/null || true

exit 0
