#!/usr/bin/env bash
# cleanup-claude-branches.sh — Delete safe `claude/*` local branches (Refs #708 / #710).
#
# Output: stdout NDJSON (one JSON object per line). Schema: schemas/cleanup-output.schema.json.
#
# Safety AND conditions (3-condition structure unchanged from pre-#710; AND 1 bases generalized in #816):
#   1. merged: ancestor of any origin/develop-* branch or origin/main
#   2. active 不在: not referenced by any active worktree
#   3. cooldown: last commit ≥ 24h ago
#   (prefix filter: claude/* only is listed)
#
# Usage:
#   scripts/cleanup-claude-branches.sh           # dry-run
#   scripts/cleanup-claude-branches.sh --apply   # actually delete
#
# Exit: 0 normal / 1 arg error / 2 not a git repo.

set -u

_SCRIPT_NAME="cleanup-claude-branches"

_emit() {
  local out='{'
  out+="\"event\":\"$1\""; shift
  out+=",\"script\":\"$_SCRIPT_NAME\""
  for kv in "$@"; do
    local k="${kv%%=*}"
    local v="${kv#*=}"
    if [[ "$v" =~ ^-?[0-9]+$ ]] || [[ "$v" == "true" || "$v" == "false" ]]; then
      out+=",\"$k\":$v"
    else
      v="${v//\\/\\\\}"; v="${v//\"/\\\"}"
      out+=",\"$k\":\"$v\""
    fi
  done
  out+='}'
  printf '%s\n' "$out"
}

COMMON_GIT_DIR="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [[ -z "$COMMON_GIT_DIR" ]]; then
  _emit error message="not a git repo (run from within the allaganeye checkout)" exit_code=2 >&2
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
      _emit error message="unknown arg '$1'" exit_code=1 >&2
      exit 1
      ;;
  esac
  shift
done

if (( APPLY )); then
  _emit start apply=true repo_root="$REPO_ROOT"
else
  _emit start apply=false repo_root="$REPO_ROOT"
fi

mapfile -t BRANCHES < <(git -C "$REPO_ROOT" branch --list 'claude/*' --format='%(refname:short)')

deleted=0
kept=0
COOLDOWN_THRESHOLD=$(($(date +%s) - 86400))

# Build active-branch set from worktree list.
declare -A ACTIVE_BRANCHES=()
while IFS= read -r line; do
  if [[ "$line" == "branch refs/heads/"* ]]; then
    ACTIVE_BRANCHES["${line#branch refs/heads/}"]=1
  fi
done < <(git -C "$REPO_ROOT" worktree list --porcelain)

# AND 1 merge bases: 全 origin/develop-* (現行/将来の開発 branch) + origin/main (#816)。
# 固定 pin (develop-0.2.0) だと release 後に新 develop branch へ merge された
# branch が永遠に not-merged 扱いになる (audit 2026-06-10 P3)。
mapfile -t MERGE_BASES < <(git -C "$REPO_ROOT" for-each-ref --format='%(refname:short)' 'refs/remotes/origin/develop-*')
MERGE_BASES+=("origin/main")

for branch in "${BRANCHES[@]}"; do
  # AND 2: active 不在判定
  if [[ -n "${ACTIVE_BRANCHES[$branch]:-}" ]]; then
    _emit kept name="$branch" reason=active
    kept=$((kept + 1))
    continue
  fi

  # AND 1: merged 判定 (いずれかの origin/develop-* or origin/main の祖先)
  merged=0
  for base in "${MERGE_BASES[@]}"; do
    if git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "$base" 2>/dev/null; then
      merged=1
      break
    fi
  done
  if [[ "$merged" -eq 0 ]]; then
    _emit kept name="$branch" reason=not-merged
    kept=$((kept + 1))
    continue
  fi

  # AND 3: cooldown
  last_ct=$(git -C "$REPO_ROOT" log -1 --format=%ct "$branch" -- 2>/dev/null || echo "")
  if [[ -z "$last_ct" ]] || [[ "$last_ct" -ge "$COOLDOWN_THRESHOLD" ]]; then
    _emit kept name="$branch" reason=cooldown
    kept=$((kept + 1))
    continue
  fi

  # 全 AND 満足 — 削除対象
  if [[ "$APPLY" -eq 1 ]]; then
    git -C "$REPO_ROOT" branch -D "$branch" >/dev/null 2>&1
    rc=$?
    if [[ "$rc" -eq 0 ]]; then
      _emit deleted name="$branch"
      deleted=$((deleted + 1))
    else
      _emit delete_failed name="$branch" exit_code="$rc"
      kept=$((kept + 1))
    fi
  else
    _emit would_delete name="$branch"
    deleted=$((deleted + 1))
  fi
done

_emit summary apply="$([[ $APPLY -eq 1 ]] && echo true || echo false)" \
              total="${#BRANCHES[@]}" deleted="$deleted" kept="$kept"
exit 0
