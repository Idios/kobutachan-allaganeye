#!/usr/bin/env bash
# cleanup-worktrees.sh — Sweep orphan .claude/worktrees/ directories (Refs #477 / #710).
#
# Output: stdout NDJSON (one JSON object per line). Schema: schemas/cleanup-output.schema.json.
# Pretty-printing: `scripts/cleanup-worktrees.sh | scripts/format-cleanup-log.sh`.
#
# Behavior (unchanged from pre-#710):
#   1. `git worktree prune` for git metadata first.
#   2. Scan .claude/worktrees/<name>/. If empty + not active, rmdir.
#
# Usage:
#   scripts/cleanup-worktrees.sh           # dry-run
#   scripts/cleanup-worktrees.sh --apply   # actually rmdir
#
# Exit: 0 normal / 1 arg error / 2 unexpected failure.

set -euo pipefail

_SCRIPT_NAME="cleanup-worktrees"

# NDJSON emitter. Usage:
#   _emit start apply=true repo_root=/path
#   _emit removed name=foo
#   _emit kept name=foo reason=not-empty
#   _emit summary apply=true total=3 removed=2 kept=1 orphan_candidates=3
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

WT_DIR="$REPO_ROOT/.claude/worktrees"
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

if [[ ! -d "$WT_DIR" ]]; then
  _emit summary apply="$([[ $APPLY -eq 1 ]] && echo true || echo false)" \
                total=0 removed=0 kept=0 orphan_candidates=0
  exit 0
fi

# Step 1: git worktree prune (silent — its output is not part of our NDJSON contract).
if (( APPLY )); then
  git -C "$REPO_ROOT" worktree prune >/dev/null 2>&1 || true
else
  git -C "$REPO_ROOT" worktree prune --dry-run >/dev/null 2>&1 || true
fi

# Step 2: scan
orphan_count=0
removed_count=0
kept_count=0

for d in "$WT_DIR"/*/; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"

  if [[ -e "$d/.git" ]]; then
    _emit skip name="$name" reason=active
    continue
  fi

  orphan_count=$((orphan_count + 1))

  if (( APPLY )); then
    if rmdir "$d" 2>/dev/null; then
      _emit removed name="$name"
      removed_count=$((removed_count + 1))
    else
      _emit kept name="$name" reason=not-empty
      kept_count=$((kept_count + 1))
    fi
  else
    if [[ -z "$(ls -A "$d" 2>/dev/null)" ]]; then
      _emit would_remove name="$name"
      removed_count=$((removed_count + 1))
    else
      _emit would_skip name="$name" reason=not-empty
      kept_count=$((kept_count + 1))
    fi
  fi
done

if (( APPLY )); then
  _emit summary apply=true total="$orphan_count" removed="$removed_count" \
                kept="$kept_count" orphan_candidates="$orphan_count"
else
  _emit summary apply=false total="$orphan_count" removed="$removed_count" \
                kept="$kept_count" orphan_candidates="$orphan_count"
fi
