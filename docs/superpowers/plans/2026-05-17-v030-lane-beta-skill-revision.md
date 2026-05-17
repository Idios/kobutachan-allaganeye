# L-β skill 改訂 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** retro spec の L-β (skill 改訂) を 5 PR で実装。M3 (subagent 起動規約 audit) / M5 (同 issue 既存 PR 検出) / M9 (`/release` Step 0a/0b/0c deferred 全件検証) / C2+C3 (Codex review skill 内 invocation) / C4+C6 skeleton (codex:rescue + fallback) を完成させる。同時に L-γ の docs (A1 / A2 / M2 / M10) への skill 側参照リンクを picking up する。

**Architecture:** 各 PR は単独 reviewable。β-1 (M3 audit) → β-2 (M5 + L-γ doc 参照) → β-3 (M9) → β-4 (Codex C2/C3/C4) → β-5 (C6 fallback) の順で依存性を考慮した着手順。β-1 で template 規約を確立すると、β-2 以降で skill を編集するときに同 template を準拠させやすい。

**Tech Stack:** Markdown (SKILL.md / docs) + Bash (session-start.sh patches) + git + markdownlint-cli2

**Spec reference:** [docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md](../specs/2026-05-17-v020-v021-retro-codex-integration-design.md) §M3 / §M5 / §M9 / §C2 / §C3 / §C4 / §C6

**Worktree:** `E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\nervous-hoover-464244` (branch: `claude/nervous-hoover-464244`, base: `develop-0.3.0`)

---

## File Structure

| 種別 | path | 担当 Task |
| --- | --- | --- |
| 更新 | `.claude/skills/review-pr/SKILL.md` | Task 1 / 2 / 4 / 5 |
| 更新 | `.claude/skills/iterate-review/SKILL.md` | Task 1 / 2 / 5 |
| 更新 | `.claude/skills/close-issue/SKILL.md` | Task 1 (subagent template audit) |
| 更新 | `.claude/skills/release/SKILL.md` | Task 3 |
| 更新 | `.claude/skills/scope-guard/SKILL.md` | Task 4 |
| 更新 | `.claude/skills/create-task/SKILL.md` | Task 2 (Track 構造参照) |
| 更新 | `.claude/hooks/session-start.sh` | Task 4 (Iron Law 6 Step 5 追記) |
| 更新 | `docs/l2-workflow.md` | Task 4 / 5 (Pre-flight Step 5 + Codex fallback §新設) |
| 更新 | `CLAUDE.md` | Task 4 (Codex 運用 § 新設) |
| 更新 | `docs/markdownlint-guide.md` | Task 2 (skill 側参照経路の更新) |

---

## Pre-flight (実装開始前に 1 回)

- [ ] **Step 0.1: base 同期 + status**

```bash
git fetch origin develop-0.3.0
git status
```

Expected: working tree clean、ahead by N。

- [ ] **Step 0.2: 既存 skill 一覧確認**

```bash
ls .claude/skills/ 2>&1
```

Expected: review-pr / iterate-review / close-issue / create-task / scope-guard / release / enforce-acceptance-criteria の 7 skill。

- [ ] **Step 0.3: spec §M3 / §M5 / §M9 / §C2-§C4 / §C6 を read**

```bash
sed -n '/^#### M3:/,/^#### M4:/p' docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md | wc -l
```

Expected: 数十行 hit。

---

## Task 1 (PR β-1, M3): subagent 起動規約の既存 skill audit

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md`
- Modify: `.claude/skills/iterate-review/SKILL.md`
- Modify: `.claude/skills/close-issue/SKILL.md`

### 設計判断

`docs/l2-workflow.md` §subagent 起動規約 は既に commit 5602f8e (L-γ M2 ではなく前 commit) で存在。本 PR では既存 project skill 内の **subagent dispatch を行う箇所**を grep で抽出し、HARD-GATE template (Stop conditions / action_safety / report 規約) が記載されているか audit、不備があれば追記する。

template 構造:

```text
## Stop conditions (必須)
- Predefined scope を超える発見 → STOP, report BLOCKED with finding details
- 想定外 finding に対する独断 fix 禁止 (scope expansion は controller 判断)

