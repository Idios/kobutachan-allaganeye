# claude/* ブランチ自動削除機構 Implementation Plan (Refs #708)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/cleanup-claude-branches.sh` を新設し、Stop hook から呼び出して安全条件 (`merged` AND `active 参照なし` AND `claude/ prefix` AND `24h cooldown`) を満たす `claude/*` ローカルブランチを自動削除する。

**Architecture:** 既存 `scripts/cleanup-worktrees.sh` は一切触らず、新 script を別 file で実装 (SRP)。`.claude/hooks/stop.sh` は PR #707 で追加した診断ログ block 構造 (`output=$(...); rc=$?` パターン、Round 1 fix 適用済) を踏襲して新 script の output block を追加。Test は `tmp/cleanup-branches-test-N/` 配下の tmp git repo に対する ad-hoc mock で 5 シナリオ手動検証 (本格 framework 化は #710 で hand off)。

**Tech Stack:** bash (`set -u`), git (`worktree list --porcelain` / `merge-base --is-ancestor` / `branch --list` / `branch -D` / `log -1 --format=%ct`), markdownlint-cli2 (doc lint via `scripts/check-markdownlint.sh`)

**Spec:** [docs/superpowers/specs/2026-05-11-cleanup-claude-branches-design.md](../specs/2026-05-11-cleanup-claude-branches-design.md)

---

## File Structure

