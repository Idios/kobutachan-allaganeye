#!/usr/bin/env bash
# cleanup-claude-branches.sh — Delete safe `claude/*` local branches (Refs #708 / #710).
#
# Output: stdout NDJSON (one JSON object per line). Schema: schemas/cleanup-output.schema.json.
#
# Safety AND conditions (3-condition structure unchanged from pre-#710; AND 1 bases generalized in #816):
#   1. merged: ancestor of the latest (sort -V) origin/develop-* or origin/main,
#      OR the branch tip OID equals a `gh pr list --state merged` head OID (#827:
#      --squash merges are not ancestors of base; OID identity match avoids
#      deleting a recreated same-name branch; gh/timeout absent or error ->
#      ancestor-only fallback)
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

# AND 1 merge bases: sort -V 最新の origin/develop-* + origin/main (#816)。
# 固定 pin (develop-0.2.0) だと release 後に新 develop branch へ merge された
# branch が永遠に not-merged 扱いになる (audit 2026-06-10 P3)。一方、全
# develop-* を信用すると fetch --prune されず残った stale な旧 develop ref
# だけに merged な branch を誤削除しうる (Codex adversarial-review HIGH) ため、
# 現行 = version 最大の develop のみを merge base に採用する (no-network 維持)。
# 注: no-network 設計のため「最新 develop ref 自体の鮮度」は原理的に保証できない
# (stale と fresh はローカルでは識別不能)。残余リスクは fetch 済み -> release なし
# 廃棄 -> 再 fetch なし、の 3 連鎖が条件で本 repo の release flow では非発生、
# かつ commit は当該 ref から reachable で GC されない (2026-06-13 Idios 受容確定)。
mapfile -t DEVELOP_REFS < <(git -C "$REPO_ROOT" for-each-ref --format='%(refname:short)' 'refs/remotes/origin/develop-*' | sort -V)
MERGE_BASES=()
if (( ${#DEVELOP_REFS[@]} > 0 )); then
  MERGE_BASES+=("${DEVELOP_REFS[-1]}")
fi
MERGE_BASES+=("origin/main")

# AND 1 augmentation (#827): --squash マージ済み branch は tip が base の祖先に
# ならない (squash は新規 commit を base に作る) ため is-ancestor では永遠に
# not-merged 扱いになる。gh pr list --state merged の head commit OID 集合を 1 回だけ
# 取得し、local branch tip の OID が一致するとき merged と判定する (is-ancestor と OR)。
# **OID 同一性で照合する** (headRefName ではない): これにより「PR merge 後に同名
# branch を再作成し未 merge の新 commit を積んだ」ケースでも local tip OID が merged
# head OID と一致しないため kept になり、不可逆 data-loss を構造的に防ぐ (codex HIGH)。
# gh または timeout が不在 / 非ゼロ exit / timeout 発火の場合は集合を空に倒し
# is-ancestor のみ (= 現行の安全側挙動) に fallback する。network lookup は必ず
# timeout で bound する (timeout 不在プラットフォームでは gh を呼ばず skip、codex MEDIUM)。
declare -A MERGED_HEAD_OIDS=()
GH_LOOKUP_STATUS=""
if (( ${#BRANCHES[@]} > 0 )); then
  if command -v gh >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
    _gh_out=$(timeout 10 gh pr list --state merged --limit 200 \
                --json headRefOid --jq '.[].headRefOid' 2>/dev/null)
    _gh_rc=$?
    if (( _gh_rc == 0 )); then
      GH_LOOKUP_STATUS="ok"
      while IFS= read -r _oid; do
        [[ -n "$_oid" ]] && MERGED_HEAD_OIDS["$_oid"]=1
      done <<< "$_gh_out"
    else
      GH_LOOKUP_STATUS="error"
    fi
  else
    GH_LOOKUP_STATUS="unavailable"
  fi
fi

if [[ -n "$GH_LOOKUP_STATUS" ]]; then
  _emit start apply="$([[ $APPLY -eq 1 ]] && echo true || echo false)" \
              repo_root="$REPO_ROOT" gh_merged_lookup="$GH_LOOKUP_STATUS"
else
  _emit start apply="$([[ $APPLY -eq 1 ]] && echo true || echo false)" \
              repo_root="$REPO_ROOT"
fi

for branch in "${BRANCHES[@]}"; do
  # AND 2: active 不在判定
  if [[ -n "${ACTIVE_BRANCHES[$branch]:-}" ]]; then
    _emit kept name="$branch" reason=active
    kept=$((kept + 1))
    continue
  fi

  # AND 1: merged 判定 (is-ancestor OR gh merged PR head、#827)
  merged=0
  merged_via=""
  for base in "${MERGE_BASES[@]}"; do
    if git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "$base" 2>/dev/null; then
      merged=1
      merged_via="ancestor"
      break
    fi
  done
  if [[ "$merged" -eq 0 ]] && (( ${#MERGED_HEAD_OIDS[@]} > 0 )); then
    branch_oid=$(git -C "$REPO_ROOT" rev-parse --verify "${branch}^{commit}" 2>/dev/null || echo "")
    if [[ -n "$branch_oid" ]] && [[ -n "${MERGED_HEAD_OIDS[$branch_oid]:-}" ]]; then
      merged=1
      merged_via="gh"
    fi
  fi
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
      _emit deleted name="$branch" merged_via="$merged_via"
      deleted=$((deleted + 1))
    else
      _emit delete_failed name="$branch" exit_code="$rc"
      kept=$((kept + 1))
    fi
  else
    _emit would_delete name="$branch" merged_via="$merged_via"
    deleted=$((deleted + 1))
  fi
done

_emit summary apply="$([[ $APPLY -eq 1 ]] && echo true || echo false)" \
              total="${#BRANCHES[@]}" deleted="$deleted" kept="$kept"
exit 0