## Report 規約 (必須)
- self-confirm: scope 外の独断行動なし
- BLOCKED 報告の format: {status, reason, would_have_done}
```

### 実装手順

- [ ] **Step 1.1: 既存 skill 内の subagent dispatch 行を grep**

```bash
grep -nE "subagent|Agent\(|Task tool|dispatch|empirical-prompt-tuning" .claude/skills/**/SKILL.md 2>&1 | head -40
```

各 hit 箇所を Read で確認し、HARD-GATE 記述の有無を audit。

- [ ] **Step 1.2: `/review-pr` skill の subagent dispatch を確認**

review-pr SKILL.md には Step 5 で `requesting-code-review` subagent (code quality 委譲) を呼ぶ箇所がある。当該 prompt に Stop conditions / action_safety / report 規約が記載されているか確認。

不備があれば該当 section に `docs/l2-workflow.md §subagent 起動規約` への明示参照 + HARD-GATE template 引用を追記。

- [ ] **Step 1.3: `/iterate-review` skill の subagent dispatch を確認**

iterate-review は `/review-pr` を fresh subagent で起動する。Step 2.2 付近の dispatch 行で Stop conditions / report 規約を確認、不備なら追記。

- [ ] **Step 1.4: `/close-issue` skill の subagent dispatch を確認**

close-issue が subagent を起動するか確認 (Step 1 grep 結果による)。dispatch を行うなら template 準拠を audit。

- [ ] **Step 1.5: markdownlint check**

```bash
npx --prefix gui markdownlint-cli2 .claude/skills/review-pr/SKILL.md .claude/skills/iterate-review/SKILL.md .claude/skills/close-issue/SKILL.md
```

Expected: 0 error。

- [ ] **Step 1.6: PR β-1 commit**

```bash
git add .claude/skills/review-pr/SKILL.md .claude/skills/iterate-review/SKILL.md .claude/skills/close-issue/SKILL.md
git commit -m "$(cat <<'EOF'
refactor(skills): subagent dispatch を docs/l2-workflow.md §subagent 起動規約 に準拠 (Refs spec L-β M3)

retro spec §M3 の実装。F6 (PR #732 8eff1d2 scope creep) / F7 (#741 cda0f8e
orphan commit) の hook 化を補完するため、既存 skill 内の subagent dispatch
prompt に HARD-GATE template (Stop conditions / action_safety / report 規約)
を audit。不備があった箇所を docs/l2-workflow.md §subagent 起動規約 への
明示参照 + template 引用で補強。

audit 対象: /review-pr Step 5 (requesting-code-review 委譲) / /iterate-review
Step 2.2 (fresh subagent dispatch) / /close-issue (subagent 利用箇所)。

memory feedback_subagent_dispatch_stop_on_scope_creep / feedback_subagent_orphaned_commit
の skill 側 hook 昇格。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 (PR β-2, M5 + L-γ doc 参照): 同 issue 既存 PR 検出 + L-γ doc skill 側参照

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (Step 1 + Step 5a/5b 編集)
- Modify: `.claude/skills/iterate-review/SKILL.md` (Round 内警告併走)
- Modify: `.claude/skills/scope-guard/SKILL.md` (refactor-pattern.md 参照)
- Modify: `.claude/skills/create-task/SKILL.md` (release-process Track 構造参照)
- Modify: `docs/markdownlint-guide.md` (header note の skill 側参照を「予定」→「実装済」更新)

### 設計判断

M5 (同 issue 既存 PR 検出) は `/review-pr` Step 1 (PR 取得) で元 issue # を解決後に `gh pr list --search "<issue#>" --state merged --limit 10` を実行し、件数 ≥1 なら Step 5b トリアージ表の冒頭に警告行を追加する。block ではなく警告のみ (spec O2 (a) 確定値)。

同時に L-γ で作成した docs (A1 refactor-pattern / A2 release-process Track / M2 外部依存規約 / M10 markdownlint-guide) の skill 側参照経路を完成させる:

- `/review-pr` Step 5 (logic/docs 整合性): M2 外部依存規約 を installer/workflow PR に引く
- `/review-pr` Step 5a (gap 分析): A1 refactor-pattern を大規模 PR 判定に引く
- `/review-pr` Step 5b (triage): M10 markdownlint-guide を MD028/MD056/MD060 fix に引く
- `/iterate-review` Step 2.4 (A 修正): M10 markdownlint-guide を MD violation の fix recipe に引く
- `/scope-guard`: A1 refactor-pattern を Phase 分割判断に引く
- `/create-task`: A2 release-process Track 構造 を patch issue 起票時に引く

### 実装手順

- [ ] **Step 2.1: `/review-pr` SKILL.md Step 1 に同 issue 既存 PR 検出を追加**

review-pr SKILL.md Step 1 (PR 取得) 末尾に以下のような subsection を追加:

