#!/usr/bin/env bash
# Stop hook: セッション終了時に worktree / branch 残骸を sweep する (Refs #477 / #708)。
#
# 2 つの cleanup script を順次起動する:
#   1. scripts/cleanup-worktrees.sh --apply    — worktree 空 dir を rmdir で除去 (#477)
#   2. scripts/cleanup-claude-branches.sh --apply — 安全 AND 条件を満たす claude/* branch を
#      git branch -D で削除 (#708、merged + active 不在 + claude/ prefix + 24h cooldown)
#
# rmdir / git branch -D とも明示的な安全条件下のみ操作するため、未保存ファイルや
# 作業中の worktree / branch が誤って消失することはない。
#
# 診断ログ: hook 自体の発火と各 cleanup script の出力 / exit code を
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
SCRIPT_BRANCHES="$REPO_ROOT/scripts/cleanup-claude-branches.sh"
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
    # trailing `|| true` を付けると `$?` が `true` (=0) に上書きされ、cleanup
    # script の non-zero exit を取りこぼす (review-pr Round 1 Finding #1)。
    # `set -e` は使っていない (set -u のみ) ため、command substitution が
    # non-zero でも shell は継続する。よって `|| true` 不要。
    output=$(bash "$SCRIPT" --apply 2>&1)
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

  # -f fallback: bash を explicit invocation (`bash "$SCRIPT_BRANCHES"`) しているので、
  # +x が付いていない file でも実行可能。OR で `-f` 単独 true の場合も run する。
  if [[ -x "$SCRIPT_BRANCHES" ]] || [[ -f "$SCRIPT_BRANCHES" ]]; then
    echo "  cleanup-claude-branches.sh: present"
    output2=$(bash "$SCRIPT_BRANCHES" --apply 2>&1)
    rc2=$?
    echo "  branch cleanup exit=$rc2"
    echo "  --- branch cleanup ---"
    printf '%s\n' "$output2"
    echo "  --- end branch cleanup ---"
    # 既存契約に倣い、branch cleanup 出力も stderr に流す
    printf '%s\n' "$output2" >&2
  else
    echo "  cleanup-claude-branches.sh: NOT FOUND at $SCRIPT_BRANCHES"
  fi
  echo ""
} >>"$LOG" 2>/dev/null || true

exit 0