| Path | 操作 | 責務 |
| --- | --- | --- |
| `scripts/cleanup-claude-branches.sh` | Create | dry-run / --apply で claude/* branch を安全 AND 判定して削除する単一目的 script |
| `.claude/hooks/stop.sh` | Modify | 既存 cleanup-worktrees.sh block の後ろに新 script 呼び出し block を追加 |
| `docs/l2-workflow.md` | Modify | §「worktree メンテナンス (#477)」内に branch cleanup 関連の段落 + subsection 追加 |
| `tmp/cleanup-branches-test-N/` | (not committed) | 各 Task の手動 mock 用 tmp git repo (実行後削除) |

---

## Task 1: Skeleton + scenario 5 (prefix filtering)

**目的**: `scripts/cleanup-claude-branches.sh` の骨格 (引数 parse / help / git common dir 解決 / `claude/*` enumeration) を作る。AND 判定はまだ全て pass 扱いで dry-run output だけ整える。scenario 5 (`feature/xxx` が列挙対象外) を pass させる。

**Files:**

- Create: `scripts/cleanup-claude-branches.sh` (~50 行)

- [ ] **Step 1: Write the failing test (scenario 5 mock setup)**

下記の bash one-liner で tmp git repo を作る:

```bash
TMP=$(mktemp -d --suffix=-cleanup-test-1)
git -C "$TMP" init -q -b develop-0.2.0
git -C "$TMP" config user.email "test@test.local"
git -C "$TMP" config user.name "test"
echo "init" > "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "init"
# `feature/xxx` branch を作る (claude/* prefix ではない → 列挙対象外)
git -C "$TMP" branch feature/xxx
# `claude/foo` branch も作る (列挙対象だが AND 判定はまだ skeleton で全部 pass する想定)
git -C "$TMP" branch claude/foo
echo "TEST_DIR=$TMP"
```

期待動作 (skeleton 版):

- 出力に `feature/xxx` が現れない (= claude/* prefix のみ enumerate)
- 出力に `claude/foo` が現れる (現時点では `would delete claude/foo` または skeleton の placeholder 出力)
- exit 0

- [ ] **Step 2: Run test to verify it fails**

```bash
bash scripts/cleanup-claude-branches.sh
```

Expected: FAIL (`bash: scripts/cleanup-claude-branches.sh: No such file or directory`)

- [ ] **Step 3: Write minimal implementation (skeleton)**

`scripts/cleanup-claude-branches.sh` を以下の内容で作成:

```bash
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
```

```bash
chmod +x scripts/cleanup-claude-branches.sh
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TMP=$(mktemp -d --suffix=-cleanup-test-1)
git -C "$TMP" init -q -b develop-0.2.0
git -C "$TMP" config user.email "test@test.local"
git -C "$TMP" config user.name "test"
echo "init" > "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "init"
git -C "$TMP" branch feature/xxx
git -C "$TMP" branch claude/foo
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh")
rm -rf "$TMP"
```

Expected output (要点):

```text
== scan claude/* branches in /tmp/...-cleanup-test-1 ==
  would delete claude/foo (skeleton, ...)
summary: 0 deleted / 1 kept / 1 total
```

(`feature/xxx` が出力に含まれていないことを目視確認 = scenario 5 pass)

- [ ] **Step 5: Commit**

```bash
git add scripts/cleanup-claude-branches.sh
git commit -F - <<'EOF'
feat(scripts): cleanup-claude-branches.sh skeleton (Refs #708)

Issue #708 (claude/* ブランチ自動削除) の実装 Task 1。

skeleton として以下を実装:
- 引数 parse (--apply / -h / --help)
- git common dir 解決 (worktree 内から呼ばれても main checkout を操作)
- claude/* prefix で branch enumerate (feature/xxx 等は対象外)
- AND 判定は後続 Task で追加、本 step では placeholder

mock test scenario 5 (prefix 違いは列挙対象外) を pass 確認。

Refs #708
EOF
```

---

## Task 2: AND 2 (active worktree exclusion)

**目的**: `git worktree list --porcelain` を parse して active worktree が参照する branch 集合を構築し、列挙された claude/* branch が含まれていれば `kept ... (reason: active)` で除外する。

**Files:**

- Modify: `scripts/cleanup-claude-branches.sh` (列挙ループ部分を拡張)

- [ ] **Step 1: Write the failing test (scenario 3 mock setup)**

```bash
TMP=$(mktemp -d --suffix=-cleanup-test-2)
git -C "$TMP" init -q -b develop-0.2.0
git -C "$TMP" config user.email "test@test.local"
git -C "$TMP" config user.name "test"
echo "init" > "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "init"
git -C "$TMP" branch claude/active-branch
# active worktree を構築 (claude/active-branch を参照)
git -C "$TMP" worktree add "$TMP-wt" claude/active-branch
echo "TEST_DIR=$TMP"
```

期待動作:

- `claude/active-branch` が `kept claude/active-branch (reason: active)` として出力される
- exit 0

- [ ] **Step 2: Run test to verify it fails**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh")
```

Expected: FAIL (現状 skeleton では `would delete claude/active-branch (skeleton, ...)` と出る → active 判定なし)

- [ ] **Step 3: Write minimal implementation**

`scripts/cleanup-claude-branches.sh` を編集して、列挙ループの前に active 集合構築を追加し、ループ内で active match を check する。

`mapfile -t BRANCHES ...` の直後に追加:

```bash
# active worktree が参照する branch 集合 (refs/heads/<name> 形式) を構築
declare -A ACTIVE_BRANCHES=()
while IFS= read -r line; do
  if [[ "$line" == "branch refs/heads/"* ]]; then
    ACTIVE_BRANCHES["${line#branch refs/heads/}"]=1
  fi
done < <(git -C "$REPO_ROOT" worktree list --porcelain)
```

そして for ループ内の `echo "  would delete ..."` を以下に置換:

```bash
for branch in "${BRANCHES[@]}"; do
  # AND 2: active 不在判定
  if [[ -n "${ACTIVE_BRANCHES[$branch]:-}" ]]; then
    echo "  kept $branch (reason: active)"
    kept=$((kept + 1))
    continue
  fi

  # AND 1 / AND 3 は後続 Task で追加、本 Task では「active 以外は keep (skeleton)」のまま
  echo "  would delete $branch (skeleton, AND 1/3 not yet implemented)"
  kept=$((kept + 1))
done
```

- [ ] **Step 4: Run test to verify it passes**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh")
rm -rf "$TMP" "$TMP-wt"
```

Expected output (要点):

```text
== scan claude/* branches in /tmp/...-cleanup-test-2 ==
  kept claude/active-branch (reason: active)
summary: 0 deleted / 1 kept / 1 total
```

- [ ] **Step 5: Commit**

```bash
git add scripts/cleanup-claude-branches.sh
git commit -F - <<'EOF'
feat(scripts): cleanup-claude-branches.sh の AND 2 (active 不在) 実装 (Refs #708)

git worktree list --porcelain を parse して active 参照集合を構築。
列挙された claude/* branch が active worktree に参照されていれば
`kept ... (reason: active)` で除外する。

mock test scenario 3 (active worktree が参照) を pass 確認。

Refs #708
EOF
```

---

## Task 3: AND 1 (merged ancestor judgment)

**目的**: `git merge-base --is-ancestor <branch> origin/develop-0.2.0` OR `... origin/main` で merged 判定。両方失敗なら `kept ... (reason: not-merged)`。

**Files:**

- Modify: `scripts/cleanup-claude-branches.sh` (for ループ内に AND 1 を追加)

- [ ] **Step 1: Write the failing test (scenario 1 + 2 mock setup)**

scenario 1 (merged) と scenario 2 (not merged) を両方含む tmp repo:

```bash
TMP=$(mktemp -d --suffix=-cleanup-test-3)
git -C "$TMP" init -q -b develop-0.2.0
git -C "$TMP" config user.email "test@test.local"
git -C "$TMP" config user.name "test"
echo "init" > "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "init"
# develop-0.2.0 に追加 commit を載せる
echo "more" >> "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "more"
DEVELOP_TIP=$(git -C "$TMP" rev-parse HEAD)
# remote tracking ref を仮構築: origin/develop-0.2.0 を develop-0.2.0 と同じに
git -C "$TMP" update-ref refs/remotes/origin/develop-0.2.0 "$DEVELOP_TIP"
# scenario 1: claude/merged は develop-0.2.0 の祖先 (= HEAD の親など)
PARENT=$(git -C "$TMP" rev-parse HEAD~1)
git -C "$TMP" branch claude/merged "$PARENT"
# scenario 2: claude/not-merged は別の commit (祖先になっていない)
git -C "$TMP" checkout -q -b tmp-not-merged "$PARENT"
echo "diverged" > "$TMP/diverged.txt"
git -C "$TMP" add diverged.txt
git -C "$TMP" commit -q -m "diverged"
git -C "$TMP" branch claude/not-merged
git -C "$TMP" checkout -q develop-0.2.0
git -C "$TMP" branch -D tmp-not-merged
echo "TEST_DIR=$TMP"
```

期待動作:

- `claude/merged` → `would delete claude/merged (skeleton, AND 3 not yet implemented)` (AND 1/2 pass、AND 3 未実装で placeholder 経由)
- `claude/not-merged` → `kept claude/not-merged (reason: not-merged)`

- [ ] **Step 2: Run test to verify it fails**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh")
```

Expected: FAIL (`claude/not-merged` も `would delete ... (skeleton)` と出る → AND 1 判定がないので両方とも skeleton fall-through)

- [ ] **Step 3: Write minimal implementation**

`scripts/cleanup-claude-branches.sh` を編集。AND 2 active check の後ろに AND 1 (merged) を挿入:

```bash
for branch in "${BRANCHES[@]}"; do
  # AND 2: active 不在判定
  if [[ -n "${ACTIVE_BRANCHES[$branch]:-}" ]]; then
    echo "  kept $branch (reason: active)"
    kept=$((kept + 1))
    continue
  fi

  # AND 1: merged 判定 (origin/develop-0.2.0 OR origin/main の祖先)
  merged=0
  if git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "origin/develop-0.2.0" 2>/dev/null; then
    merged=1
  elif git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "origin/main" 2>/dev/null; then
    merged=1
  fi
  if (( merged == 0 )); then
    echo "  kept $branch (reason: not-merged)"
    kept=$((kept + 1))
    continue
  fi

  # AND 3 は後続 Task で追加、本 Task では merged + active なし = skeleton fall-through
  echo "  would delete $branch (skeleton, AND 3 not yet implemented)"
  kept=$((kept + 1))
done
```

- [ ] **Step 4: Run test to verify it passes**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh")
rm -rf "$TMP"
```

Expected output (要点):

```text
  would delete claude/merged (skeleton, AND 3 not yet implemented)
  kept claude/not-merged (reason: not-merged)
summary: 0 deleted / 2 kept / 2 total
```

- [ ] **Step 5: Commit**

```bash
git add scripts/cleanup-claude-branches.sh
git commit -F - <<'EOF'
feat(scripts): cleanup-claude-branches.sh の AND 1 (merged) 実装 (Refs #708)

git merge-base --is-ancestor で origin/develop-0.2.0 OR origin/main の
祖先か判定。両方とも非 ancestor / 両方とも ref 未存在の場合は
`kept ... (reason: not-merged)` で除外。

未 fetch の remote ref は is-ancestor false に倒れて keep される = 安全側。

mock test scenario 1 + 2 (merged / not-merged) を pass 確認。

Refs #708
EOF
```

---

## Task 4: AND 3 (24h cooldown)

**目的**: `git log -1 --format=%ct <branch>` の unix timestamp が `$(date +%s) - 86400` より小さい (= 24h より前) ことを確認。新しい branch は `kept ... (reason: cooldown)`。

**Files:**

- Modify: `scripts/cleanup-claude-branches.sh` (for ループ内に AND 3 を追加)

- [ ] **Step 1: Write the failing test (scenario 4 mock setup)**

scenario 1 (merged + 古い、現実装で would delete) と scenario 4 (merged + 新しい、cooldown 内) を混在させる:

```bash
TMP=$(mktemp -d --suffix=-cleanup-test-4)
git -C "$TMP" init -q -b develop-0.2.0
git -C "$TMP" config user.email "test@test.local"
git -C "$TMP" config user.name "test"
echo "init" > "$TMP/README.md"
git -C "$TMP" add README.md
# scenario 1 用の古い commit (48h 前)
GIT_AUTHOR_DATE="$(date -d '48 hours ago' -Iseconds)" \
GIT_COMMITTER_DATE="$(date -d '48 hours ago' -Iseconds)" \
  git -C "$TMP" commit -q -m "old"
OLD_TIP=$(git -C "$TMP" rev-parse HEAD)
# develop-0.2.0 にもう 1 commit (新しい、現在時刻)
echo "recent" >> "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "recent"
DEVELOP_TIP=$(git -C "$TMP" rev-parse HEAD)
git -C "$TMP" update-ref refs/remotes/origin/develop-0.2.0 "$DEVELOP_TIP"
# scenario 1: claude/old は 48h 前の commit を tip にする (merged + 古い)
git -C "$TMP" branch claude/old "$OLD_TIP"
# scenario 4: claude/recent は最新 commit を tip にする (merged + 新しい)
git -C "$TMP" branch claude/recent "$DEVELOP_TIP"
echo "TEST_DIR=$TMP"
```

期待動作:

- `claude/old` → `would delete claude/old (skeleton, ...)` (AND 1/2/3 全 pass、--apply まだないので skeleton fall-through)
  - **本 Task 完了時点では `would delete claude/old`** (最終 AND 3 判定 pass の結果として would-delete fall-through を維持)
- `claude/recent` → `kept claude/recent (reason: cooldown)`

- [ ] **Step 2: Run test to verify it fails**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh")
```

Expected: FAIL (`claude/recent` も `would delete ... (skeleton, AND 3 not yet implemented)` と出る → AND 3 判定なし)

- [ ] **Step 3: Write minimal implementation**

`scripts/cleanup-claude-branches.sh` を編集。AND 1 merged check の後ろに AND 3 (cooldown) を挿入し、最終 fall-through を `would delete <branch>` (skeleton 注釈なし) に変更:

```bash
COOLDOWN_THRESHOLD=$(($(date +%s) - 86400))

for branch in "${BRANCHES[@]}"; do
  # AND 2: active 不在判定
  if [[ -n "${ACTIVE_BRANCHES[$branch]:-}" ]]; then
    echo "  kept $branch (reason: active)"
    kept=$((kept + 1))
    continue
  fi

  # AND 1: merged 判定
  merged=0
  if git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "origin/develop-0.2.0" 2>/dev/null; then
    merged=1
  elif git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "origin/main" 2>/dev/null; then
    merged=1
  fi
  if (( merged == 0 )); then
    echo "  kept $branch (reason: not-merged)"
    kept=$((kept + 1))
    continue
  fi

  # AND 3: cooldown (最終 commit が 24h 以上前か)
  last_ct=$(git -C "$REPO_ROOT" log -1 --format=%ct "$branch" 2>/dev/null || echo "")
  if [[ -z "$last_ct" ]] || (( last_ct >= COOLDOWN_THRESHOLD )); then
    echo "  kept $branch (reason: cooldown)"
    kept=$((kept + 1))
    continue
  fi

  # 全 AND 満足 — 削除対象 (--apply は Task 5 で追加)
  echo "  would delete $branch"
  kept=$((kept + 1))
done
```

- [ ] **Step 4: Run test to verify it passes**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh")
rm -rf "$TMP"
```

Expected output (要点):

```text
  would delete claude/old
  kept claude/recent (reason: cooldown)
summary: 0 deleted / 2 kept / 2 total
```

- [ ] **Step 5: Commit**

```bash
git add scripts/cleanup-claude-branches.sh
git commit -F - <<'EOF'
feat(scripts): cleanup-claude-branches.sh の AND 3 (24h cooldown) 実装 (Refs #708)

git log -1 --format=%ct で branch の最終 commit unix timestamp を取得し、
$(date +%s) - 86400 と比較。24h 以内なら `kept ... (reason: cooldown)`。
log 失敗時 (broken ref) も cooldown reason で keep = 安全側。

これで AND 1/2/3 + claude/ prefix の全 4 条件が揃った。
本 Task では --apply モード未実装のため、全 AND 満足は dry-run 表示
`would delete <branch>` で fall-through する。実 deletion は Task 5。

mock test scenario 4 (cooldown 内) を pass 確認。

Refs #708
EOF
```

---

## Task 5: --apply mode + summary

**目的**: `--apply` flag 時に `git branch -D` で実削除。summary 行 (`<D> deleted / <K> kept / <T> total`) を最終的に確定させる。

**Files:**

- Modify: `scripts/cleanup-claude-branches.sh` (削除実行 + summary 整合)

- [ ] **Step 1: Write the failing test (scenario 1 --apply)**

```bash
TMP=$(mktemp -d --suffix=-cleanup-test-5)
git -C "$TMP" init -q -b develop-0.2.0
git -C "$TMP" config user.email "test@test.local"
git -C "$TMP" config user.name "test"
echo "init" > "$TMP/README.md"
git -C "$TMP" add README.md
GIT_AUTHOR_DATE="$(date -d '48 hours ago' -Iseconds)" \
GIT_COMMITTER_DATE="$(date -d '48 hours ago' -Iseconds)" \
  git -C "$TMP" commit -q -m "old"
OLD_TIP=$(git -C "$TMP" rev-parse HEAD)
echo "recent" >> "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "recent"
DEVELOP_TIP=$(git -C "$TMP" rev-parse HEAD)
git -C "$TMP" update-ref refs/remotes/origin/develop-0.2.0 "$DEVELOP_TIP"
git -C "$TMP" branch claude/old "$OLD_TIP"
echo "TEST_DIR=$TMP"
```

期待動作:

- `bash scripts/cleanup-claude-branches.sh --apply` で `deleted claude/old`
- 実行後 `git branch --list 'claude/*'` の結果が空
- `summary: 1 deleted / 0 kept / 1 total`

- [ ] **Step 2: Run test to verify it fails**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh" --apply)
git -C "$TMP" branch --list 'claude/*'
```

Expected: FAIL (現状 `would delete claude/old` が出るが `claude/old` は削除されない / branch --list で `claude/old` がまだ残る / `summary: 0 deleted / 1 kept / 1 total`)

- [ ] **Step 3: Write minimal implementation**

最後の fall-through ブロックを以下に置換:

```bash
  # 全 AND 満足 — 削除対象
  if (( APPLY )); then
    if git -C "$REPO_ROOT" branch -D "$branch" 2>/dev/null; then
      echo "  deleted $branch"
      deleted=$((deleted + 1))
    else
      echo "  delete failed: $branch"
      kept=$((kept + 1))
    fi
  else
    echo "  would delete $branch"
    deleted=$((deleted + 1))
  fi
```

注: dry-run 時も `deleted` counter を increment することで summary の `deleted` 列が「削除候補数」になり、`--apply` 後の summary と意味的に対応する。

- [ ] **Step 4: Run test to verify it passes**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh" --apply)
echo "--- remaining claude/* branches: ---"
git -C "$TMP" branch --list 'claude/*'
rm -rf "$TMP"
```

Expected output (要点):

```text
  deleted claude/old
summary: 1 deleted / 0 kept / 1 total
--- remaining claude/* branches: ---
(空行)
```

- [ ] **Step 5: Commit**

```bash
git add scripts/cleanup-claude-branches.sh
git commit -F - <<'EOF'
feat(scripts): cleanup-claude-branches.sh --apply モード + summary 整合 (Refs #708)

--apply 時に git branch -D で実削除を行う。失敗時は `delete failed: <branch>`
を出力して kept としてカウント、hook 全体を妨げないよう exit 0 維持。
dry-run 時は `would delete <branch>` で deleted counter を increment
(= 削除候補数として summary 表示に対応)。

mock test scenario 1 (merged + 古い + active なし) を --apply 付きで
pass 確認: `deleted claude/old` 出力 + 実 branch -D 実行を git branch --list
で目視確認。

Refs #708
EOF
```

---

## Task 6: stop.sh integration

**目的**: `.claude/hooks/stop.sh` を編集して、既存 cleanup-worktrees.sh block の後ろに新 cleanup-claude-branches.sh の output block を追加。`stop-hook.log` の 1 ファイル統合を実現。

**Files:**

- Modify: `.claude/hooks/stop.sh`

- [ ] **Step 1: Write the failing test (mock stop.sh invocation)**

stop.sh を mock で起動して `stop-hook.log` に新 block が現れるか確認するセットアップ:

```bash
TMP=$(mktemp -d --suffix=-stop-hook-test-6)
mkdir -p "$TMP/.claude/state" "$TMP/scripts"
# 既存 cleanup-worktrees.sh を simulate (stdout 1 行のみ)
cat > "$TMP/scripts/cleanup-worktrees.sh" <<'MOCK'
#!/usr/bin/env bash
echo "mock dir cleanup output"
exit 0
MOCK
chmod +x "$TMP/scripts/cleanup-worktrees.sh"
# 新 cleanup-claude-branches.sh を simulate
cat > "$TMP/scripts/cleanup-claude-branches.sh" <<'MOCK'
#!/usr/bin/env bash
echo "mock branch cleanup output"
exit 0
MOCK
chmod +x "$TMP/scripts/cleanup-claude-branches.sh"
echo "TEST_DIR=$TMP"
```

期待動作:

- `CLAUDE_PROJECT_DIR=$TMP bash .claude/hooks/stop.sh` 実行で `$TMP/.claude/state/stop-hook.log` に以下が含まれる:
  - `--- cleanup output ---` block (既存)
  - `--- branch cleanup ---` block (新規) + `mock branch cleanup output`
  - `branch cleanup exit=0`

- [ ] **Step 2: Run test to verify it fails**

```bash
CLAUDE_PROJECT_DIR="$TMP" bash .claude/hooks/stop.sh
echo "--- log ---"
cat "$TMP/.claude/state/stop-hook.log"
```

Expected: FAIL (現状 stop.sh は cleanup-worktrees.sh しか呼ばないので `--- branch cleanup ---` block が log にない)

- [ ] **Step 3: Write minimal implementation**

`.claude/hooks/stop.sh` を編集。`SCRIPT=...` の直後に `SCRIPT_BRANCHES` を追加し、cleanup-worktrees.sh block の終わり (現状 line 49 の `else ... fi` 直後) と最後の空 `echo ""` の間に新 block を挿入。

Diff の outline:

```diff
 SCRIPT="$REPO_ROOT/scripts/cleanup-worktrees.sh"
+SCRIPT_BRANCHES="$REPO_ROOT/scripts/cleanup-claude-branches.sh"
 LOG="$REPO_ROOT/.claude/state/stop-hook.log"
```

そして既存の `--- end output ---` block の後ろ、`echo ""` の前に挿入:

```bash
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
> "$TMP/.claude/state/stop-hook.log"
CLAUDE_PROJECT_DIR="$TMP" bash .claude/hooks/stop.sh
echo "--- log ---"
cat "$TMP/.claude/state/stop-hook.log"
rm -rf "$TMP"
```

Expected output (log 内に以下が連続して存在):

```text
  cleanup-worktrees.sh: present
  cleanup exit=0
  --- cleanup output ---
mock dir cleanup output
  --- end output ---
  cleanup-claude-branches.sh: present
  branch cleanup exit=0
  --- branch cleanup ---
mock branch cleanup output
  --- end branch cleanup ---
```

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/stop.sh
git commit -F - <<'EOF'
feat(hooks): stop.sh から cleanup-claude-branches.sh も呼び出し (Refs #708)

PR #707 で追加した診断ログ block 構造 (output=$(...); rc=$?) を踏襲し、
cleanup-worktrees.sh block の後ろに cleanup-claude-branches.sh の output
block を追加。stop-hook.log に `--- branch cleanup ---` ... `--- end
branch cleanup ---` block が 1 ファイル統合で記録される。

mock 試験 (cleanup-worktrees.sh + cleanup-claude-branches.sh の 2 つを
mock simulate) で log block が期待通り順次出力されることを確認。

Refs #708
EOF
```

---

## Task 7: docs/l2-workflow.md update

**目的**: §「worktree メンテナンス (#477)」内の関連箇所を更新し、新規 subsection を追加。

**Files:**

- Modify: `docs/l2-workflow.md` (4 箇所)

- [ ] **Step 1: Read current l2-workflow.md §「worktree メンテナンス (#477)」**

```bash
sed -n '555,600p' docs/l2-workflow.md
```

期待: line 555-600 に既存 section が見えている (Task 着手前の baseline 確認用)

- [ ] **Step 2: Modify §「自動実行 (Stop hook)」**

`docs/l2-workflow.md` line 561 (`セッション終了時に ... rmdir で除去する。`) を以下に Edit で置換:

old_string:

```text
セッション終了時に `.claude/hooks/stop.sh` が `scripts/cleanup-worktrees.sh --apply` を起動し、空ディレクトリを rmdir で除去する。`rmdir` のみを使うため未保存ファイルを含むディレクトリは絶対に削除されず、セッション中の作業が消失することはない。
```

new_string:

```text
セッション終了時に `.claude/hooks/stop.sh` が **2 つの cleanup script を順次起動**する:

1. `scripts/cleanup-worktrees.sh --apply` — 空ディレクトリを `rmdir` で除去 (非空 dir は touch しない)
2. `scripts/cleanup-claude-branches.sh --apply` — 安全 AND 条件を満たす `claude/*` ローカルブランチを `git branch -D` (#708)

両 script とも明示的に安全な条件下のみ操作するため、未保存ファイルや作業中ブランチが誤って消失することはない。
```

- [ ] **Step 3: Add new subsection §「branch cleanup の安全条件 (AND)」**

`docs/l2-workflow.md` 内の §「自動実行 (Stop hook)」の **直後** (= `### 手動実行` の直前) に Edit で挿入。

挿入位置の old_string (アンカー用):

```text
設定箇所: `.claude/settings.json` の `hooks.Stop` セクション。

### 手動実行
```

new_string:

```text
設定箇所: `.claude/settings.json` の `hooks.Stop` セクション。

### branch cleanup の安全条件 (AND)

`scripts/cleanup-claude-branches.sh --apply` が `git branch -D` で削除する条件 (#708):

- **merged**: `origin/develop-0.2.0` または `origin/main` の祖先 (`git merge-base --is-ancestor`)
- **active 参照なし**: `git worktree list --porcelain` の `branch refs/heads/...` 集合に含まれない
- **prefix 限定**: `claude/` のみ (= `feature/xxx` 等の手動 branch は対象外)
- **24h cooldown**: 最終 commit (`git log -1 --format=%ct`) が 24h 以上前

評価順序は AND 1 → AND 2 → AND 3。最初に fail した条件が `kept <branch> (reason: not-merged | active | cooldown)` の reason として記録される。

`origin/develop-0.2.0` / `origin/main` が未 fetch だと `merge-base --is-ancestor` が false に倒れて keep される = 安全側。`git fetch` は hook 内で実行せず、user の通常運用 (`git pull`) を前提とする。

### 手動実行
```

- [ ] **Step 4: Modify §「手動実行」の例コード**

`docs/l2-workflow.md` 内の §「手動実行」コードブロック (現状 cleanup-worktrees.sh のみ) を Edit で置換。

old_string:

```bash
# 削除候補を表示するだけ (dry-run, デフォルト)
scripts/cleanup-worktrees.sh

# 実際に rmdir を実行 (非空ディレクトリは触らない)
scripts/cleanup-worktrees.sh --apply
```

new_string:

```bash
# 削除候補を表示するだけ (dry-run, デフォルト)
scripts/cleanup-worktrees.sh
scripts/cleanup-claude-branches.sh

# 実際に rmdir / branch -D を実行 (安全条件を満たすもののみ)
scripts/cleanup-worktrees.sh --apply
scripts/cleanup-claude-branches.sh --apply
```

- [ ] **Step 5: Modify §「安全性」 (追記)**

`docs/l2-workflow.md` §「安全性」の最後に追記。

old_string (該当 section の末尾):

```text
Windows のディレクトリハンドル保持問題 (#477 コメント) は上記 2 段階設計により回避している。
```

new_string:

```text
Windows のディレクトリハンドル保持問題 (#477 コメント) は上記 2 段階設計により回避している。

`cleanup-claude-branches.sh` も同様に明示的に安全な AND 4 条件下でのみ `git branch -D` を実行し、merged 保証により data loss しない。`origin/develop-0.2.0` / `origin/main` が未 fetch なら `is-ancestor` false に倒れて keep する設計のため、fetch されていない開発環境でも安全に動作する。
```

- [ ] **Step 6: Run markdownlint to verify clean**

```bash
bash scripts/check-markdownlint.sh 2>&1 | grep 'docs/l2-workflow.md' | head -10
echo "exit=$(bash scripts/check-markdownlint.sh >/dev/null 2>&1; echo $?)"
```

Expected: `docs/l2-workflow.md` に errors なし (grep ヒット 0)、exit=0

- [ ] **Step 7: Commit**

```bash
git add docs/l2-workflow.md
git commit -F - <<'EOF'
docs(l2-workflow): §「worktree メンテナンス (#477)」に branch cleanup 追記 (Refs #708)

§「自動実行 (Stop hook)」: 2 script の順次起動を明示
新規 subsection §「branch cleanup の安全条件 (AND)」: merged / active /
prefix / cooldown の AND 評価順序と未 fetch 時の挙動を記載
§「手動実行」: 2 script の dry-run / --apply 例を併記
§「安全性」: branch cleanup も AND 4 条件下のみ動作し data loss しない旨追記

markdownlint clean 確認済。

Refs #708
EOF
```

---

## Task 8: Full 5-scenario self-test

**目的**: PR body の Self-Test Report に転載する evidence を取るため、5 シナリオを 1 つの tmp git repo に統合して実行し output を確認する。

**Files:**

- (no commit) `tmp/cleanup-branches-full-test/` 配下の tmp git repo

- [ ] **Step 1: Build a unified mock containing all 5 scenarios**

```bash
TMP=$(mktemp -d --suffix=-cleanup-full-test)
git -C "$TMP" init -q -b develop-0.2.0
git -C "$TMP" config user.email "test@test.local"
git -C "$TMP" config user.name "test"
echo "init" > "$TMP/README.md"
git -C "$TMP" add README.md
GIT_AUTHOR_DATE="$(date -d '48 hours ago' -Iseconds)" \
GIT_COMMITTER_DATE="$(date -d '48 hours ago' -Iseconds)" \
  git -C "$TMP" commit -q -m "old base"
OLD_TIP=$(git -C "$TMP" rev-parse HEAD)
echo "recent" >> "$TMP/README.md"
git -C "$TMP" add README.md
git -C "$TMP" commit -q -m "recent"
DEVELOP_TIP=$(git -C "$TMP" rev-parse HEAD)
git -C "$TMP" update-ref refs/remotes/origin/develop-0.2.0 "$DEVELOP_TIP"
# scenario 1: merged + 古い + active なし (= deleted)
git -C "$TMP" branch claude/foo "$OLD_TIP"
# scenario 2: not merged (= kept not-merged)
git -C "$TMP" checkout -q -b tmp-divergent "$OLD_TIP"
echo "divergent" > "$TMP/divergent.txt"
git -C "$TMP" add divergent.txt
GIT_AUTHOR_DATE="$(date -d '48 hours ago' -Iseconds)" \
GIT_COMMITTER_DATE="$(date -d '48 hours ago' -Iseconds)" \
  git -C "$TMP" commit -q -m "divergent"
git -C "$TMP" branch claude/bar
git -C "$TMP" checkout -q develop-0.2.0
git -C "$TMP" branch -D tmp-divergent
# scenario 3: active worktree が参照 (= kept active)
git -C "$TMP" branch claude/baz "$OLD_TIP"
git -C "$TMP" worktree add "$TMP-wt-baz" claude/baz >/dev/null
# scenario 4: merged + 新しい (= kept cooldown)
git -C "$TMP" branch claude/qux "$DEVELOP_TIP"
# scenario 5: prefix 違い (列挙対象外)
git -C "$TMP" branch feature/xxx "$OLD_TIP"
echo "TEST_DIR=$TMP"
```

- [ ] **Step 2: Run dry-run, capture output**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh") | tee /tmp/cleanup-branches-self-test-dryrun.txt
```

Expected output (要点、順不同):

```text
  would delete claude/foo
  kept claude/bar (reason: not-merged)
  kept claude/baz (reason: active)
  kept claude/qux (reason: cooldown)
summary: 1 deleted / 3 kept / 4 total
```

(`feature/xxx` が一切登場しないことを目視確認 = scenario 5 pass)

- [ ] **Step 3: Run --apply, capture output**

```bash
(cd "$TMP" && bash "$OLDPWD/scripts/cleanup-claude-branches.sh" --apply) | tee /tmp/cleanup-branches-self-test-apply.txt
```

Expected output:

```text
  deleted claude/foo
  kept claude/bar (reason: not-merged)
  kept claude/baz (reason: active)
  kept claude/qux (reason: cooldown)
summary: 1 deleted / 3 kept / 4 total
```

- [ ] **Step 4: Verify post-apply branch state**

```bash
echo "--- remaining claude/* branches: ---"
git -C "$TMP" branch --list 'claude/*'
echo "--- expect: claude/bar, claude/baz, claude/qux (3 件) ---"
```

Expected: `claude/bar`, `claude/baz`, `claude/qux` の 3 件が残存、`claude/foo` は消滅

- [ ] **Step 5: Tear down test fixtures**

```bash
git -C "$TMP" worktree remove --force "$TMP-wt-baz" 2>/dev/null || true
rm -rf "$TMP" "$TMP-wt-baz"
```

(no commit; この Task は evidence 取得が目的)

---

## Task 9: PR pre-flight + push + PR creation + iterate-review

**目的**: Iron Law 6 Pre-flight を実行し、PR を作成して `/iterate-review` で review-fix loop を回す。

**Files:**

- (no file changes) このタスクは git / gh コマンド実行のみ

- [ ] **Step 1: Pre-flight — fetch origin, check base sync**

```bash
git fetch origin develop-0.2.0
echo "--- HEAD..origin/develop-0.2.0 (取り込み未済 commit) ---"
git --no-pager log --oneline HEAD..origin/develop-0.2.0
echo "--- touched files ---"
git --no-pager diff --name-only origin/develop-0.2.0 HEAD
```

Expected: 取り込み未済 commit があれば touched files との交差を check。交差ありなら `git merge origin/develop-0.2.0` で取り込み + Task 8 を再実行。なしならそのまま進める。

- [ ] **Step 2: Pre-flight — parallel PR check**

```bash
gh pr list --search "708 in:body" --state all --repo Idios/kobutachan-allaganeye | head -10
gh pr list --search "cleanup-claude-branches in:body" --state all --repo Idios/kobutachan-allaganeye | head -10
```

Expected: 本 PR 以外に open PR が #708 を参照していないこと、`cleanup-claude-branches.sh` への並行修正 PR がないこと

- [ ] **Step 3: Push branch**

```bash
git push origin claude/exciting-mendel-e3daa1
```

Expected: push 成功 (本 branch は PR #707 で merged 済だが、新 commit が追加されているので新規 PR が作成可能)

- [ ] **Step 4: Create PR with HEREDOC body**

```bash
gh pr create --base develop-0.2.0 \
  --title "feat(scripts): #708 claude/* ブランチ自動削除機構の追加 (Refs #708)" \
  --body-file - <<'EOF'
## 概要

worktree session 終了時に `claude/*` ローカルブランチが残り続け **220 個** に膨れていた問題 (#708) を解消する。新 script `scripts/cleanup-claude-branches.sh` を新設し、Stop hook (`.claude/hooks/stop.sh`) から呼び出して安全 AND 条件 (merged + active なし + claude/ prefix + 24h cooldown) を満たす branch を自動削除する。

## 設計 doc

[`docs/superpowers/specs/2026-05-11-cleanup-claude-branches-design.md`](docs/superpowers/specs/2026-05-11-cleanup-claude-branches-design.md) で `/superpowers:brainstorming` により 7 軸 (trigger / safety / fetch / script 配置 / log / test / doc) を user 確認の上で確定。

## 実装計画

[`docs/superpowers/plans/2026-05-11-cleanup-claude-branches-implementation.md`](docs/superpowers/plans/2026-05-11-cleanup-claude-branches-implementation.md) で Task 1〜9 に分解 (TDD-style: mock setup → fail confirm → implement → pass confirm → commit)。

## 変更内容

- **Created**: [`scripts/cleanup-claude-branches.sh`](scripts/cleanup-claude-branches.sh) — dry-run / --apply 2 モード、AND 1/2/3 + claude/ prefix 判定、summary 出力
- **Modified**: [`.claude/hooks/stop.sh`](.claude/hooks/stop.sh) — cleanup-worktrees.sh block の後ろに新 script の output block を追加 (stop-hook.log 統合)
- **Modified**: [`docs/l2-workflow.md`](docs/l2-workflow.md) — §「worktree メンテナンス (#477)」内に branch cleanup 関連の段落 + 新規 subsection §「branch cleanup の安全条件 (AND)」を追加

## 安全性 / Iron Law 整合

- **Iron Law 2** (3 件以上の bulk は AskUserQuestion 必須) との整合: Stop hook 非対話だが、AND 4 条件で「明らかに安全な branch (merged + active なし + 24h 以上前 + claude/ prefix)」のみ自動削除に厳格限定
- **未 fetch 時の挙動**: `merge-base --is-ancestor` が false に倒れて keep → 安全側
- **削除失敗時の挙動**: per-branch ログに `delete failed: <branch>` 記録、hook 全体は exit 0 維持

## Self-Test Report

5 シナリオを tmp git repo で手動検証 (実装計画 Task 8):

- [x] **シナリオ 1** (merged + 古い + active なし) → `deleted claude/foo` 出力 + 実際に `branch -D` 実行確認
- [x] **シナリオ 2** (not merged) → `kept claude/bar (reason: not-merged)` 出力確認
- [x] **シナリオ 3** (active worktree が参照) → `kept claude/baz (reason: active)` 出力確認
- [x] **シナリオ 4** (24h cooldown 内、新しい commit) → `kept claude/qux (reason: cooldown)` 出力確認
- [x] **シナリオ 5** (prefix 違い `feature/xxx`) → 列挙対象外で出力なし確認
- [x] **stop.sh 統合 mock 試験** → `stop-hook.log` に `--- branch cleanup ---` block が `--- cleanup output ---` block の後ろに記録されることを確認
- [x] **markdownlint clean** → `bash scripts/check-markdownlint.sh` exit 0 確認
- [x] **bash -n syntax check** → `bash -n scripts/cleanup-claude-branches.sh` clean 確認
- 実機検証 (依頼): merge 後 1〜2 セッション運用 → main checkout で `git branch --list 'claude/*' | wc -l` の推移を確認し、220 から減少していることを Idios に確認していただく必要あり

## Path 別自動チェック

変更 path は bash scripts (`scripts/cleanup-claude-branches.sh` / `.claude/hooks/stop.sh`) + docs markdown (`docs/l2-workflow.md`)。Python (`ruff` / `pyright` / `pytest`) / GUI (`npm`) / installer pester は対象外。markdownlint は実行済。

## Scope 注記 (Iron Law 3)

- bats / pytest 化は本 PR の scope 外 (#710 hook test infra で扱う)
- H3 (Windows handle 保持) 関連の cleanup-worktrees.sh 改修は本 PR 外 (PR #707 merge 後の log 観測で確定後に別 issue 化)
- 動的な base branch 設定 (環境変数) は YAGNI

## 関連

- Refs #708 (本 issue)
- Refs #477 (`.claude/worktrees/` 残骸再発防止 元 issue / PR #493 で `cleanup-worktrees.sh` を追加)
- Refs PR #707 (Stop hook 診断ログ追加 — 本仕組みの log 統合先)
- Refs #710 (hook test infra + 構造化 cleanup output schema — 本 PR の手動 mock を test case 化する hand off 先)

session-id: exciting-mendel-e3daa1
🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

Expected: PR URL が `https://github.com/Idios/kobutachan-allaganeye/pull/<N>` で返ってくる

- [ ] **Step 5: Update #710 issue body with hand-off reference**

`/create-task` skill ではなく `gh issue edit` で本 PR の Self-Test 手順を test case 化対象として #710 に追記:

```bash
gh issue view 710 --repo Idios/kobutachan-allaganeye --json body -q '.body' > /tmp/issue-710-body.md
echo '' >> /tmp/issue-710-body.md
echo '---' >> /tmp/issue-710-body.md
echo '' >> /tmp/issue-710-body.md
echo "## test case 化対象の追加 (#708 / PR #<本PR> 由来)" >> /tmp/issue-710-body.md
echo '' >> /tmp/issue-710-body.md
echo 'PR #<本PR> で実装した `scripts/cleanup-claude-branches.sh` の手動 mock 5 シナリオ (実装計画 Task 8) を、本 issue の test framework 確立時に test case 化する。'  >> /tmp/issue-710-body.md
echo '' >> /tmp/issue-710-body.md
echo '対象シナリオ:' >> /tmp/issue-710-body.md
echo '1. merged + 古い + active なし → `deleted claude/foo`' >> /tmp/issue-710-body.md
echo '2. not merged → `kept ... (reason: not-merged)`' >> /tmp/issue-710-body.md
echo '3. active worktree が参照 → `kept ... (reason: active)`' >> /tmp/issue-710-body.md
echo '4. 24h cooldown 内 → `kept ... (reason: cooldown)`' >> /tmp/issue-710-body.md
echo '5. prefix 違い (`feature/xxx`) → 列挙対象外' >> /tmp/issue-710-body.md
echo '' >> /tmp/issue-710-body.md
echo '実装計画の Task 8 step 1 (mock setup one-liner) をそのまま fixture builder として参照可能。' >> /tmp/issue-710-body.md
gh issue edit 710 --repo Idios/kobutachan-allaganeye --body-file /tmp/issue-710-body.md
rm -f /tmp/issue-710-body.md
```

Expected: #710 body に hand-off reference 追記済

- [ ] **Step 6: Launch /iterate-review on the new PR**

```text
/iterate-review <本PR番号>
```

Expected: review-fix loop が走り、収束または divergence 検知で完了

---

## Self-Review Notes

### Spec coverage

| Spec section | 対応 Task |
| --- | --- |
| §4 アーキテクチャ (2 script を順次起動) | Task 6 (stop.sh 統合) |
| §5 データフロー (AND 1/2/3 評価) | Task 1-4 (各 AND 実装) |
| §6.1 cleanup-claude-branches.sh 仕様 | Task 1-5 |
| §6.2 stop.sh 変更 | Task 6 |
| §7 エラーハンドリング | Task 2 (active match), Task 3 (merge-base 失敗 = not-merged), Task 4 (log -1 失敗 = cooldown), Task 5 (branch -D 失敗 = delete failed) |
| §8.1 5 シナリオ手動検証 | Task 1 (scenario 5), Task 2 (3), Task 3 (1+2), Task 4 (4), Task 5 (1 with --apply), Task 8 (全 5 統合) |
| §8.2 #710 hand off | Task 9 step 5 |
| §9 doc 更新 (4 箇所) | Task 7 step 2-5 (4 Edit) |

### Placeholder scan

- 「<本PR>」プレースホルダ (Task 9 PR body / #710 hand-off) は PR 作成時点で番号が確定するので、その時点で具体化する明示的な late-binding (= 設計上必要なプレースホルダ、固定不可)。

### Type / interface consistency

- `cleanup-claude-branches.sh` の output 形式は全 Task で一貫: `would delete <branch>` / `deleted <branch>` / `kept <branch> (reason: <r>)` / `delete failed: <branch>` / `summary: <D> deleted / <K> kept / <T> total`
- reason 値の表記は `not-merged` / `active` / `cooldown` で全 Task 一致
- `--apply` flag 名は全 Task 一致

### Risk note

- Task 4 の `date -d '48 hours ago'` は GNU date (Linux / Git Bash for Windows) で動く。macOS BSD date では `-d` flag が異なるが、本 plan の実装環境は Windows + Git Bash (Idios 環境) 想定なので問題なし。
- Task 8 全シナリオ統合 mock は branch tip が完全 unique な commit を持つよう `tmp-divergent` を一旦作って branch 取得後削除する pattern を使う (clean tmp repo を保つため)。