```markdown
#### 同 issue 過去 PR 検出 (M5)

元 issue # を解決した直後に過去 PR 件数を確認:

\`\`\`bash
gh pr list --search "<issue#>" --state merged --limit 10
\`\`\`

件数 ≥1 (本 PR 以外に同 issue を fix した merged PR が既存) なら、Step 5b トリアージ表の冒頭に警告行を必ず追加:

「同 issue で過去に merged PR `<N>` 件あります (PR #..., #...)。前回 fix の root cause が今回の変更で完全解消しているか、Step 5 / 5a で重点的に確認してください」

意図的な multi-phase 分割 (例: AppError migration #663→#689→#714 系) の場合は元 issue の本文/コメントで明示確認し、警告を「意図的分割と確認済」として処置。block / threshold は設けない (spec O2 (a) 確定値)。
```

- [ ] **Step 2.2: `/review-pr` SKILL.md Step 5 / 5a / 5b に L-γ doc 参照を追加**

各 Step で:

- Step 5: PR の touched files に installer / workflow 系を含むなら `docs/l2-workflow.md` §外部依存規約 (M2) を引いて URL 規約適合を逐条検証
- Step 5a (gap 分析): PR が大規模 (touched > 30 file or diff > 1000 line) なら `docs/refactor-pattern.md` (A1) §4 判定基準を引いて Phase 分割すべきだった可能性を triage 表 (B) trigger 候補に挙げる
- Step 5b (triage): markdownlint violation を triage に含めるとき、fix recipe (MD028 / MD056 / MD060 等) は `docs/markdownlint-guide.md` (M10) §typical fixes を参照

- [ ] **Step 2.3: `/iterate-review` SKILL.md に M5 警告併走 + M10 参照を追加**

Round 2.2 (subagent return → main session) で M5 警告を併走 (review-pr Step 1 の subagent return 後に main session が再度表示)。

Step 2.4 (A 修正、markdownlint fail 含む) に `docs/markdownlint-guide.md` (M10) §typical fixes へのリンクを追加。

- [ ] **Step 2.4: `/scope-guard` SKILL.md に A1 refactor-pattern 参照を追加**

scope-guard が scope 拡大検知時に 3 択を提示するが、大規模 refactor が scope 拡大の真因の場合は Phase 分割を選択肢として `docs/refactor-pattern.md` (A1) §4 を引く。

- [ ] **Step 2.5: `/create-task` SKILL.md に A2 release-process Track 構造参照を追加**

create-task が patch release 用 issue を起票する際、`docs/release-process.md` §Patch release の Track 構造 (A2) に対応する prefix label / scope label を判定するための参照を追加。

- [ ] **Step 2.6: `docs/markdownlint-guide.md` header の skill 側参照を「実装済」に更新**

既存 header (Lane γ-3 commit 5602f8e で挿入):

```markdown
- `/review-pr` skill Step 5b トリアージ (L-β で追加予定)
- `/iterate-review` skill Step 2.4 (L-β で追加予定)
```

を以下に書き換え:

```markdown
- `/review-pr` skill Step 5b トリアージ (本 PR β-2 で実装済)
- `/iterate-review` skill Step 2.4 (本 PR β-2 で実装済)
```

- [ ] **Step 2.7: 全 markdownlint pass + commit**

```bash
npx --prefix gui markdownlint-cli2 .claude/skills/review-pr/SKILL.md .claude/skills/iterate-review/SKILL.md .claude/skills/scope-guard/SKILL.md .claude/skills/create-task/SKILL.md docs/markdownlint-guide.md
```

Expected: 0 error。

