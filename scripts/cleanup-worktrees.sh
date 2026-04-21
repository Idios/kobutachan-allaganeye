#!/usr/bin/env bash
# cleanup-worktrees.sh — Sweep orphan .claude/worktrees/ directories (Refs #477).
#
# セッション終了時に `git worktree remove` が実行されても、
# .claude/worktrees/<name>/ 自体のディレクトリだけが空で残る残骸パターン
# に対する手動 sweep スクリプト。
#
# 動作:
#   1. `git worktree prune` で git 側メタデータを先にクリーンアップ
#   2. .claude/worktrees/<name>/ を走査し、
#      - `.git` (ファイル or ディレクトリ) が存在しない = アクティブ worktree ではない
#      - 中身が空 = 残骸の可能性が高い
#      に該当するディレクトリを rmdir で削除 (非空なら失敗して安全)
#
# 使い方:
#   scripts/cleanup-worktrees.sh           # dry-run (削除候補を表示するのみ)
#   scripts/cleanup-worktrees.sh --apply   # 実際に rmdir を実行
#
# 仕様:
#   - rmdir のみを使用するため、非空ディレクトリは削除されない (安全側)
#   - アクティブ worktree (`.git` 参照がある) は対象外
#   - exit 0: 正常 / exit 1: 引数エラー / exit 2: 予期しない失敗

set -euo pipefail

# `--git-common-dir` returns the shared .git directory even from inside a
# linked worktree, so `.claude/worktrees/` (which only lives in the main
# checkout) is always reachable regardless of where the script is invoked.
COMMON_GIT_DIR="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [[ -z "$COMMON_GIT_DIR" ]]; then
  echo "error: not a git repo (run from within the allaganeye checkout)" >&2
  exit 2
fi
# Resolve to an absolute path; the main repo root is its parent.
COMMON_GIT_DIR="$(cd "$COMMON_GIT_DIR" && pwd)"
REPO_ROOT="$(dirname "$COMMON_GIT_DIR")"

WT_DIR="$REPO_ROOT/.claude/worktrees"
APPLY=0

while (( $# > 0 )); do
  case "$1" in
    --apply|-a) APPLY=1 ;;
    -h|--help)
      # Print the leading comment header only (stop at first non-comment line).
      awk 'NR==1 && /^#!/ {next} /^# ?/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown arg '$1'" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ ! -d "$WT_DIR" ]]; then
  echo "no worktree dir at $WT_DIR — nothing to do"
  exit 0
fi

echo "== step 1: git worktree prune =="
if (( APPLY )); then
  git -C "$REPO_ROOT" worktree prune -v
else
  git -C "$REPO_ROOT" worktree prune --dry-run -v || true
fi

echo ""
echo "== step 2: scan $WT_DIR for orphan directories =="
orphan_count=0
removed_count=0
for d in "$WT_DIR"/*/; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"

  # Active worktree (has .git reference) — skip.
  if [[ -e "$d/.git" ]]; then
    echo "  skip $name (active worktree)"
    continue
  fi

  orphan_count=$((orphan_count + 1))

  if (( APPLY )); then
    # rmdir fails safely on non-empty dirs; surface that as a notice.
    if rmdir "$d" 2>/dev/null; then
      echo "  removed $name"
      removed_count=$((removed_count + 1))
    else
      echo "  kept $name (directory not empty; inspect manually)"
    fi
  else
    if [[ -z "$(ls -A "$d" 2>/dev/null)" ]]; then
      echo "  would remove $name (empty)"
    else
      echo "  would skip $name (directory not empty)"
    fi
  fi
done

echo ""
if (( APPLY )); then
  echo "done: $removed_count removed / $orphan_count orphan candidates"
else
  echo "dry-run: $orphan_count orphan candidate(s). Re-run with --apply to remove empty ones."
fi
