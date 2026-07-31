# L2 Lane IV-c Group H Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** v0.2.0 wave 0 の Lane IV-c (Group H = lint / CLI 系 polish) を 2 PR 構成で完了させる。Phase 1 = ESLint で Tauri 2 silent loss を予防 (#643)、Phase 2 = CLI progress bar の ETA ラベル付与 (#365)。

**Architecture:** Phase 1 は ESLint flat config の `rules` block に `no-restricted-globals` + `no-restricted-properties` を追加し、`window.confirm/alert/prompt` の bare global と member access の両経路を block。Phase 2 は `_eta_progressbar` を `_ETAProgressBar(_ClickProgressBar)` subclass + `format_progress_line()` override に refactor し、4 bar (Detecting / Refining / Scorebar / Splitting) で `NN% ETA: H:MM:SS` 形式に統一。

**Tech Stack:** ESLint v9 flat config (Phase 1) / Click 8.x ProgressBar (Phase 2) / pytest parametrize + regex (Phase 2 test) / `superpowers:test-driven-development` HARD-GATE 適用 (Phase 2)

**Spec:** [docs/superpowers/specs/2026-05-08-l2-lane-ivc-group-h-design.md](../specs/2026-05-08-l2-lane-ivc-group-h-design.md)

---

## Phase 1: 章 1 — #643 ESLint Tauri 2 silent loss 予防

### Task 1: PR Pre-flight + branch 切り (Iron Law 6)

**Files:** (なし、git 操作のみ)

- [ ] **Step 1: 取り込み未済 commit を確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 0 commit (取り込み未済なし) または develop-0.2.0 に新規 commit があるかを確認。新規があれば touched files (`gui/eslint.config.js`, `docs/ui-interaction-spec.md`) と交差するかを判定し、交差するなら Step 2 で merge する。

- [ ] **Step 2: 必要に応じて base 同期**

交差ありなら:

```bash
git merge origin/develop-0.2.0
```

交差なしなら skip。

- [ ] **Step 3: 並行 worktree PR 重複確認**

```bash
gh pr list --search "643 in:title,body" --state all
```

Expected: 既存 PR が無いこと (もしあれば本 plan を中止して既存 PR の状態を確認)。

- [ ] **Step 4: branch 切り (origin/develop-0.2.0 から派生明示、worktree branch の plan/spec commits を取り込まないこと)**

```bash
git switch -c claude/musing-davinci-38136f-eslint origin/develop-0.2.0
```

Expected: branch 切り替え完了。`git log --oneline origin/develop-0.2.0..HEAD` が空 (ahead-by-0)。

**注意**: worktree session の現在 branch (`claude/musing-davinci-38136f`) には plan/spec commits が含まれているため、`git switch -c <new-branch>` だけだとそれらを inherit してしまう。`origin/develop-0.2.0` を明示することで Phase 1 の PR scope を本質的な実装変更のみに保つ (Iron Law 3 担保)。Unit P1-A 実行時に同問題で markdownlint FAIL + plan/spec docs scope creep を発生させた経緯あり (rebase で fix 済)。

---

### Task 2: ESLint rules + docs 追加

**Files:**

- Modify: `gui/eslint.config.js` (既存 24 行に rules を追記)
- Modify: `docs/ui-interaction-spec.md` (§1.3 末尾に段落追加)

- [ ] **Step 1: `gui/eslint.config.js` を edit**

Edit tool で以下の `old_string` → `new_string` 置換:

`old_string`:

```js
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
    },
  },
```

`new_string`:

```js
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // #643: Tauri 2 WebView2 disables window.confirm/alert/prompt as no-op.
      // Catch both bare global calls and `window.X` member access.
      // See docs/ui-interaction-spec.md §1.3.
      'no-restricted-globals': [
        'error',
        {
          name: 'confirm',
          message:
            'Tauri 2 WebView2 disables window.confirm. Use `import { ask } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          name: 'alert',
          message:
            'Tauri 2 WebView2 disables window.alert. Use `import { message } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          name: 'prompt',
          message:
            'Tauri 2 WebView2 disables window.prompt. Use plugin-dialog equivalents instead. See docs/ui-interaction-spec.md §1.3.',
        },
      ],
      'no-restricted-properties': [
        'error',
        {
          object: 'window',
          property: 'confirm',
          message:
            'Tauri 2 WebView2 disables window.confirm. Use `import { ask } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          object: 'window',
          property: 'alert',
          message:
            'Tauri 2 WebView2 disables window.alert. Use `import { message } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          object: 'window',
          property: 'prompt',
          message:
            'Tauri 2 WebView2 disables window.prompt. Use plugin-dialog equivalents instead. See docs/ui-interaction-spec.md §1.3.',
        },
      ],
    },
  },