```bash
git add .claude/skills/review-pr/SKILL.md .claude/skills/iterate-review/SKILL.md .claude/skills/scope-guard/SKILL.md .claude/skills/create-task/SKILL.md docs/markdownlint-guide.md
git commit -m "$(cat <<'EOF'
feat(skills): 同 issue 過去 PR 検出 + L-γ doc 参照経路完成 (Refs spec L-β M5)

retro spec §M5 の実装 + L-γ A1 / A2 / M2 / M10 の skill 側参照完成。

/review-pr SKILL.md:
- Step 1 末尾に「同 issue 過去 PR 検出」subsection 追加。元 issue # 解決
  直後に gh pr list --search "<#>" --state merged --limit 10、件数 ≥1 で
  Step 5b 冒頭に警告行を追加 (spec O2 (a) block しない確定)
- Step 5: M2 docs/l2-workflow.md §外部依存規約 への参照 (installer/workflow PR 用)
- Step 5a: A1 docs/refactor-pattern.md §4 判定基準 への参照 (大規模 PR 用)
- Step 5b: M10 docs/markdownlint-guide.md §typical fixes への参照

/iterate-review SKILL.md:
- M5 警告併走 (subagent return 後 main session で再表示)
- Step 2.4 で M10 markdownlint-guide §typical fixes 参照

/scope-guard SKILL.md:
- A1 docs/refactor-pattern.md §4 を Phase 分割判断選択肢として参照

/create-task SKILL.md:
- A2 docs/release-process.md §Patch release Track 構造 を patch issue 起票時に参照

docs/markdownlint-guide.md:
- header の skill 側参照経路を「L-β で追加予定」→「本 PR β-2 で実装済」に更新

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 (PR β-3, M9): `/release` skill Step 0a/0b/0c 再設計

**Files:**

- Modify: `.claude/skills/release/SKILL.md`

### 設計判断

spec M9 (再設計版、2026-05-17 D1 確定) の通り `/release` skill の Step 0 を 3 サブステップに分割:

- Step 0a: 既存受け入れゲート (docs/release-process.md レイヤーリリース受け入れゲート)
- Step 0b: `gh issue list --label deferred --state open --limit 200` で deferred 全件取得
- Step 0c: 各 issue を 1 件ずつ user に提示し (a) 次 release 吸収 / (b) deferred 継続 / (c) close の 3 択分類。件数 ≥3 は Iron Law 2 bulk pre-check 後に個別調整

結果は spec PR (Track 0) の table に保存し、Track B 吸収候補の追跡可能性を確保。

### 実装手順

- [ ] **Step 3.1: 既存 `/release` SKILL.md の Step 0 を Read**

```bash
sed -n '/^## .*Step 0\|^### Step 0/,/^## \|^### /p' .claude/skills/release/SKILL.md | head -50
```

Step 0 の現在構造を把握 (おそらく「受け入れゲート確認」のみ)。

- [ ] **Step 3.2: Step 0 を Step 0a / 0b / 0c に分割**

既存 Step 0 を Step 0a (rename) として保持し、Step 0b と Step 0c を新規追加:

```markdown
### Step 0a: レイヤーリリース受け入れゲート (既存)

(従来の Step 0 内容)

### Step 0b: deferred 全件取得 (M9、F8 教訓)

\`\`\`bash
gh issue list --label deferred --state open --limit 200 --json number,title,labels,createdAt,updatedAt
\`\`\`

Expected: 数十件 (v0.M cycle 中に蓄積された deferred issue)。0 件なら 0c skip。

### Step 0c: deferred 1 件ずつ 3 択分類

各 deferred issue を user に提示し、AskUserQuestion で:

- (a) 次 release 吸収 (本 patch / minor で Track B 候補)
- (b) deferred 継続 (次 cycle に再評価)
- (c) close (won't fix / 再現不能 / 仕様変更等)

件数 ≥3 の場合は Iron Law 2 (bulk operation) に従い、サンプル 1 件提示 + 「全件 OK / 個別調整 / やめる」3 択 を先に取る。「個別調整」選択時のみ 1 件ずつの確認に進む。

判定結果は spec PR (Track 0) に table として保存:

\`\`\`markdown
### §deferred 全件検証結果 (`/release` Step 0c)

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #374 | ... | (a) 次 patch 吸収 | UX critical |
| #432 | ... | (b) deferred 継続 | L3 scope |
| #555 | ... | (c) close | 再現不能 |
\`\`\`

(a) と分類された issue 群が `docs/release-process.md` §Patch release の Track 構造 (A2) の Track B 吸収候補。

### Step 0c で block する条件

- deferred 件数 > 0 かつ Step 0c の確認が完了していない → release PR 作成を block
- (a) 分類 issue 群が次 release scope に取り込まれる commit / PR plan を持たない → block (`/iterate-review` / `/create-task` で Track B の plan を先に作る)
```

- [ ] **Step 3.3: markdownlint check + commit**

```bash
npx --prefix gui markdownlint-cli2 .claude/skills/release/SKILL.md
```

