# claude/* ローカルブランチ自動削除機構 設計 (Refs #708)

**作成**: 2026-05-11
**Refs**: #708 (元 issue) / #477 (worktree dir cleanup 元 issue) / #710 (hook test infra)
**PR 関連**: #707 (Stop hook 診断ログ追加、本仕組みの log 統合先)

---

## 1. 概要

新 script `scripts/cleanup-claude-branches.sh` を新設し、Stop hook (`.claude/hooks/stop.sh`) から 2 つ目の呼び出しを行う。安全 AND 条件 (`merged` AND `active 参照なし` AND `claude/ prefix` AND `24h cooldown`) を満たす `claude/*` ローカルブランチを `git branch -D` で削除する。

既存 `scripts/cleanup-worktrees.sh` は一切触らず regression 0。`git worktree remove` が worktree dir のみ片付け branch には触れない仕様の補完として、worktree dir cleanup と同じ Stop hook 経由で branch cleanup も自動化する。

## 2. 背景 (Why)

`/iterate-review` PR #707 の調査過程で以下が判明:

- `.claude/worktrees/` 実物 dir: 27 個 / `git worktree list` active: 6 個
- 一方 `git branch --list 'claude/*'` は **220 個** 残存
- worktree dir 削除と branch 削除は別軸 (`git worktree remove` は branch に触れない仕様) のため、worktree cleanup が動いていても branch は溜まり続ける構造

ユーザー (Idios) 認識「worktree とブランチをクリーンアップする仕組み」と、現実装 (worktree dir のみ) の乖離を埋める。

## 3. 主要決定事項 (brainstorming 結果)

