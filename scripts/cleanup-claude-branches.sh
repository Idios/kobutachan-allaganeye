#!/usr/bin/env bash
# cleanup-claude-branches.sh — Delete safe `claude/*` local branches (Refs #708).
#
# 安全 AND 条件:
#   1. merged: origin/develop-0.2.0 または origin/main の祖先
#   2. active 不在: git worktree list 内で参照されていない
#   3. cooldown: 最終 commit が 24h 以上前
#   (prefix: claude/ のみ列挙対象)
#
# 使い方:
#   scripts/cleanup-claude-branches.sh           # dry-run (default)
#   scripts/cleanup-claude-branches.sh --apply   # 実削除
#
# 仕様:
#   - rmdir 同様、削除は明確に安全な条件下のみ (data loss なし保証)
#   - git common dir 解決により worktree 内から呼ばれても main checkout を操作
#   - exit 0: 正常 / 1: 引数エラー / 2: not a git repo
#   - 削除失敗は exit 0 維持 (hook 全体を妨げない)

set -u

COMMON_GIT_DIR="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [[ -z "$COMMON_GIT_DIR" ]]; then
  echo "error: not a git repo (run from within the allaganeye checkout)" >&2
  exit 2
fi
COMMON_GIT_DIR="$(cd "$COMMON_GIT_DIR" && pwd)"
REPO_ROOT="$(dirname "$COMMON_GIT_DIR")"

APPLY=0
while (( $# > 0 )); do
  case "$1" in
    --apply|-a) APPLY=1 ;;
    -h|--help)
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

echo "== scan claude/* branches in $REPO_ROOT =="
mapfile -t BRANCHES < <(git -C "$REPO_ROOT" branch --list 'claude/*' --format='%(refname:short)')

if (( ${#BRANCHES[@]} == 0 )); then
  echo "  no claude/* branches found"
  echo "summary: 0 deleted / 0 kept / 0 total"
  exit 0
fi

deleted=0
kept=0
for branch in "${BRANCHES[@]}"; do
  # 後続 Task で AND 1/2/3 を埋める。skeleton では全 branch を keep (placeholder)。
  echo "  would delete $branch (skeleton, all conditions assumed satisfied)"
  kept=$((kept + 1))
done

echo "summary: $deleted deleted / $kept kept / ${#BRANCHES[@]} total"
exit 0