```bash
git add .claude/skills/release/SKILL.md
git commit -m "$(cat <<'EOF'
refactor(skill): /release Step 0 を 0a/0b/0c に分割 (Refs spec L-β M9)

retro spec §M9 (2026-05-17 D1 再設計版) の実装。release-blocker label は
撤回 (M8 撤回) し、release 前に deferred 全件検証する設計に一本化。

Step 0a (既存): レイヤーリリース受け入れゲート
Step 0b (新規): gh issue list --label deferred --state open --limit 200 で全件取得
Step 0c (新規): 1 件ずつ (a) 次release吸収 / (b) deferred 継続 / (c) close 分類
  - 件数 ≥3 は Iron Law 2 bulk pre-check (サンプル + 全件OK/個別/やめる) 経由
  - 結果を spec PR (Track 0) の table に保存 → Track B 吸収候補追跡

F8 (deferred 持ち越し) の根本対策。docs/release-process.md §Patch release
の Track 構造 (A2) と連携。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 (PR β-4, C2 + C3 + C4): Codex 統合 (review gate / rescue)

**Files:**

- Modify: `.claude/hooks/session-start.sh` (Iron Law 6 Step 5 追記)
- Modify: `docs/l2-workflow.md` (§PR 作成 Pre-flight に Step 5 詳細)
- Modify: `.claude/skills/review-pr/SKILL.md` (Step 5a に optional `/codex:review`)
- Modify: `CLAUDE.md` (§Codex 運用 新設、§バグ修正時の方針 に `/codex:rescue` 運用ルール)
- Modify: `.claude/skills/scope-guard/SKILL.md` (Codex commit 検査範囲拡張)

### 設計判断

spec O1 (b) / O5 (b) 確定値に沿う:

- C1 (review gate ON 全 turn) は採用しない。代わりに `/review-pr` `/iterate-review` 内で明示 invocation
- C2: Iron Law 6 Pre-flight Step 5 (`/codex:adversarial-review`) を session-start.sh と docs/l2-workflow.md に追記
- C3: `/review-pr` Step 5a に optional `/codex:review` (deep dive 起動条件付き)
- C4: `/codex:rescue` を root-cause 専用に絞り、scope-guard で囲む

### 実装手順

- [ ] **Step 4.1: session-start.sh Iron Law 6 の Pre-flight 表記に Step 5 を追記**

`.claude/hooks/session-start.sh` の Iron Law 6 内 `**PR 作成 Pre-flight** ...` 行 (現在は Step 0-4) を以下に書き換え:

```text
**PR 作成 Pre-flight (#659 で運用化、#722 で Step 0 ハードゲート追加、L-β β-4 で Step 5 Codex adversarial pass 追加)**: Step 0 = `gh pr list --search "<元issue#>" --state open` でハードゲート (<1s、build/verify の前) → Step 1 base 同期 (`git fetch origin <base>`) → Step 2 取り込み未済 commit (`git log HEAD..origin/<base>`) → Step 3 touched files 交差判定 → Step 4 並行 PR 重複再確認 (`gh pr list --search "<元issue#>" --state all`) → Step 5 `/codex:adversarial-review` (focus 文字列で Iron Law 3 / encoding / GPU fallback / 同 issue 過去 PR root cause を疑う、C2)。詳細は `docs/l2-workflow.md` §「PR 作成 Pre-flight」 を参照
```

- [ ] **Step 4.2: docs/l2-workflow.md の PR 作成 Pre-flight 関連 § に Step 5 詳細を追記**

`docs/l2-workflow.md` の PR 作成 Pre-flight を扱う § (既存) に Step 5 詳細を追記:

```markdown
### Step 5: /codex:adversarial-review (Codex 統合、C2)

Pre-flight Step 0-4 完了後、PR 作成直前に Codex で adversarial pass を行う:

\`\`\`bash
/codex:adversarial-review --base develop-X.Y.Z --focus "<focus 文字列>"
\`\`\`

focus 文字列 (project 固有焦点):
- Iron Law 3 (scope creep) を疑え。touched files が元 issue の宣言 scope と整合するか
- ffmpeg / GPU fallback / encoding boundary を疑え (F1 / F4 再発を阻止)
- 同 issue 過去 PR の root cause が今回も残っていないか (M5 と協調)

Codex finding は Claude が triage し、(A) 本 PR 修正 / (B)(C) handoff のいずれかに振り分け。「BLOCK」相当の指摘でも Codex 自身に commit させない (M3 整合)。Codex が token 枯渇等で fail した場合は **C6 fallback** (本 docs 後段 §Codex fallback、本 plan β-5 で追加) に沿う。
```

- [ ] **Step 4.3: `/review-pr` SKILL.md Step 5a に optional `/codex:review` を追加**

review-pr SKILL.md Step 5a (gap 分析) に以下の subsection を追加:

```markdown
#### optional /codex:review (Codex 統合、C3)

以下のいずれかを満たす PR で `/codex:review --base develop-X.Y.Z` を併走させる (人手 trigger or skill 内 auto):

- PR diff が大きい (touched > 15 file or > 500 lines)、または
- 過去 root cause が複数 (M5 警告 ≥2 件)、または
- L1 (CLI / detector / GPU) の core ロジック変更を含む

Codex の finding は Step 5b triage 表に「出所 = codex:review」と記載して統合。Codex に直接 commit させない (M3 整合)。token 枯渇で fail した場合は C6 fallback (`docs/l2-workflow.md` §Codex fallback) に沿う。
```

- [ ] **Step 4.4: CLAUDE.md に §Codex 運用 を新設**

CLAUDE.md の §Plugin との関係 (override 宣言) の直後あたりに以下を追加:

```markdown
## Codex 運用

Codex (openai-codex プラグイン 1.0.4) を Iron Law 3 / 5 と衝突しない形で workflow に統合する。設計原則: **Codex は adversarial second-opinion 専用、自身に独断 fix させない**。

### review / adversarial-review (C2 / C3)

- 全 turn 自動の Stop-time review gate は **OFF のまま**保持 (spec O1 (b) 確定)
- 代わりに `/review-pr` (Step 5a) と `/iterate-review` 内で明示 invocation
- Iron Law 6 Pre-flight Step 5 として `/codex:adversarial-review` を必ず実行

### rescue (C4)

- `/codex:rescue` は **root-cause 調査専用** (spec O5 (b) 確定、常用禁止)
- 機能実装 / refactor / docs 改修等の default invocation は禁止
- 使う場合は rescue prompt に `<action_safety>` で「scope を超える finding → 独断 fix 禁止、BLOCKED 報告」を必ず明記 (M3 整合)
- `--write` default のままだが、Codex が write する場合は staging のみ、commit / push は controller の明示指示後
- rescue 完了後、Idios に finding を提示し AskUserQuestion で「本 PR 修正 / 別 issue / 無視」の 3 択
- `/scope-guard` skill が Codex commit (`git log --author=...codex...`) を検査範囲に含める

### Token 枯渇時の fallback (C6)

詳細は [docs/l2-workflow.md §Codex fallback](docs/l2-workflow.md#codex-fallback) を参照。
```

- [ ] **Step 4.5: CLAUDE.md §バグ修正時の方針 に `/codex:rescue` 運用ルール短文を追記**

既存 §バグ修正時の方針 末尾 (encoding boundary checklist の直後) に 1 段落追加:

```markdown
#### `/codex:rescue` 限定使用 (C4、spec O5 (b) 確定)

根本原因分析 / 類似バグ調査 phase で `/codex:rescue` を限定的に併用してよい。常用は禁止。詳細は §Codex 運用 §rescue を参照。
```

- [ ] **Step 4.6: `/scope-guard` SKILL.md に Codex commit 検査範囲を追加**

scope-guard SKILL.md の検査範囲 § (existing) に以下を追加:

```markdown
### Codex commit 検査範囲 (C4)

`/codex:rescue` が `--write` で commit を作った場合、scope 外の独断 fix がないか scope-guard が検査する:

\`\`\`bash
git log --author='codex\|Codex' --oneline -10
\`\`\`

該当 commit があれば scope check に含める (本 skill §Step 3 の検査対象に加える)。
```

- [ ] **Step 4.7: markdownlint + bash syntax + commit**

```bash
npx --prefix gui markdownlint-cli2 docs/l2-workflow.md .claude/skills/review-pr/SKILL.md .claude/skills/scope-guard/SKILL.md CLAUDE.md
bash -n .claude/hooks/session-start.sh && echo "session-start.sh OK"
```

```bash
git add .claude/hooks/session-start.sh docs/l2-workflow.md .claude/skills/review-pr/SKILL.md .claude/skills/scope-guard/SKILL.md CLAUDE.md
git commit -m "$(cat <<'EOF'
feat(workflow): Codex 統合 — Pre-flight Step 5 / review-pr Step 5a / rescue 運用ルール (Refs spec L-β C2/C3/C4)

retro spec §C2 / §C3 / §C4 の実装。Codex は adversarial second-opinion 専用、
自身に独断 fix させない設計 (Iron Law 3/5/6 整合)。spec O1 (b) / O5 (b)
確定値に沿う。

session-start.sh:
- Iron Law 6 の Pre-flight 表記に Step 5 (/codex:adversarial-review) を追加

docs/l2-workflow.md:
- §PR 作成 Pre-flight に Step 5 詳細 (focus 文字列例 / triage / fallback 言及)

.claude/skills/review-pr/SKILL.md:
- Step 5a に optional /codex:review subsection 追加 (起動条件 / triage 統合)

CLAUDE.md:
- §Codex 運用 新設 (review/adversarial-review/rescue/fallback の運用集約)
- §バグ修正時の方針 に /codex:rescue 限定使用の短文追記

.claude/skills/scope-guard/SKILL.md:
- 検査範囲に Codex commit (git log --author='codex|Codex') を追加 (C4)

C6 fallback の詳細 (検出条件 / 戦略 / 必須記載) は L-β β-5 で別 PR で追加。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 (PR β-5, C6): Codex fallback skeleton

**Files:**

- Modify: `docs/l2-workflow.md` (§Codex fallback 新設)
- Modify: `.claude/skills/review-pr/SKILL.md` (Step 5a Codex 併走部分に return code 判定 + fallback 分岐)
- Modify: `.claude/skills/iterate-review/SKILL.md` (Round 内 Codex 経路 fallback 分岐)

### 設計判断

spec C6 の通り、Codex CLI が rate-limit / quota / network / auth で fail した場合、Claude Code 側で superpowers:requesting-code-review (review) / systematic-debugging (rescue) を fallback として起動する。fallback notice を skill report に必須記載 (Iron Law 5 整合)。

### 実装手順

- [ ] **Step 5.1: docs/l2-workflow.md に §Codex fallback を新設 (§参考 の直前)**

```markdown
## Codex fallback (C6、Codex token 枯渇 / failure 時)

Codex CLI (`codex-companion.mjs` runtime) が以下のいずれかで fail した場合、Claude Code 側で同等処理を fallback 実行する。Iron Law 1 / 6 違反 (受け入れ条件検証 / Pre-flight ゲート不通過のまま進行) を防ぐ。

### 検出条件

| 検出条件 | 判定 |
| --- | --- |
| exit code 非ゼロ + stderr に `rate.?limit`, `quota`, `429`, `usage_limit` のいずれか | **token 枯渇 (明確)** → 自動 fallback |
| exit code 非ゼロ + stderr に `auth`, `unauthorized`, `401`, `403`, `api.?key` | **認証失敗 (明確)** → 自動 fallback + user notify |
| exit code 非ゼロ + stderr に `timeout`, `EHOSTUNREACH`, `ENETUNREACH`, `ECONNRESET` | **network failure (明確)** → 自動 fallback |
| exit code 非ゼロ + 上記いずれにも該当しない stderr | **曖昧** → user に AskUserQuestion (再試行 / Claude fallback / abort) |
| exit code 0 + stdout が空 / parse 不能 | **応答異常** → user に AskUserQuestion |

### Fallback 戦略

| Codex command | 通常用途 | Fallback 内容 |
| --- | --- | --- |
| `/codex:review` (C3 で `/review-pr` Step 5a に invoke) | code quality adversarial pass | superpowers `requesting-code-review` subagent を起動して同等の adversarial review |
| `/codex:adversarial-review` (C2 で Iron Law 6 Step 5 に invoke) | Pre-flight 第 5 ゲート | superpowers `requesting-code-review` subagent + project 固有 focus を起動 |
| `/codex:rescue` (C4 で root-cause 調査時に invoke) | bug 根本原因 + 類似バグ探索 | Claude main + superpowers `systematic-debugging` skill で自力調査 |

### Fallback 実行時の必須記載 (Iron Law 5 整合)

skill report (review 報告 / Round summary comment) に以下を**必ず明示**:

\`\`\`text
> **Codex fallback notice**: 本 review は Codex CLI が <検出条件> で fail したため、
> Claude Code (superpowers:<skill-name>) で代替実行しました。
> Codex 側の review は次セッションで再試行を推奨します。
> stderr 要約: <stderr の先頭 200 字>
\`\`\`

これがないと Idios が Codex review 済と誤認するリスクがある。

### Fallback の限界

- Codex は GPT-5.4 (独立 model) の second opinion。Claude Code fallback は同一 model の self-review に近く、bias 構造が同じになる
- 重要 PR (release 直前 / 大規模 refactor) で Codex fallback が trigger した場合、user に AskUserQuestion で「Codex 復旧待ち / Claude fallback で push」の 3 択を提示
```

- [ ] **Step 5.2: `/review-pr` SKILL.md Step 5a Codex 併走部分に return code 判定 + fallback 分岐を追加**

review-pr SKILL.md Step 5a の `optional /codex:review` subsection に以下の skeleton を追加:

```markdown
##### Codex fail 時の fallback 手順

Codex CLI が exit code 非ゼロを返した場合、`docs/l2-workflow.md` §Codex fallback の検出条件 table に従い:

1. stderr を keyword match (rate-limit / quota / 429 / auth / timeout etc.) で分類
2. 明確な failure → 自動 fallback: superpowers `requesting-code-review` subagent を起動 (Codex 用 focus 文字列を流用)
3. 曖昧 → user に AskUserQuestion (再試行 / Claude fallback / abort) 3 択
4. fallback 実行時は Step 6 レビュー報告に「Codex fallback notice」を必須記載 (template は docs/l2-workflow.md §Codex fallback 参照)
```

- [ ] **Step 5.3: `/iterate-review` SKILL.md Round 内 Codex 経路に fallback 分岐を追加**

iterate-review SKILL.md の Round 2.2 (subagent dispatch) 内、Codex 利用部分があれば return code 判定 + fallback 分岐を追加。詳細は `docs/l2-workflow.md` §Codex fallback を参照。

- [ ] **Step 5.4: markdownlint + commit**

```bash
npx --prefix gui markdownlint-cli2 docs/l2-workflow.md .claude/skills/review-pr/SKILL.md .claude/skills/iterate-review/SKILL.md
```

```bash
git add docs/l2-workflow.md .claude/skills/review-pr/SKILL.md .claude/skills/iterate-review/SKILL.md
git commit -m "$(cat <<'EOF'
feat(workflow): Codex fallback skeleton (Refs spec L-β C6)

retro spec §C6 の実装 (D2 確定)。Codex token 枯渇 / failure 時に Iron Law 1 / 6
違反を防ぐため、Claude Code 側で fallback を起動する設計を docs と skill に追加。

docs/l2-workflow.md:
- §Codex fallback 新設
  - 検出条件 table (exit code + stderr keyword で 5 分類)
  - Fallback 戦略 table (review / adversarial-review → requesting-code-review
    subagent、rescue → systematic-debugging skill)
  - 必須記載 (Codex fallback notice template、Iron Law 5 整合)
  - 限界の明示 (bias 構造同一化、重要 PR は AskUserQuestion 3 択)

.claude/skills/review-pr/SKILL.md:
- Step 5a optional /codex:review subsection に「Codex fail 時の fallback 手順」
  追加 (keyword match → 自動 fallback / 曖昧 → AskUserQuestion 3 択)

.claude/skills/iterate-review/SKILL.md:
- Round 内 Codex 経路に fallback 分岐リンク (docs/l2-workflow.md §Codex fallback 参照)

C1 (review gate OFF 維持) / C2 / C3 / C4 は L-β β-4 で実装済。本 PR で C6 完成形。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Lane 完了後の最終確認

- [ ] **Step 6.1: branch HEAD に 5 commit (β-1 / β-2 / β-3 / β-4 / β-5)**

```bash
git log --oneline -10
```

- [ ] **Step 6.2: 全 markdownlint + pytest hooks pass**

```bash
bash scripts/check-markdownlint.sh
python -m pytest tests/hooks/ -v
```

- [ ] **Step 6.3: 次の Lane (L-δ) 移行判断**

L-β 完了で残りは L-δ (Codex 統合運用化、2 PR)。L-β で C2 / C3 / C4 / C6 を skill 側に組み込み済のため、L-δ は CLAUDE.md / docs/l2-workflow.md の運用文書集約と C5 (superpowers subagent → Codex 直列構成) の doc 化が中心。

---

## 受け入れ基準 (L-β 全体)

spec §M3 / §M5 / §M9 / §C2 / §C3 / §C4 / §C6 の skill 側完成形をすべて満たす:

- [x] 既存 skill 内 subagent dispatch に HARD-GATE template 準拠 (M3)
- [x] `/review-pr` Step 1 に同 issue 過去 PR 検出、Step 5b 警告行 (M5)
- [x] `/release` skill Step 0a / 0b / 0c に分割 (M9)
- [x] session-start.sh Iron Law 6 に Pre-flight Step 5 追記 (C2)
- [x] `/review-pr` Step 5a に optional `/codex:review` (C3)
- [x] CLAUDE.md §Codex 運用 + `/scope-guard` Codex commit 検査 (C4)
- [x] `docs/l2-workflow.md` §Codex fallback + skill 側 fallback skeleton (C6)
- [x] L-γ doc (A1 / A2 / M2 / M10) への skill 側参照経路完成

## リスクと緩和策

| # | リスク | 緩和 |
| --- | --- | --- |
| RL1 | M3 audit で大幅 prompt 改修が必要になり 1 PR が膨らむ | β-1 は audit + 最小修正に絞り、大幅改修が必要なら別 PR (β-1-bis) に分割 |
| RL2 | /release Step 0c の AskUserQuestion 件数が多すぎる (deferred 50+ 件) | 件数 ≥3 は Iron Law 2 bulk pre-check (サンプル + 全件OK/個別/やめる) で吸収 |
| RL3 | C6 fallback skeleton は実装試験できない (Codex 実機 fail を起こす必要がある) | docs / skill の skeleton まで実装、実機検証は L-δ で実施 |
| RL4 | C2/C3 の Codex invocation を skill 内で組み込むと Codex 未導入環境で skill が破綻 | fallback (C6) を介して superpowers subagent に倒れるため graceful。Codex 未インストール時は最初から fallback 経路を辿る |

---

## 次の Lane plan 作成 tasks (L-β 完了後に着手)

- `docs/superpowers/plans/2026-05-17-v030-lane-delta-codex-ops.md` (C1 / C5 / C6 最終運用化)