| 軸 | 決定 |
| --- | --- |
| Trigger | **Stop hook 自動削除** (非対話) |
| Safety AND セット | `is-ancestor(origin/develop-0.2.0 OR origin/main)` AND `active 参照なし` AND `24h cooldown` (列挙 filter: `claude/` prefix 限定) |
| `git fetch` | hook 内では走らせない (user の通常 `git pull` 運用前提、未 fetch なら is-ancestor false で keep = 安全側) |
| Script 配置 | 別 script `scripts/cleanup-claude-branches.sh` を新設 (SRP / 既存 cleanup-worktrees.sh は touched せず) |
| Log 統合 | PR #707 で追加した `.claude/state/stop-hook.log` に `--- branch cleanup ---` block を追記 (1 ファイル統合) |
| テスト | ad-hoc mock で進め、本格 test framework 化は #710 (hook test infra) に hand off |
| Doc 更新 | `docs/l2-workflow.md` §「worktree メンテナンス (#477)」内に subsection 追加 |

## 4. アーキテクチャ

```text
Stop hook 発火
   ↓
.claude/hooks/stop.sh (PR #707 で診断ログ追加済の構造を拡張)
   ├─ Step 1 (既存): bash scripts/cleanup-worktrees.sh --apply
   │     → stop-hook.log に `--- cleanup output ---` block
   │
   └─ Step 2 (新規): bash scripts/cleanup-claude-branches.sh --apply
         → stop-hook.log に `--- branch cleanup ---` block
```

設計上の核:

- **責務分離 (SRP)**: 1 script = 1 責任。dir cleanup と branch cleanup を別 script に。
- **`git common dir` 解決**: 既存 `cleanup-worktrees.sh` と同じく `git rev-parse --git-common-dir` で main checkout root を解決し、worktree path から呼ばれても main checkout の branch を操作。
- **fetch なし**: hook 内で `git fetch` は走らせず、user の通常運用 (`git pull` / `git fetch`) を前提。未 fetch なら `is-ancestor` false に倒れる = 安全側 (削除しない)。

## 5. データフロー

```text
[Stop hook 発火]
   ↓
[stop.sh:
   - $CLAUDE_PROJECT_DIR / REPO_ROOT 解決
   - .claude/state/stop-hook.log にヘッダ追記]
   ↓
[Step 1: cleanup-worktrees.sh --apply]  ← 既存、PR #707 修正済
   - git worktree prune
   - .claude/worktrees/ scan → orphan rmdir
   - 出力を `--- cleanup output ---` block へ
   ↓
[Step 2 (NEW): cleanup-claude-branches.sh --apply]
   - git -C $main_root branch --list 'claude/*' → 対象 enumerate
   - git -C $main_root worktree list --porcelain → active 参照集合
   - 各 claude/<name> を **評価順 AND 2 → AND 1 → AND 3** で判定 (cost-efficient: AND 2 は local hash lookup で安価、AND 1/3 は git subprocess を spawn):
       AND 2 (1st check): ∉ active 参照集合
       AND 1 (2nd check): is-ancestor(develop-0.2.0) OR is-ancestor(main)
       AND 3 (3rd check): log -1 ct < (now - 24*3600)
       → all satisfy: git branch -D
       → any fail:    keep (reason: not-merged | active | cooldown)
   - per-branch 結果 + summary を出力
   - 出力を `--- branch cleanup ---` block へ
   ↓
[stop.sh exit 0]
```

## 6. コンポーネント仕様

### 6.1 `scripts/cleanup-claude-branches.sh` (新規)

#### 呼び出し

```bash
scripts/cleanup-claude-branches.sh           # dry-run (default)
scripts/cleanup-claude-branches.sh --apply   # 実削除
scripts/cleanup-claude-branches.sh -h        # help
```

#### 動作

1. `git rev-parse --git-common-dir` → main checkout root を解決 (worktree path から呼ばれても OK)
2. `git -C $ROOT worktree list --porcelain` を parse して `refs/heads/<branch>` 集合を作成 (active 参照集合)
3. `git -C $ROOT branch --list 'claude/*' --format='%(refname:short)'` で対象 branch 列挙
4. 各 `claude/<name>` について判定 (**評価順序: AND 2 → AND 1 → AND 3** — cost-efficient: AND 2 は local hash lookup で安価、AND 1 / AND 3 は git subprocess を spawn するため後回し。最初に fail した時点で評価終了し、その条件名を reason に確定):
   - **AND 1 (merged)**: `git -C $ROOT merge-base --is-ancestor "<branch>" "origin/develop-0.2.0"` OR `... "origin/main"` (いずれか成功で OK)。両方とも非 ancestor / 両方とも ref 未存在の場合 fail → reason `not-merged`
   - **AND 2 (active 不在)**: active 参照集合に `refs/heads/<branch>` が含まれない。含まれる場合 fail → reason `active`
   - **AND 3 (cooldown)**: `git -C $ROOT log -1 --format=%ct "<branch>"` (unix timestamp) が `$(date +%s) - 86400` より小さい (= 24h より前)。新しい場合 fail → reason `cooldown`
5. 全 AND 満足:
   - `--apply` あり: `git -C $ROOT branch -D "<branch>"` → 出力 `deleted <branch>`
   - dry-run: 出力 `would delete <branch>`
6. 1 つでも fail: 出力 `kept <branch> (reason: not-merged | active | cooldown)` (最初に fail した条件を reason)
7. 末尾に `summary: <D> deleted / <K> kept / <T> total` を出力

#### exit code

- 0: 正常終了
- 1: 引数エラー
- 2: not a git repo
- (削除失敗は 0 維持: hook 全体を妨げない)

### 6.2 `.claude/hooks/stop.sh` 変更 (既存ファイル拡張)

PR #707 の構造 (`output=$(...); rc=$?` パターン、Round 1 fix 適用済) を踏襲し、`cleanup-worktrees.sh` の block と並列に `branch cleanup` block を追加。

差分概要 (実装段階で確定):

```bash
# 既存
SCRIPT="$REPO_ROOT/scripts/cleanup-worktrees.sh"
# 追加
SCRIPT_BRANCHES="$REPO_ROOT/scripts/cleanup-claude-branches.sh"
```

ログブロックに `--- branch cleanup ---` セクションを追加 (内部構造は `cleanup-worktrees.sh` ブロックと対称)。

## 7. エラーハンドリング

| 状況 | 動作 |
| --- | --- |
| `cleanup-claude-branches.sh` 不存在 | `stop.sh` 側 `[[ -f $SCRIPT_BRANCHES ]]` で skip、hook continue (cleanup-worktrees.sh と同じ defensive pattern) |
| `git rev-parse --git-common-dir` 失敗 | script exit 2 / `stop.sh` log に exit code 2 記録して continue |
| `origin/develop-0.2.0` / `origin/main` が ref 未存在 (= 未 fetch) | `merge-base --is-ancestor` が 1 (= not ancestor) で返る → keep (`not-merged`) → **安全側** |
| `git log -1` 失敗 (broken branch ref) | cooldown 判定不能 = keep (`cooldown` reason) → 安全側 |
| `git branch -D` 失敗 (例: HEAD と同じ branch / 何らかの protection) | per-branch ログに `delete failed: <branch> (exit=N)` 記録、次の branch に continue、全体 exit 0 |
| log file 書き込み失敗 (`.claude/state/` permission denied 等) | `stop.sh` `>>"$LOG" 2>/dev/null \|\| true` でスワロー、stderr の既存契約は維持 |
| 220 branch 一気処理の性能 | per-branch 判定 < 0.1s × 220 ≈ 22s。初日のみ、以降は 24h cooldown により 1 セッション数件 |

## 8. テスト方針

### 8.1 本 PR 内 (ad-hoc mock)

`scripts/cleanup-claude-branches.sh` 実装後、`tmp/cleanup-branches-test/` に tmp git repo を作って以下 5 シナリオを手動検証:

| # | シナリオ | 期待動作 |
| --- | --- | --- |
| 1 | merged + 古い + active なし | `deleted claude/foo` |
| 2 | not merged (develop-0.2.0 / main の祖先でない) | `kept claude/bar (reason: not-merged)` |
| 3 | active worktree が参照 | `kept claude/baz (reason: active)` |
| 4 | 24h cooldown 内 (新しい commit) | `kept claude/qux (reason: cooldown)` |
| 5 | prefix 違い (`feature/xxx`) | 列挙対象外で出力なし |

PR body Self-Test Report に上記 5 シナリオの実行結果を `- [x]` で記載。

### 8.2 #710 への hand off

bats / pytest 化は #710 (hook test infra + 構造化 cleanup output schema) の scope。本 PR 内では手動 mock 手順を本 spec doc に明文化し、#710 issue body にも「PR #<本PR> の手動 mock を test case 化対象」と追記する。

## 9. doc 更新

`docs/l2-workflow.md` §「worktree メンテナンス (#477)」(line 555-600) に以下を反映:

### 9.1 §「自動実行 (Stop hook)」更新

現状:

> セッション終了時に `.claude/hooks/stop.sh` が `scripts/cleanup-worktrees.sh --apply` を起動し、空ディレクトリを rmdir で除去する。

変更後 (案):

> セッション終了時に `.claude/hooks/stop.sh` が **2 つの cleanup script を順次起動**します:
>
> 1. `scripts/cleanup-worktrees.sh --apply`: 空 dir を rmdir
> 2. `scripts/cleanup-claude-branches.sh --apply`: 安全条件を満たす `claude/*` branch を `git branch -D`

### 9.2 新規 subsection §「branch cleanup の安全条件 (AND)」

`claude/*` branch を自動削除する AND 条件:

- **merged**: `origin/develop-0.2.0` または `origin/main` の祖先
- **active 参照なし**: `git worktree list` 内で参照されていない
- **prefix 限定**: `claude/` のみ (= namespace 限定で `feature/xxx` 等は対象外)
- **24h cooldown**: 最終 commit が 24h 以上前

`origin/develop-0.2.0` / `origin/main` が未 fetch だと `is-ancestor` が false に倒れて keep される。user の通常 `git pull` 運用を前提に、`git fetch` は hook 内で実行しない。

### 9.3 §「手動実行」更新

dry-run と `--apply` の各 script 例を併記。

### 9.4 §「安全性」追記

> branch 削除も AND 3 条件 (merged + active 参照なし + 24h cooldown) + `claude/` prefix 限定下で実行され、merged 保証により data loss しない。fetch されていない remote ref は `is-ancestor` false に倒れて keep (= 安全側)。

## 10. Scope 外 (本 PR で扱わない)

- **bats / pytest 化** → #710 で hand off
- **H3 (Windows handle 保持) 関連の `cleanup-worktrees.sh` 改修** → PR #707 merge 後の `.claude/state/stop-hook.log` 観測で確定後に別 issue 化
- **動的な base branch 設定 (環境変数)** → YAGNI (release のたびに hook コード書き換えと環境変数書き換えは手間が同じ)
- **`claude/*` 以外の branch (`feature/`, `fix/` 等) の cleanup** → namespace 限定で意図的に scope 外

## 11. Iron Law との整合

| Iron Law | 整合方針 |
| --- | --- |
| 1 (NO PR MERGE WITHOUT ALL ACCEPTANCE CRITERIA CHECKED) | PR body の Self-Test Report に 5 シナリオ実行結果を逐条記載 |
| 2 (NO BULK OPERATION WITHOUT AskUserQuestion CONFIRMATION) | Stop hook は非対話だが、AND 3 条件 (merged + active なし + 24h cooldown) + `claude/` prefix 限定で「明らかに安全な branch」のみ自動削除する設計に厳格限定することで Iron Law 2 の趣旨 (= ユーザー意図に反する破壊的操作を防ぐ) と整合 |
| 3 (NO SCOPE CREEP WITHOUT NEW ISSUE) | bats / pytest 化や H3 関連改修は本 PR scope 外、#710 / 別 issue で扱う旨を明記 |
| 4 (NO Closes / Fixes / Resolves KEYWORDS) | PR 本文 / commit message は `Refs #708` 形式 |
| 5 (NO INDEPENDENT JUDGMENT ON AMBIGUOUS POINTS) | brainstorming で trigger / safety / base / log / test / doc / script 配置 の 7 軸を AskUserQuestion で逐条確認済 |
| 6 (NO PR CREATION WITHOUT VERIFIED CHECKS) | bash script のみのため Python / GUI / installer pester 対象外、`bash -n` syntax check + ad-hoc mock 5 シナリオを実行 |

## 12. 関連

- Refs #708 (本 issue)
- Refs #477 (`.claude/worktrees/` 残骸再発防止 元 issue / PR #493 で `cleanup-worktrees.sh` 追加)
- Refs PR #707 (Stop hook 診断ログ追加、本仕組みの log 統合先)
- Refs #710 (hook test infra + 構造化 cleanup output schema、test の本格化先)

session-id: exciting-mendel-e3daa1