```

- [ ] **Step 2: `docs/ui-interaction-spec.md` §1.3 末尾段落追加**

Edit tool で以下:

`old_string`:

```markdown
**アンチパターン**: dirty=true なのに confirm せず遷移する設計 (#589 修正前の `PreviewScreen` の handleBack / handleExport が該当、現在は §2.4.1 / §2.4.14 経由で §1.3 準拠 + canonical 文言統一済)。

### 1.4 sample mode (filePath==null) の read-only 明示
```

`new_string`:

```markdown
**アンチパターン**: dirty=true なのに confirm せず遷移する設計 (#589 修正前の `PreviewScreen` の handleBack / handleExport が該当、現在は §2.4.1 / §2.4.14 経由で §1.3 準拠 + canonical 文言統一済)。

**lint 強制 ([#643](https://github.com/Idios/kobutachan-allaganeye/issues/643))**: 上記 canonical 違反 (`window.confirm` / `window.alert` / `window.prompt` の bare 呼び出しおよび `window.X` 経由 member access) は `gui/eslint.config.js` の `no-restricted-globals` + `no-restricted-properties` で **error として block** する。`npm run lint` / CI gui-frontend job が fail し、IDE 上でも即時警告される。エラーメッセージに plugin-dialog 代替 API へのリンクを含める。

### 1.4 sample mode (filePath==null) の read-only 明示
```

---

### Task 3: ローカル自動チェック (Iron Law 6 path 別自動チェック)

**Files:** (検査のみ)

- [ ] **Step 1: 依存確認**

```bash
cd gui && npm install --no-audit --no-fund
```

Expected: `package-lock.json` に変更なし、no install ops needed (新規依存追加なし)。

- [ ] **Step 2: ESLint で既存 src/ が新 rule で全 PASS することを確認**

```bash
cd gui && npm run lint
```

Expected: exit 0、`gui/src/` 配下に違反なし (既存コードは PR #628 commit `cc94f1f` 以降 plugin-dialog 経由のみで、`window.confirm` 等は説明コメント内のみ)。

もし違反が出た場合は **Stop** して原因を分析。実コードに `window.confirm` / `confirm()` 等が残存している場合は本 plan の前提が崩れている (spec の §1.1 background が誤り) ため Idios に報告。

- [ ] **Step 3: TypeScript 型チェック**

```bash
cd gui && npm run typecheck
```

Expected: exit 0 (eslint config 変更は TS 型に影響なし)。

- [ ] **Step 4: GUI vitest**

```bash
cd gui && npm test
```

Expected: 全 PASS (eslint config は test runtime に影響なし)。

- [ ] **Step 5: vite build**

```bash
cd gui && npm run build
```

Expected: exit 0、`gui/dist/` 生成。

- [ ] **Step 6: Rust 型チェック**

```bash
cd gui/src-tauri && cargo check
```

Expected: exit 0 (Rust 側は変更なし、参照のみ)。

---

### Task 4: commit + PR #1 作成

**Files:** (commit + push + PR)

- [ ] **Step 1: 変更を確認**

```bash
git status --short
git diff --stat
```

Expected: `gui/eslint.config.js` と `docs/ui-interaction-spec.md` の 2 file 変更のみ。

- [ ] **Step 2: commit**

```bash
git add gui/eslint.config.js docs/ui-interaction-spec.md
git commit -m "$(cat <<'EOF'
feat(gui): ESLint で window.confirm/alert/prompt を block (Refs #643)

Tauri 2 WebView2 の security 制約により window.confirm/alert/prompt が
no-op になる silent loss 問題 (PR #628 で実体修正済) を、lint レベルで
予防する rule を追加して再発防止する。

## 変更内容

### gui/eslint.config.js

src/**/*.{ts,tsx} block の rules に以下を追加:

- no-restricted-globals: bare global の confirm() / alert() / prompt() を
  block。代替 API (@tauri-apps/plugin-dialog の ask / message) と
  docs/ui-interaction-spec.md §1.3 リンクを含むエラーメッセージ
- no-restricted-properties: window.confirm() / window.alert() /
  window.prompt() の member access 経路も block。同上のメッセージ

### docs/ui-interaction-spec.md §1.3

末尾に「lint 強制 (#643)」段落を追加。canonical 違反は ESLint で error
として block される旨と、CI / IDE での挙動を明文化。

## CI fail evidence

別途検証 PR を立てて CI lint が exit 1 + 6 violation 報告で fail する
ことを CI run URL で実証する (machine-verified evidence、Self-Test
Report 末尾に追記予定)。

## 受け入れ条件マッピング

- [x] gui/eslint.config.js に no-restricted-globals 相当の rule 追加
- [x] エラーメッセージに plugin-dialog 代替 API + ui-interaction-spec.md §1.3 リンク
- [x] CI grep check 不要判断 (理由: ESLint で IDE + CI 両方カバー、grep はコメント false positive)
- [x] docs/ui-interaction-spec.md §1.3 末尾に lint 強制段落追加

session-id: musing-davinci-38136f

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

<!-- Note: machine-verified の `[x]` チェックは PR body のみで管理し、commit message には include しない。Task 5 Step 8 / Task 6 で PR body 側の検証 PR CI evidence を更新すること。 -->

Expected: commit 成功、`[claude/musing-davinci-38136f-eslint <hash>]` 表示。

- [ ] **Step 3: push**

```bash
git push -u origin claude/musing-davinci-38136f-eslint
```

Expected: branch push 成功。

- [ ] **Step 4: PR #1 body を一時ファイルに書き出す (Task 6 で再利用するため named file 経由)**

```bash
mkdir -p .git/plan-tmp
cat > .git/plan-tmp/pr1_body.md <<'EOF'
## 概要

Tauri 2 WebView2 の security 制約により `window.confirm/alert/prompt` が no-op になる silent loss 問題 (PR #628 で実体修正済) を、lint レベルで予防する rule を追加する。bare global と `window.X` member access の両経路を block する。

## 変更ファイル

- `gui/eslint.config.js`: `no-restricted-globals` + `no-restricted-properties` を `src/**/*.{ts,tsx}` block に追加
- `docs/ui-interaction-spec.md`: §1.3 末尾に「lint 強制 (#643)」段落追加

## 受け入れ条件マッピング (Iron Law 1)

issue [#643](https://github.com/Idios/kobutachan-allaganeye/issues/643) の受け入れ条件 5 項目を逐条検証:

- [x] `gui/eslint.config.js` に `no-restricted-globals` 相当の rule 追加
  → `gui/eslint.config.js` の `src/**/*.{ts,tsx}` block の `rules` 内、`no-restricted-globals` (3 globals) + `no-restricted-properties` (3 globals × `object: 'window'`) として追加
- [x] エラーメッセージに plugin-dialog 代替 API + `docs/ui-interaction-spec.md` §1.3 リンクを含める
  → 各 rule の `message` field に「Use \`import { ... } from "@tauri-apps/plugin-dialog"\`」+ 「See docs/ui-interaction-spec.md §1.3」を含む
- [ ] 故意に `window.confirm` を含むコードを書いた branch で CI lint が fail することを確認
  → 別途検証 PR を立てて CI run URL evidence を本 PR Self-Test Report 末尾に追記する (Step 5)
- [x] CI grep check を併設するか判断 → **不要**判断
  → 理由: ESLint で IDE 警告 + CI fail を兼ね、grep はコメント / docstring 内の言及まで誤検出する (現状 `gui/src/screens/PreviewScreen.tsx:445` と `gui/src/components/RestoreButton.tsx:9` の説明コメント内 `window.confirm` がそれにあたる)
- [x] `docs/ui-interaction-spec.md` §1.3 末尾に「lint で強制」記述を追加
  → 「**lint 強制 (#643)**」段落を §1.3 末尾に追加

## Self-Test Report

### machine-verified

- [x] `cd gui && npm run lint` (新 rule で `gui/src/` 全 PASS)
- [x] `cd gui && npm run typecheck`
- [x] `cd gui && npm test`
- [x] `cd gui && npm run build`
- [x] `cd gui/src-tauri && cargo check`

### machine-unverifiable

(なし、Idios 実機検証不要)

## 関連

- 派生元 PR: [#628](https://github.com/Idios/kobutachan-allaganeye/pull/628) (#589 修正、commit `cc94f1f` で `window.confirm` → plugin-dialog ask 一括 migrate)
- 親 issue: [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) (PreviewScreen state mutation flow + dirty consume confirm)
- 関連 doc: `docs/ui-interaction-spec.md` §1.3 (silent loss 防止: dirty consume 側で confirm)
- spec: `docs/superpowers/specs/2026-05-08-l2-lane-ivc-group-h-design.md` §4

session-id: musing-davinci-38136f

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

Expected: `.git/plan-tmp/pr1_body.md` に body が書き出される (Task 6 Step 2 で sed で書き換えて再投稿する)。

- [ ] **Step 5: PR #1 を作成**

```bash
gh pr create --base develop-0.2.0 --head claude/musing-davinci-38136f-eslint --title "feat(gui): ESLint で window.confirm/alert/prompt を block (Refs #643)" --body-file .git/plan-tmp/pr1_body.md
```

Expected: PR 作成成功、PR URL 出力。**PR 番号を記録** (以降の step で `#684` と参照)。

- [ ] **Step 6: CI 待機 + PASS 確認**

```bash
gh pr checks #684 --watch
```

Expected: 全 job PASS (`python` / `gui-frontend` / その他)。失敗が出た場合は失敗 job log を確認し、原因を切り分け。

---

### Task 5: 違反検証 PR で CI fail evidence 取得

**Files:**

- Create: `gui/src/__verify_eslint_643__.tsx` (検証 branch のみ、close 後削除)

- [ ] **Step 1: 検証 branch を切る**

```bash
git switch -c claude/musing-davinci-38136f-eslint-verify
```

Expected: branch 切り替え (Task 4 の commit を継承)。

- [ ] **Step 2: 違反コードファイル作成**

Write tool で `gui/src/__verify_eslint_643__.tsx`:

```tsx
// gui/src/__verify_eslint_643__.tsx
//
// This file is intentionally invalid for ESLint verification of #643.
// It MUST be deleted (along with the verification PR being closed without
// merge) once CI fail evidence is captured. Do not merge this file into
// any long-lived branch.

export function _verify643(): void {
  // Bare global calls (no-restricted-globals)
  confirm('bare global confirm');
  alert('bare global alert');
  prompt('bare global prompt');

  // window.X member access (no-restricted-properties)
  window.confirm('member access confirm');
  window.alert('member access alert');
  window.prompt('member access prompt');
}
```

- [ ] **Step 3: ローカルで lint fail を確認**

```bash
cd gui && npm run lint
```

Expected: exit 1、6 errors 報告 (`no-restricted-globals` 3 件 + `no-restricted-properties` 3 件)。それぞれ message に plugin-dialog 代替 + `§1.3` リンクが含まれること。

- [ ] **Step 4: commit + push**

```bash
git add gui/src/__verify_eslint_643__.tsx
git commit -m "$(cat <<'EOF'
test: verify ESLint blocks Tauri 2 silent loss patterns (Refs #643)

This commit intentionally introduces 6 violations of the no-restricted-globals
+ no-restricted-properties rules added in PR #684 to demonstrate that CI
gui-frontend lint job blocks the violations.

This branch / PR is for CI fail evidence ONLY and MUST NOT be merged.
After CI run captures the 6 violations as failure, the PR will be closed
without merge and the verification file deleted.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin claude/musing-davinci-38136f-eslint-verify
```

Expected: push 成功。

- [ ] **Step 5: 検証 PR 作成**

```bash
gh pr create --base develop-0.2.0 --head claude/musing-davinci-38136f-eslint-verify --title "test: verify ESLint blocks Tauri 2 silent loss patterns (Refs #643, expected to fail CI)" --body-file - <<'EOF'
## 目的

PR #684 (Refs #643) で追加した `no-restricted-globals` + `no-restricted-properties` rule が、`window.confirm/alert/prompt` の bare global / member access 両経路を CI で block することを **CI fail evidence** として記録する検証 PR。

## ⚠️ この PR は merge しない

`gui/src/__verify_eslint_643__.tsx` に 6 件の違反コードを意図的に追加してある。CI gui-frontend lint job が exit 1 + 6 errors を報告することを確認したら、本 PR は **close without merge** する (実装は本流 PR #684 で merge)。

## 期待する CI 挙動

- `gui-frontend` job の `npm run lint` step が exit 1
- 6 violations 報告:
  - `no-restricted-globals`: `confirm` / `alert` / `prompt` 各 1 件 (合計 3)
  - `no-restricted-properties`: `window.confirm` / `window.alert` / `window.prompt` 各 1 件 (合計 3)
- 各 message に `@tauri-apps/plugin-dialog` 代替 API と `docs/ui-interaction-spec.md` §1.3 リンクが含まれる

## 関連

- 本流 PR: #684
- spec: `docs/superpowers/specs/2026-05-08-l2-lane-ivc-group-h-design.md` §6.2

session-id: musing-davinci-38136f-eslint-verify
EOF
```

Expected: PR 作成成功、PR URL + 番号を記録 (以降 `#685`)。

- [ ] **Step 6: CI 結果待機 (FAIL を期待)**

```bash
gh pr checks #685 --watch
```

Expected: `gui-frontend` job が **FAIL**。Other jobs (`python` 等) は PASS で OK (Python 側に変更なし)。

- [ ] **Step 7: CI fail log で 6 violations を確認**

```bash
gh pr view #685 --json statusCheckRollup --jq '.statusCheckRollup[] | select(.conclusion == "FAILURE")'
# failed_job_id を gh api で取得してから log を確認:
FAILED_JOB_ID=$(gh pr view '#685' --json statusCheckRollup --jq '.statusCheckRollup[] | select(.conclusion == "FAILURE") | .databaseId' | head -1)
gh run view --log-failed --job="$FAILED_JOB_ID" | grep -E '(no-restricted-globals|no-restricted-properties)' | head -20
```

Expected: 6 行 (各違反 1 行)、または該当 job log で 6 errors の詳細を確認。CI run URL を記録 (Task 6 で本流 PR Self-Test Report に追記)。

- [ ] **Step 8: 検証 PR を close without merge**

```bash
gh pr close #685 --comment "$(cat <<'EOF'
CI fail evidence captured: gui-frontend lint job reports 6 violations
(3 no-restricted-globals + 3 no-restricted-properties) as expected.

# 以下は本 plan 実行時に記録された実数 URL を引用 (historical record)。
# 新規 plan で再利用する場合は実行時の URL に書き換える必要あり。
CI run URL: https://github.com/Idios/kobutachan-allaganeye/actions/runs/25529744519

Closing this verification PR without merge. The actual rule additions
are merged via PR #684. The verification file
gui/src/__verify_eslint_643__.tsx is contained to this branch and is
not propagated to develop-0.2.0.
EOF
)"
```

Expected: PR closed (state: CLOSED, not MERGED)。

---

### Task 6: 本流 PR #1 の Self-Test Report に CI evidence URL を追記

**Files:** Modify `.git/plan-tmp/pr1_body.md` (Task 4 Step 4 で書き出し済)、その後 `gh pr edit --body-file` で再投稿

- [ ] **Step 1: 本流 branch に戻る**

```bash
git switch claude/musing-davinci-38136f-eslint
```

- [ ] **Step 2: `.git/plan-tmp/pr1_body.md` の検証 PR 行を `[x]` に書き換える**

`gh pr edit` は body 全文置換のため、Task 4 Step 4 で書き出した一時ファイルを sed で書き換えて再投稿する。

<!-- Historical reference: 本 plan 実行時の実数 (#685, 25529744519) を記録。以下は参考のみ。 -->

<!-- sed コマンドは wording 変化で silently fail するため、実際の更新には Claude Code の Edit tool で old_string/new_string 完全一致で書き換えること (Edit tool 推奨)。以下は historical reference として残す: -->

```bash
# 検証 PR 行を [x] + URL 入りに置換 (historical record、実行時は Edit tool 推奨)
# sed -i 's|...|...|' .git/plan-tmp/pr1_body.md
```

`#685` を Task 5 Step 5 で記録した検証 PR 番号、failed CI run URL を Task 5 Step 7 で記録した URL に置換して Edit tool で更新する。以下は本 plan 実行時の historical record (以後の再利用時は実行時の値に書き換えること):

- 検証 PR 番号: `#685`
- CI run URL: `https://github.com/Idios/kobutachan-allaganeye/actions/runs/25529744519`

- [ ] **Step 3: 書き換え結果を確認**

```bash
grep -A1 -B1 "違反コード検証 PR" .git/plan-tmp/pr1_body.md
```

Expected: 該当行が `- [x] 違反コード検証 PR #<実数> (closed without merge): CI run https://... で ...` になっている。

- [ ] **Step 4: gh pr edit で本文再投稿**

```bash
gh pr edit #684 --body-file .git/plan-tmp/pr1_body.md
```

Expected: PR body 更新成功。

- [ ] **Step 5: PR view で Self-Test Report が全 `[x]` になっていることを確認**

```bash
gh pr view #684 --json body --jq .body | grep -A20 "Self-Test Report"
```

Expected: machine-verified セクションの全項目が `[x]`、特に検証 PR 行に CI run URL が埋まっていること。

- [ ] **Step 6: 一時ファイルを削除 (任意、本 plan 完了後の cleanup)**

```bash
rm -f .git/plan-tmp/pr1_body.md
rmdir --ignore-fail-on-non-empty .git/plan-tmp 2>/dev/null || true
```

Expected: 一時ファイル削除。`.git/plan-tmp/` は git ignore 配下なので push に影響なし。

---

## Phase 1 完了基準

Phase 2 に進む前に以下を確認:

- [ ] PR #684 の CI 全 job PASS
- [ ] PR #684 Self-Test Report の machine-verified 項目全 `[x]`
- [ ] PR #685 が CLOSED (not MERGED) かつ CI run URL が PR #684 本文に記載

PR #684 の **review / merge は本 plan の対象外** (`/review-pr` skill 経由で別途実施、merge 後 `/close-issue` で issue #643 を base 再検証して close)。

---

## Phase 2: 章 2 — #365 CLI progress bar ETA ラベル

### Task 7: PR Pre-flight + branch 切り (Iron Law 6)

**Files:** (なし、git 操作のみ)

- [ ] **Step 1: 取り込み未済 commit を確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 0 commit、または取り込み未済が touched files (`allaganeye/commands/split_matches.py`, `tests/test_split_matches.py`) と交差するなら Step 2 で merge。

- [ ] **Step 2: 必要に応じて base 同期**

交差ありなら:

```bash
git fetch origin develop-0.2.0
```

交差なしなら skip。Phase 1 の `claude/musing-davinci-38136f-eslint` は merge しない (Phase 2 は Phase 1 と独立 PR)。

- [ ] **Step 3: 並行 worktree PR 重複確認**

```bash
gh pr list --search "365 in:title,body" --state all
```

Expected: 既存 PR が無いこと。

- [ ] **Step 4: branch 切り (origin/develop-0.2.0 から派生明示、worktree branch の plan/spec commits を取り込まないこと)**

```bash
git switch -c claude/musing-davinci-38136f-progress-bar origin/develop-0.2.0
```

Expected: branch 切り替え完了。`git log --oneline origin/develop-0.2.0..HEAD` が空 (ahead-by-0)。

**注意**: worktree session の現在 branch (`claude/musing-davinci-38136f`) には plan/spec commits が含まれているため、`git switch -c <new-branch>` だけだとそれらを inherit してしまう。`origin/develop-0.2.0` を明示することで Phase 2 の PR scope を本質的な実装変更のみに保つ (Iron Law 3 担保)。

---

### Task 8: TDD cycle 1 Red — 4 bar parametrize test

**Files:**

- Modify: `tests/test_split_matches.py` (test 追加のみ、実装はまだ)

- [ ] **Step 1: 既存 test_split_matches.py の構造確認**

```bash
head -30 tests/test_split_matches.py
grep -n "^import\|^from" tests/test_split_matches.py | head -20
```

Expected: import 文の構成を把握。`pytest` / `re` / `time` / `from allaganeye.commands.split_matches import ...` の既存パターンを参考に。

- [ ] **Step 2: test を追加 (failing test、Red phase)**

`tests/test_split_matches.py` の末尾に以下を Edit tool で append (適切な import を冒頭に追加):

冒頭 import section (既存に追加):

```python
import re
import time
```

(既存で import されていれば skip)

`from allaganeye.commands.split_matches import` の既存 import line に `_ETAProgressBar` と `_PROGRESS_LABEL_WIDTH` を追加 (既存 import に append):

```python
from allaganeye.commands.split_matches import (
    # ... 既存 import ...
    _ETAProgressBar,
    _eta_progressbar,
    _PROGRESS_LABEL_WIDTH,
)
```

ファイル末尾に test 追加:

```python
# ============================================================
# #365: progress bar ETA ラベル付与の format 検証
# ============================================================

_ETA_LINE_PATTERN = re.compile(r"\b\d{1,3}%\s+ETA:\s+(?:\d+d\s+)?\d+:\d{2}:\d{2}\b")


def _drive_to_known_eta(bar: _ETAProgressBar, completed: int) -> None:
    """Force eta_known by simulating elapsed time + progress.

    click ProgressBar は ``start`` / ``last_eta`` が None / update 未実行の間
    ``eta_known=False`` のまま 'ETA: --' 相当を出す。テストでは過去
    timestamp + update() で eta_known=True を満たす。
    """
    past = time.time() - 10.0
    bar.start = past
    bar.last_eta = past
    bar.update(completed)


@pytest.mark.parametrize("label", ["Detecting", "Refining", "Scorebar", "Splitting"])
def test_eta_progressbar_label_present_for_all_bars(label: str) -> None:
    """4 bar 全てで 'ETA: H:MM:SS' label を出すこと (#365)."""
    bar = _eta_progressbar(100, label)
    _drive_to_known_eta(bar, 50)

    line = bar.format_progress_line()

    assert line.startswith(label.ljust(_PROGRESS_LABEL_WIDTH))
    assert "ETA: " in line, f"missing 'ETA: ' label in: {line!r}"
    assert _ETA_LINE_PATTERN.search(line), f"format mismatch: {line!r}"
```

- [ ] **Step 3: test を実行して fail を確認**

```bash
pytest tests/test_split_matches.py::test_eta_progressbar_label_present_for_all_bars -v
```

Expected: **FAIL** (4 bar 全てで失敗)。Error は `ImportError: cannot import name '_ETAProgressBar'` (理由: `_ETAProgressBar` class はまだ未実装)。

もし `_ETAProgressBar` を import せず実行しても fail することを確認したい場合は import を一時的に外しても OK だが、TDD Red phase の本旨は **未実装に対する test 失敗を確認** すること。

---

### Task 9: TDD cycle 1 Green — `_ETAProgressBar` minimal 実装

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (`_eta_progressbar` を refactor)

- [ ] **Step 1: 現行 `_eta_progressbar` の周辺を確認**

```bash
sed -n '1060,1095p' allaganeye/commands/split_matches.py
```

Expected: 現行の `_eta_progressbar` 関数 (line 1070-1089 付近) と前後 helper を把握。

- [ ] **Step 2: `_ETAProgressBar` class を追加 + `_eta_progressbar` を refactor**

Edit tool で以下:

`old_string`:

```python
def _eta_progressbar(length: int, label: str, *, suppress_click_eta: bool = False):  # type: ignore[no-untyped-def]
    """Create a progress bar with explicit ETA label (#329).

    Labels are left-justified to ``_PROGRESS_LABEL_WIDTH`` so that
    Detecting / Refining / Splitting bars align vertically.

    When ``suppress_click_eta`` is True (GPU mode, #438), click's own
    ETA is hidden.  GPU chunk completion is non-linear so click's rate
    estimator produces nonsense (e.g. ``3d 08:08:52``); the caller
    supplies a self-computed ETA in the label instead.
    """
    import click

    return click.progressbar(
        length=length,
        label=label.ljust(_PROGRESS_LABEL_WIDTH),
        bar_template="%(label)s%(bar)s %(info)s",
        show_eta=not suppress_click_eta,
        show_percent=True,
    )
```

`new_string`:

```python
class _ETAProgressBar(_ClickProgressBar):
    """Progress bar with explicit 'ETA: H:MM:SS' label (#365).

    click のデフォルト ``%(info)s`` placeholder は ``<percent>  <eta>``
    をラベルなしで展開するだけのため、ユーザーには時刻文字列だけが見え、
    経過時間/残り時間/動画内位置のどれか判別できない (#329 元 issue,
    PR #343 不完全修正、#365 で再対応)。

    本 subclass は ``format_progress_line`` を override し以下に統一:

        Detecting  ###################---  93% ETA: 00:00:22

    ``eta_known=False`` (update 未呼び出し / make_step の 1 秒 debounce
    gate 内) のときも ETA セクションを出し ``ETA: --:--:--`` placeholder
    を表示する (Idios feedback for #365: pre-update でも ETA を出す改善)。

    ``show_eta=False`` (GPU mode #438 の ``suppress_click_eta=True``
    経路) では ETA セクションを出さず percent のみ表示。caller 側が
    self-computed ETA を label に組み込む既存挙動と互換。

    ``finished=True`` (100% 完了) では ETA: 00:00:00 を出さず percent
    のみ表示 (click 親 class と整合)。

    依存する `click._termui_impl` module の `ProgressBar` class が提供する
    メソッド / attribute (click 8.x の internal だが API surface は安定):
      - ``format_bar()``    -- bar 文字列
      - ``format_pct()``    -- "  N%" or "NN%" (左 padding あり)
      - ``format_eta()``    -- "H:MM:SS" or "" (eta_known=False のとき空、本 subclass では '--:--:--' で fallback)
      - ``self.label``      -- ljust 済みラベル
      - ``self.show_eta``   -- ETA 表示フラグ
      - ``self.eta_known``  -- ETA 計算可能フラグ (1 update 後に True)
      - ``self.finished``   -- 100% 完了フラグ (本 subclass で ETA suppression に使用)
      - ``self.start``      -- 開始時刻 (test の time travel に使用)
      - ``self.last_eta``   -- 直近 ETA 計算時刻 (test の time travel に使用)
    """

    def format_progress_line(self) -> str:
        bar = self.format_bar()
        pct = self.format_pct()
        if self.show_eta and not self.finished:
            # eta_known=False (update 未呼び出し / make_step の 1 秒 debounce gate 内)
            # のとき format_eta() は空文字列を返すので、'--:--:--' placeholder で
            # 常時 ETA を表示する (Idios feedback: pre-update でも ETA を出す改善、#365)。
            eta = self.format_eta() or "--:--:--"
            return f"{self.label}{bar} {pct} ETA: {eta}"
        return f"{self.label}{bar} {pct}"


def _eta_progressbar(
    length: int, label: str, *, suppress_click_eta: bool = False
) -> _ETAProgressBar:
    """Create a progress bar with explicit ETA label (#329 / #365).

    Labels are left-justified to ``_PROGRESS_LABEL_WIDTH`` so that
    Detecting / Refining / Scorebar / Splitting bars align vertically.

    When ``suppress_click_eta`` is True (GPU mode, #438), click's own
    ETA is hidden (``show_eta=False``); caller supplies a self-computed
    ETA in the label instead. ``_ETAProgressBar.format_progress_line``
    consumes ``show_eta`` to skip the 'ETA: ' tail in that path.
    """
    return _ETAProgressBar(
        iterable=None,
        length=length,
        label=label.ljust(_PROGRESS_LABEL_WIDTH),
        bar_template="",  # 未使用 (format_progress_line を override したため)
        # click.progressbar() factory 経由では empty_char='-' / width=36 が default
        # だが、ProgressBar.__init__ class 直接インスタンス化では empty_char=' ' /
        # width=30 と異なる default を持つ。issue #365 期待動作
        # `Detecting  ####---  93% ETA: 0:00:22` の `####---` (dash empty char +
        # 36 width) を維持するため明示する (PR #687 review feedback #1+#2 対応)。
        fill_char="#",
        empty_char="-",
        width=36,
        show_eta=not suppress_click_eta,
        show_percent=True,
    )
```

- [ ] **Step 3: `_ClickProgressBar` import を module top に追加 (旧 `_eta_progressbar` 内 `import click` の代替)**

旧実装は関数内で `import click` していた (lazy import)。新 `_ETAProgressBar` class は `_ClickProgressBar` を継承するため、ファイル冒頭の import section に追加する必要がある。

`allaganeye/commands/split_matches.py` の冒頭 import 群を確認:

```bash
head -30 allaganeye/commands/split_matches.py | grep -n "^import\|^from"
```

`from click._termui_impl import ProgressBar as _ClickProgressBar` が既に top level になければ Edit tool で追加 (既存 import 群の適切な位置に):

```python
import typer
from click._termui_impl import ProgressBar as _ClickProgressBar  # subclass 用 (#365)

from allaganeye.audio.matcher import BgmHit
```

- [ ] **Step 4: 4 bar test を実行して PASS を確認**

```bash
pytest tests/test_split_matches.py::test_eta_progressbar_label_present_for_all_bars -v
```

Expected: **PASS** (4 parametrize 全て)。format `Detecting  ###---  50% ETA: H:MM:SS` が全 bar で揃う。

もし FAIL (例: `format_pct()` の output に `%` が含まれない / `format_eta()` が `--` を返す等の click version 差異) なら、click 8.x の実装をローカルで確認:

```bash
python -c "from click._termui_impl import ProgressBar as _ClickProgressBar; help(_ClickProgressBar.format_pct)"
python -c "from click._termui_impl import ProgressBar as _ClickProgressBar; help(_ClickProgressBar.format_eta)"
```

挙動が想定と異なれば spec §5.1 の API 依存を再確認。

- [ ] **Step 5: 既存 test の回帰確認 (短時間)**

```bash
pytest tests/test_split_matches.py -v
```

Expected: 既存 43 test + 新 4 parametrize = 47 PASS (Phase 2 後続 cycle で更に test を追加していく)。失敗が出たら **Stop** して原因を分析。`click.progressbar` を直接 monkeypatch している既存 test があれば修正が必要。

---

### Task 10: TDD cycle 2 Red — GPU mode test

**Files:**

- Modify: `tests/test_split_matches.py` (新 test を append)

- [ ] **Step 1: GPU mode test を追加**

`tests/test_split_matches.py` の末尾 (Task 8 で追加した 4 bar test の後) に Edit tool で append:

```python
def test_eta_progressbar_suppresses_eta_in_gpu_mode() -> None:
    """suppress_click_eta=True (GPU mode #438) では ETA tail を出さず percent のみ."""
    bar = _eta_progressbar(100, "Detecting", suppress_click_eta=True)
    _drive_to_known_eta(bar, 50)

    line = bar.format_progress_line()

    assert "ETA: " not in line
    assert re.search(r"\b\d{1,3}%\s*$", line.rstrip()), line
```

- [ ] **Step 2: test を実行**

```bash
pytest tests/test_split_matches.py::test_eta_progressbar_suppresses_eta_in_gpu_mode -v
```

Expected: **PASS** (Task 9 の `_ETAProgressBar` 実装で `if self.show_eta and not self.finished:` 条件分岐が GPU mode の `show_eta=False` を扱うため、ETA tail を出さず percent のみ)。

これは厳密 TDD の Red→Green サイクルとしては「Green by accident」だが、本 test は **既存挙動を保護する verification test** として価値があり、Task 9 の minimal 実装が正しく GPU mode を扱っていることの **regression guard** になる。click upgrade で挙動が変わった場合や、将来 `_ETAProgressBar.format_progress_line` を別目的で改修した時に、本 test が GPU mode の互換性 break を検出する。

(もし Task 9 の minimal 実装が GPU mode 分岐を持たない単純化版だった場合、ここで test は **FAIL** し、Task 11 で `if self.show_eta:` 分岐を追加して PASS させる純粋な TDD cycle になる。本 plan では Task 9 で全分岐を含む完全版を実装しているため、Task 10 は verification 役割。)

---

### Task 11: TDD cycle 3 Red — eta_known=False test

**Files:**

- Modify: `tests/test_split_matches.py` (新 test を append)

- [ ] **Step 1: eta_known=False test を追加**

`tests/test_split_matches.py` の末尾に Edit tool で append:

```python
def test_eta_progressbar_placeholder_eta_before_first_update() -> None:
    """update 前 (eta_known=False) は 'ETA: --:--:--' placeholder を出す (#365 Idios feedback)."""
    bar = _eta_progressbar(100, "Detecting")
    # _drive_to_known_eta を呼ばない -- eta_known=False のまま

    line = bar.format_progress_line()

    assert "ETA: --:--:--" in line, f"missing placeholder in: {line!r}"
    assert "0%" in line


def test_eta_progressbar_gpu_dispatching_label_with_eta_placeholder() -> None:
    """GPU mode dispatching 段階の label に 'ETA: --:--:--' を含む format を verify (#365).

    Caller (on_chunk_dispatch) が更新する label の expected string を bar に
    直接設定し、format_progress_line() 出力に 'ETA: --:--:--' が含まれる
    + subclass は ETA tail を出さない (show_eta=False) ことを確認する。
    """
    bar = _eta_progressbar(100, "Detecting", suppress_click_eta=True)
    bar.label = "Detecting [dispatching 32 chunks, ETA: --:--:--]".ljust(
        _PROGRESS_LABEL_WIDTH + 50
    )

    line = bar.format_progress_line()

    assert "ETA: --:--:--" in line, f"caller label placeholder missing in: {line!r}"
    assert line.count("ETA:") == 1, f"expected single ETA occurrence in: {line!r}"
```

- [ ] **Step 2: test を実行**

```bash
pytest tests/test_split_matches.py::test_eta_progressbar_placeholder_eta_before_first_update -v
```

Expected: **PASS** (Task 9 の `_ETAProgressBar.format_progress_line` の `if self.show_eta and not self.finished:` 条件で eta_known=False 時に format_eta() の空文字列を `--:--:--` で fallback して `ETA: --:--:--` placeholder を表示)。

Task 10 と同様、これも minimal 実装が完全版である本 plan では verification 役割。click 8.x で `eta_known` 属性の semantics が変わった場合や、将来 `format_progress_line` の条件分岐を改修した場合に、本 test が破壊的変更を検出する。

---

### Task 11.1: TDD cycle 4 — bar visual factory baseline test (PR #687 review feedback #1+#2)

**Files:**

- Modify: `tests/test_split_matches.py` (新 test を append)

- [ ] **Step 1: bar visual test を追加**

`tests/test_split_matches.py` の末尾に Edit tool で append:

```python
def test_eta_progressbar_bar_visual_uses_dashes_and_36_width() -> None:
    """Bar should use '-' for empty cells and 36-char width
    (factory baseline #365 期待動作の `####---` を維持、PR #687 review feedback #1+#2)."""
    bar = _eta_progressbar(100, "Detecting")
    _drive_to_known_eta(bar, 50)
    line = bar.format_progress_line()
    assert "----" in line, f"empty char should be '-': {line!r}"
    bar_part = line.split("Detecting", 1)[1].strip().split(" ")[0]
    assert len(bar_part) == 36, f"bar width should be 36: {bar_part!r}"
```

- [ ] **Step 2: test を実行**

```bash
pytest tests/test_split_matches.py::test_eta_progressbar_bar_visual_uses_dashes_and_36_width -v
```

Expected: **PASS** (`fill_char="#"` / `empty_char="-"` / `width=36` を明示したため `####----` 形式 36 width で描画)。

---

### Task 11.2: TDD cycle 5 — finished=True ETA suppression test (PR #687 review feedback)

**Files:**

- Modify: `tests/test_split_matches.py` (新 test を append)

- [ ] **Step 1: finished ETA suppression test を追加**

`tests/test_split_matches.py` の末尾に Edit tool で append:

```python
def test_eta_progressbar_finished_no_eta_tail() -> None:
    """finished=True (100%) は ETA tail を出さない (click 親 class 整合)."""
    bar = _eta_progressbar(100, "Detecting")
    _drive_to_known_eta(bar, 100)
    assert bar.finished is True
    line = bar.format_progress_line()
    assert "ETA:" not in line, f"finished bar should not show ETA: {line!r}"
    assert "100%" in line
```

- [ ] **Step 2: test を実行**

```bash
pytest tests/test_split_matches.py::test_eta_progressbar_finished_no_eta_tail -v
```

Expected: **PASS** (`format_progress_line` の `if self.show_eta and not self.finished:` 条件で `finished=True` 時に ETA tail を出さずに percent のみ表示)。

---

### Task 12: 既存 test 回帰確認 + 自動チェック

**Files:** (検査のみ)

- [ ] **Step 1: 全 split_matches test を走査**

```bash
pytest tests/test_split_matches.py -v
```

Expected: 既存 43 + 新 4 parametrize + GPU mode 1 + eta_known=False 1 + bar_visual 1 + finished 1 = 51 test PASS。

- [ ] **Step 2: progress bar 関連 regression test を走査**

```bash
pytest tests/test_regression_330.py tests/test_progress_emitter.py -v
```

Expected: 全 PASS (`_eta_progressbar` の戻り型変更が既存 progress bar regression test を壊していないこと)。失敗があれば `_eta_progressbar` の戻り値 method 互換性を再確認 (context manager protocol / `update` / `label` 属性等)。

- [ ] **Step 3: 全 unit test (slow 除く) で回帰確認**

```bash
pytest -m "not slow and not baseline_regen"
```

Expected: 全 PASS。

- [ ] **Step 4: ruff check**

```bash
ruff check .
```

Expected: exit 0、新コードに lint 違反なし。

- [ ] **Step 5: ruff format check**

```bash
ruff format --check .
```

Expected: exit 0、format 整合。

- [ ] **Step 6: pyright**

```bash
pyright
```

Expected: 0 errors。`_ETAProgressBar` の type annotation (`length: int`, `label: str`, return `_ETAProgressBar`) が pyright で resolve できることを確認。

---

### Task 13: commit + PR #2 作成

**Files:** (commit + push + PR)

- [ ] **Step 1: 変更を確認**

```bash
git status --short
git diff --stat
```

Expected: `allaganeye/commands/split_matches.py` と `tests/test_split_matches.py` の 2 file 変更のみ。

- [ ] **Step 1.5 (R3 追加): `docs/cli-spec.md` 100% 行を新仕様に追従**

`Detecting / Refining / Scorebar / Splitting` 100% 行で ETA tail を抑止する仕様変更に追従して `docs/cli-spec.md` を更新:

```bash
grep -nE "Detecting.*100%|Refining.*100%|Scorebar.*100%|Splitting.*100%" docs/cli-spec.md
```

各行を `Detecting  #################################### 100%` 形式 (ETA tail なし) に Edit tool で置換。

- [ ] **Step 2: commit**

```bash
git add allaganeye/commands/split_matches.py tests/test_split_matches.py
git commit -m "$(cat <<'EOF'
fix(cli): 進捗バー ETA 表示に 'ETA: ' ラベルを付与 (Refs #365)

PR #343 (#329 修正) で `show_eta=True` を click.progressbar に渡したものの、
bar_template が `%(info)s` を使っていたため click は "<percent>  <eta>"
をラベルなしで展開し、ユーザーには時刻だけが見えて意味が伝わらない不完全
修正で merge されていた (#365)。

## 変更内容

### allaganeye/commands/split_matches.py

- 新 class `_ETAProgressBar(_ClickProgressBar)` を追加し、
  `format_progress_line()` を override して以下の format に統一:
    Detecting  ###################---  93% ETA: 00:00:22
- `_eta_progressbar()` の戻り型を `_ETAProgressBar` に refactor。
  4 bar (Detecting / Refining / Scorebar / Splitting) で format 統一。
- GPU mode (suppress_click_eta=True → show_eta=False、PR #438 経路) は
  ETA tail を出さず percent のみ。caller の self-computed ETA を label
  に組み込む既存挙動と互換。
- `_ClickProgressBar` import を module top に追加 (`from click._termui_impl import ProgressBar as _ClickProgressBar`)。旧 `_eta_progressbar` 内 `import click` は class 定義のため module top レベルに移動。

### tests/test_split_matches.py

PR #343 の test 不足 (進捗バー出力に対する snapshot / 部分文字列 assert
不在) を反省し、`format_progress_line()` の出力を直接 assert する unit
test を 6 種追加:

1. `test_eta_progressbar_label_present_for_all_bars` (4 parametrize)
   -- 4 bar 全てで `\b\d{1,3}%\s+ETA:\s+\d+:\d{2}:\d{2}\b` regex 一致
2. `test_eta_progressbar_suppresses_eta_in_gpu_mode`
   -- GPU mode で 'ETA: ' tail を出さない (#438 互換)
3. `test_eta_progressbar_placeholder_eta_before_first_update`
   -- update 前 (eta_known=False) は 'ETA: --:--:--' placeholder を表示 (Idios feedback)
4. `test_eta_progressbar_gpu_dispatching_label_with_eta_placeholder`
   -- GPU mode dispatching label に 'ETA: --:--:--' を含む format verify (二重 ETA 防止)
5. `test_eta_progressbar_bar_visual_uses_dashes_and_36_width`
   -- factory baseline `####---` (`empty_char='-'`, `width=36`) を維持 (PR #687 review feedback #1+#2)
6. `test_eta_progressbar_finished_no_eta_tail`
   -- finished=True (100%) で ETA tail を出さない (PR #687 review feedback)

## 影響範囲

- Detecting (split_matches.py:810)
- Refining (split_matches.py:898)
- Scorebar (split_matches.py:922)
- Splitting (split_matches.py:1130)

検知ロジック不変、進捗表示の format のみ変更。

## 受け入れ条件マッピング

issue [#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) には明示
の `## 受け入れ条件` 節がないため「期待動作」「根本原因分析」から逐条:

- [x] 期待動作: `Detecting ####---  93% ETA: 00:00:22` 形式
      → _ETAProgressBar.format_progress_line で実現
- [x] 影響範囲全 4 bar: Detecting / Refining / Scorebar / Splitting
      → _eta_progressbar 戻り型変更で全 caller が新 format
- [x] 直接原因 (`%(info)s` ラベルなし展開) の解消
      → bar_template="" + format_progress_line override で bypass
- [x] 検出漏れ (PR #343 test 不足) の再発防止
      → 6 種 test (4 bar parametrize + GPU mode + placeholder eta + GPU dispatching placeholder + bar visual factory baseline + finished ETA suppression) 追加

session-id: musing-davinci-38136f

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit 成功。

- [ ] **Step 3: push**

```bash
git push -u origin claude/musing-davinci-38136f-progress-bar
```

Expected: branch push 成功。

- [ ] **Step 4: PR #2 body を一時ファイルに書き出す (Task 14 で再利用)**

```bash
mkdir -p .git/plan-tmp
cat > .git/plan-tmp/pr2_body.md <<'EOF'
## 概要

PR #343 (#329 修正) で `show_eta=True` を click.progressbar に渡したものの、`bar_template` が `%(info)s` を使っていたため click は `<percent>  <eta>` をラベルなしで展開し、ユーザーには時刻だけが見えて意味が伝わらない不完全修正で merge されていた ([#365](https://github.com/Idios/kobutachan-allaganeye/issues/365))。

`_eta_progressbar` を `_ETAProgressBar(_ClickProgressBar)` subclass + `format_progress_line()` override に refactor し、4 bar (Detecting / Refining / Scorebar / Splitting) で `93% ETA: 00:00:22` 形式に統一する。

## 変更ファイル

- `allaganeye/commands/split_matches.py`: `_ETAProgressBar` 追加、`_eta_progressbar` refactor、`_ClickProgressBar` import を module top に追加
- `tests/test_split_matches.py`: `format_progress_line()` の直接 assert test 6 種 (4 bar parametrize + GPU mode + placeholder eta + GPU dispatching placeholder + bar visual factory baseline + finished ETA suppression)

## 受け入れ条件マッピング (Iron Law 1)

issue [#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) には明示的な `## 受け入れ条件` セクションが無いため、「期待動作」と「根本原因分析」を逐条検証:

- [x] **期待動作**: `Detecting ####---  93% ETA: 00:00:22` 形式
  → `_ETAProgressBar.format_progress_line` で `f"{self.label}{bar} {pct} ETA: {eta}"` を生成
- [x] **影響範囲全 4 bar** (`Detecting`, `Refining`, `Scorebar`, `Splitting`)
  → `_eta_progressbar` の戻り型を `_ETAProgressBar` に変えるだけで全 caller (split_matches.py:810/898/922/1130) が新 format を享受
- [x] **直接原因** (`%(info)s` でラベルなし展開) の解消
  → `bar_template=""` + `format_progress_line` override で click の組み込み templating を bypass
- [x] **検出漏れ** (PR #343 のテスト不足) の再発防止
  → `format_progress_line()` の出力に対する parametrize test (4 bar) + regex 一致 + GPU mode 経路 test + placeholder eta test + GPU dispatching placeholder test + bar visual factory baseline test + finished ETA suppression test の 6 種を追加

## Self-Test Report

### machine-verified

- [x] `pytest tests/test_split_matches.py` (新 6 種 test 含む全 PASS、51 test)
- [x] `pytest tests/test_regression_330.py tests/test_progress_emitter.py` (regression PASS)
- [x] `pytest -m "not slow and not baseline_regen"` (全 unit test PASS)
- [x] `ruff check .`
- [x] `ruff format --check .`
- [x] `pyright` (0 errors)

### machine-unverifiable (Idios 実機検証)

- 短い sample 動画で `allaganeye split <video> --dry-run` 実行 → Detecting / Refining / Scorebar / Splitting 4 bar 全てに `ETA: H:MM:SS` 表示
- `--gpu` で sample 動画 → ETA 二重表示が起きないこと (GPU mode #438 互換確認)
- 既存 metadata.json と diff なし (検知ロジック regression なし)

## 関連

- 元 issue: [#329](https://github.com/Idios/kobutachan-allaganeye/issues/329) (CLOSED、不完全修正のため #365 で再対応)
- PR: [#343](https://github.com/Idios/kobutachan-allaganeye/pull/343) (不完全修正)
- GPU mode 経路: PR [#438](https://github.com/Idios/kobutachan-allaganeye/pull/438) (`suppress_click_eta=True`)
- spec: `docs/superpowers/specs/2026-05-08-l2-lane-ivc-group-h-design.md` §5

session-id: musing-davinci-38136f

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

Expected: `.git/plan-tmp/pr2_body.md` に body が書き出される。

- [ ] **Step 5: PR #2 を作成**

```bash
gh pr create --base develop-0.2.0 --head claude/musing-davinci-38136f-progress-bar --title "fix(cli): 進捗バー ETA 表示に 'ETA: ' ラベルを付与 (Refs #365)" --body-file .git/plan-tmp/pr2_body.md
```

Expected: PR 作成成功、PR URL + 番号を記録 (以降 `#687`)。

- [ ] **Step 6: CI 待機 + PASS 確認**

```bash
gh pr checks #687 --watch
```

Expected: 全 job PASS。

---

### Task 14: Idios に実機表示確認を依頼 (Iron Law 6 実機検証 trigger)

**Files:** (なし、user interaction のみ)

- [ ] **Step 1: AskUserQuestion で実機検証を依頼**

`AskUserQuestion` で以下:

```text
Question: PR #687 (#365 ETA label) は CLI 進捗表示の format 変更で、
検知ロジック不変ですが、4 bar の表示確認は機械化できないため Idios
実機検証を依頼します。

実機検証項目 (3 つ):
- 短い sample 動画で `allaganeye split <video> --dry-run` 実行 →
  Detecting / Refining / Scorebar / Splitting 4 bar 全てに
  'ETA: H:MM:SS' が表示されること
- GPU mode (--gpu) で同 sample 動画 → ETA 二重表示が起きないこと
- 既存 metadata.json と diff なし (検知ロジック regression なし)

選択肢:
(a) 検証完了 (3 項目 OK) — PR Self-Test Report の machine-unverifiable
    を [x] に切り替えて review 段階へ
(b) NG あり — 詳細を別途報告して Plan 修正

(c) 後で実施 — 現時点では PR review/merge は保留
```

- [ ] **Step 2: 結果を PR #687 Self-Test Report に反映**

**(a) 完了 (3 項目 OK) を選択した場合**:

`.git/plan-tmp/pr2_body.md` (Task 13 Step 4 で書き出し済) の `### machine-unverifiable (Idios 実機検証)` セクション 3 行を `- [x]` 切替する。

**重要**: `sed -i` は wording 変化で silently fail するため、**Claude Code の Edit tool で `old_string` / `new_string` を完全一致で書き換えること** (sed の brittle anchor を避けるため Edit tool 推奨)。以下の sed コマンドは historical reference として残すが、実際の更新は Edit tool で行うこと:

```bash
# historical reference (実行時は Edit tool 推奨):
# sed -i 's|^- 短い sample 動画で.*$|- [x] ...|' .git/plan-tmp/pr2_body.md
# sed -i 's|^- `--gpu` で sample 動画.*$|- [x] ...|' .git/plan-tmp/pr2_body.md
# sed -i 's|^- 既存 metadata.json.*$|- [x] ...|' .git/plan-tmp/pr2_body.md
```

Edit tool での変更対象は以下の 3 行 (末尾に「Idios 実機 YYYY-MM-DD 確認」を追記):

- `- 短い sample 動画で ...` → `- [x] 短い sample 動画で ... (Idios 実機 2026-05-08 確認)`
- `- \`--gpu\` で sample 動画 → ETA 二重表示が起きないこと ...` → `- [x] ... (Idios 実機 2026-05-08 確認)`
- `- 既存 metadata.json と diff なし ...` → `- [x] ... (Idios 実機 2026-05-08 確認)`

書き換え結果を確認:

```bash
grep -A4 "machine-unverifiable" .git/plan-tmp/pr2_body.md
```

Expected: 3 行全てが `- [x]` で始まり、末尾に「Idios 実機 YYYY-MM-DD 確認」が付いている。

PR body を再投稿:

```bash
gh pr edit #687 --body-file .git/plan-tmp/pr2_body.md
```

最後に一時ファイルを削除:

```bash
rm -f .git/plan-tmp/pr2_body.md
rmdir --ignore-fail-on-non-empty .git/plan-tmp 2>/dev/null || true
```

**(b) NG あり を選択した場合**:

- Idios から詳細 (どの bar / どの mode で何が起きたか) を `AskUserQuestion` で詳細聴取
- Phase 2 の Task 9-12 のいずれかに戻って実装修正 (例: 4 bar の format ズレなら Task 9 Step 2、GPU mode 二重表示なら Task 9 の `if self.show_eta and not self.finished:` 条件 + caller label と subclass の ETA 表示重複を再確認)
- 修正後 Task 12 (自動チェック) → Task 13 Step 2-3 (commit + push) → Task 13 Step 6 (CI 再確認) → Task 14 Step 1 (再依頼)

**(c) 後で実施 (保留) を選択した場合**:

- PR #687 は open のまま放置、本 plan の Phase 2 を **machine-unverifiable 未消化のまま保留完了** 扱いにする
- Idios が後日実機検証を実施する際の手順を PR comment に書いておく:

```bash
gh pr comment #687 --body "$(cat <<'EOF'
## machine-unverifiable 実機検証 (Idios 後日実施)

短い sample 動画 (例: `videos/short_sample.mkv`) で以下 3 項目を確認してください:

1. `allaganeye split <video> --dry-run` 実行 → Detecting / Refining / Scorebar / Splitting 4 bar 全てに `ETA: H:MM:SS` 表示
2. `allaganeye split <video> --gpu --dry-run` で ETA 二重表示が起きないこと (GPU mode #438 互換)
3. `--dry-run` 無し実行で既存 metadata.json と diff なし (検知ロジック regression なし)

完了後、PR body の `### machine-unverifiable` セクションを `- [x]` に手動更新してください。
EOF
)"
```

Expected: PR comment 投稿成功、Idios が後日実機検証可能な状態。

---

## Phase 2 完了基準

- [ ] PR #687 の CI 全 job PASS
- [ ] PR #687 Self-Test Report の machine-verified 全 `[x]`
- [ ] Idios 実機検証 (machine-unverifiable) が完了 or 保留状態を明記

PR #687 の **review / merge は本 plan の対象外** (`/review-pr` skill 経由で別途実施、merge 後 `/close-issue` で issue #365 を base 再検証して close)。

---

## 全体完了基準 (Lane IV-c Group H)

- [ ] Phase 1 完了 (PR #684 CI PASS + 検証 PR #685 closed without merge + Self-Test Report 完了)
- [ ] Phase 2 完了 (PR #687 CI PASS + Idios 実機検証完了 / 保留)
- [ ] 両 PR の `/review-pr` 実行 + `/close-issue` への引き渡しは別 session で実施

## 関連 doc

- spec: [docs/superpowers/specs/2026-05-08-l2-lane-ivc-group-h-design.md](../specs/2026-05-08-l2-lane-ivc-group-h-design.md)
- roadmap: [docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md](2026-05-07-l2-v020-roadmap.md) §Group H / §Lane IV-c
- workflow: `docs/l2-workflow.md` §PR 作成 Pre-flight / §Self-Test Report 規約 / §実機検証 trigger
