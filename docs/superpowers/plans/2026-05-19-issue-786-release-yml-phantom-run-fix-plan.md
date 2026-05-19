# Issue #786: release.yml phantom run 修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `develop-0.3.0` への push で release.yml が phantom run (jobs=0, conclusion=failure) になる schema-invalid な `shell: ${{ matrix.shell }}` を `defaults.run.shell` に移し、build-windows job を復活させた上で PR #785 post-merge plan Step 1 を empirical 検証し、#752 受け入れ条件 (file count reduction ≥ 80%) を実測再確認して #786 と #752 を close する。

**Architecture:** `.github/workflows/release.yml` の build-windows job 直下に `defaults.run.shell: ${{ matrix.shell }}` を追加し、9 個の step から `shell: ${{ matrix.shell }}` 行を削除する最小変更 (Option A2、+3/-9 = -6 net line)。修復後の CI で artifact (`allaganeye-windows-v0.3.0` / `allaganeye-baseline-v0.3.0`) が生成されることで build-windows 動作を実証、`baseline.json` から file count を抽出して PR #785 に Empirical Validation Report comment を投稿。最後に `/close-issue #752` → `/close-issue #786` で正式 close。

**Tech Stack:** GitHub Actions (YAML) / Python (yaml.safe_load) / gh CLI (artifact download, PR comment, issue close) / Codex (adversarial-review) / superpowers iterate-review, close-issue skills

**Spec:** [docs/superpowers/specs/2026-05-19-issue-786-release-yml-phantom-run-fix-design.md](../specs/2026-05-19-issue-786-release-yml-phantom-run-fix-design.md)

**Iron Law 参照**:

- Iron Law 1 (受け入れ条件逐条検証) → spec §受け入れ条件 を Phase 3 で逐条 check
- Iron Law 4 (Closes/Fixes/Resolves キーワード禁止) → PR 本文 / commit message で禁止語使わない、手動 close
- Iron Law 5 (曖昧な判断は AskUserQuestion) → 各 task で曖昧判断点があれば pause + AskUserQuestion
- Iron Law 6 (Pre-flight Step 0-5) → Phase 1 Task 1-2 + Task 6 で実施
- 詳細: [docs/l2-workflow.md](../../l2-workflow.md)

---

## Phase 1: release.yml 修正 PR

### Task 1: Spec read + Iron Law 6 Pre-flight Step 0 (重複 PR ハードゲート)

**Files:**

- Read: `docs/superpowers/specs/2026-05-19-issue-786-release-yml-phantom-run-fix-design.md`

- [ ] **Step 1: Spec を読んで scope / fix method / 受け入れ条件を確認**

Read tool で spec doc 全文を読む。特に §Fix method (Option A2 の修正前後 yaml example) と §受け入れ条件を memorize。

- [ ] **Step 2: Iron Law 6 Pre-flight Step 0 ハードゲート (gh pr list で重複 PR 検出、<1s)**

Run:

```bash
gh pr list --search "#786" --state open --json number,title,headRefName,baseRefName
```

Expected: `[]` (empty array、重複 PR ゼロ)。1 件以上検出されたら STOP し、AskUserQuestion で「既存 PR に追記 / 重複として close / continue」の 3 択を user に問う。

- [ ] **Step 3: 同 issue 過去 PR の root cause を確認 (Iron Law 6 Step 5 prep)**

Run:

```bash
gh pr list --search "release.yml phantom run" --state all --json number,title,state,closedAt --limit 10
```

Expected: 過去に同 issue を扱った PR があれば内容を確認 (root cause の繰り返し回避用)。本 issue #786 は今回が初対応のため通常はゼロ件。

---

### Task 2: Iron Law 6 Pre-flight Step 1-3 (base sync / 取り込み未済 commit / touched files 交差判定)

**Files:**

- なし (git 操作のみ)

- [ ] **Step 1: Step 1 base sync**

Run:

```bash
git fetch origin develop-0.3.0
```

Expected: `* branch  develop-0.3.0 -> FETCH_HEAD` または既に最新なら出力なし。fail 時は network / auth を確認。

- [ ] **Step 2: Step 2 取り込み未済 commit 確認**

Run:

```bash
git log HEAD..origin/develop-0.3.0 --oneline
```

Expected: 空 (現在の worktree branch `claude/brave-heisenberg-5730dd` が origin/develop-0.3.0 と同期済)。commit が出る場合は `git merge origin/develop-0.3.0` で取り込み。

- [ ] **Step 3: Step 3 touched files 交差判定**

Run:

```bash
git diff --stat origin/develop-0.3.0 -- .github/workflows/
```

Expected: 既に commit 済の spec doc 以外で release.yml への変更がゼロ件 (= 修正前の clean state)。release.yml が既に modify されていれば現状を確認し、想定外の変更があれば AskUserQuestion で対応相談。

---

### Task 3: release.yml 修正 (defaults.run.shell 追加 + 9 箇所の shell: 行削除)

**Files:**

- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: 該当行 (L102-L120) を Read で取得**

Read tool で `.github/workflows/release.yml:102:140` を取得。build-windows job の `strategy:` `matrix:` `name:` `env:` までを確認。

- [ ] **Step 2: build-windows job 直下に `defaults.run.shell` を挿入**

Edit tool で L117 (`ALLAGANEYE_BUILD_CACHE_DIR: ${{ github.workspace }}/build-cache`) の直前 (= `env:` の直前) に以下 3 行を挿入。

```yaml
    defaults:
      run:
        shell: ${{ matrix.shell }}
```

挿入後の構造:

```yaml
  build-windows:
    needs: version-check
    runs-on: windows-latest
    # ... (コメント)
    strategy:
      fail-fast: false
      matrix:
        shell: [pwsh, powershell]
    name: build-windows (${{ matrix.shell }})
    defaults:
      run:
        shell: ${{ matrix.shell }}
    env:
      ALLAGANEYE_BUILD_CACHE_DIR: ${{ github.workspace }}/build-cache
    steps:
      ...
```

Edit の old_string は `name: build-windows (${{ matrix.shell }})\n    env:` (= name 行 + env 行)、new_string は `name: build-windows (${{ matrix.shell }})\n    defaults:\n      run:\n        shell: ${{ matrix.shell }}\n    env:`。

- [ ] **Step 3: 9 箇所の `shell: ${{ matrix.shell }}` 行を削除 (replace_all 使用)**

Edit tool で以下を `replace_all: true` で削除。

old_string:

```yaml
        shell: ${{ matrix.shell }}
```

new_string (空、= 行ごと削除):

```text
```

実装注: Edit tool の new_string 空文字列の動作確認が必要。new_string が空文字列だと old_string の matched 全 occurrence が削除される (改行ごと)。Bash の `grep -c` で削除前 9 件、削除後 0 件を確認する step を続く Task 4 で実施。

代替手法 (Edit tool で空 new_string が動作しない場合): 9 step を 1 つずつ Edit で削除 (`old_string` に該当 step の `shell:` 行を含む 3-4 行、`new_string` に `shell:` 行抜きの 2-3 行)。

- [ ] **Step 4: defaults.run.shell が ubuntu-latest 上の他 job (version-check / release) に波及しないことを再確認**

Read tool で `.github/workflows/release.yml` の全体構造 (`jobs:` 以下) を確認。`defaults:` block が build-windows job 配下にだけあり、version-check / release job には無いことを確認。

`shell: bash` 指定の step (version-check の `Resolve and verify version` step / release の `Create release archive` / `Extract release notes` step) が **そのまま残っている** ことを確認 (削除されていない)。

Run:

```bash
MSYS_NO_PATHCONV=1 grep -n 'shell: bash' .github/workflows/release.yml
```

Expected: 3 件 (`Resolve and verify version` / `Create release archive` / `Extract release notes from CHANGELOG`)。

---

### Task 4: Local 検証 (YAML syntax + 残存 shell: matrix の不在確認 + actionlint optional + markdownlint)

**Files:**

- なし (検証のみ)

- [ ] **Step 1: YAML syntax check (python yaml.safe_load)**

Run:

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8').read()); print('YAML OK')"
```

Expected: `YAML OK` を出力。yaml.YAMLError が出たら syntax 修正。

- [ ] **Step 2: `shell: ${{ matrix.shell }}` 行が 0 件であることを確認**

Run:

```bash
MSYS_NO_PATHCONV=1 grep -cE 'shell:.*matrix' .github/workflows/release.yml
```

Expected: `0` を出力 (修正前は 9)。0 以外なら Task 3 Step 3 の削除漏れあり、再修正。

- [ ] **Step 3: `defaults.run.shell` が 1 件存在することを確認**

Run:

```bash
MSYS_NO_PATHCONV=1 grep -nE 'defaults:|shell: \$\{\{ matrix' .github/workflows/release.yml
```

Expected:

```text
<line>:    defaults:
<line>:        shell: ${{ matrix.shell }}
```

(= 2 行のみ、L117 付近)

- [ ] **Step 4: (Optional) actionlint で schema 検証**

local 環境に actionlint がインストールされている場合のみ実行。

Run:

```bash
which actionlint && actionlint .github/workflows/release.yml || echo "actionlint not available, skipped"
```

Expected: `actionlint not available, skipped` (Windows 環境では未インストールが通常) もしくは actionlint で error なし。actionlint で error が出る場合は内容を確認し修正。

- [ ] **Step 5: markdownlint (plan doc 変更分のみ check)**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: `0 errors`。本 task で plan doc 1 file を追加するため markdownlint check が必要。violation が出たら `bash scripts/check-markdownlint.sh --fix` で自動修正。

---

### Task 5: Commit (release.yml 修正)

**Files:**

- なし (git 操作)

- [ ] **Step 1: git status で stage 状況を確認**

Run:

```bash
git status
```

Expected: 修正済 `.github/workflows/release.yml` が unstaged、本 plan doc が untracked (Phase 1 で同一 commit に含めるか別 commit にするかは Step 2 で決定)。

- [ ] **Step 2: plan doc も同一 commit に含めるか判断**

判断基準: plan doc は本 PR の context として一緒に commit するのが convention (spec doc は brainstorming 終了時に既に別 commit 済、plan doc は本 PR の作業対象として release.yml と同 commit が自然)。

実行: plan doc を release.yml 修正と同一 commit に含める。

```bash
git add .github/workflows/release.yml docs/superpowers/plans/2026-05-19-issue-786-release-yml-phantom-run-fix-plan.md
```

- [ ] **Step 3: commit (Iron Law 4 厳守: Closes/Fixes/Resolves 禁止)**

Run:

```bash
git commit -m "$(cat <<'EOF'
fix(workflow): #786 release.yml phantom run を defaults.run.shell で解消

shell: ${{ matrix.shell }} が GitHub Actions schema-invalid
(jobs.<job_id>.steps[*].shell field は matrix context 非サポート)
で develop-0.3.0 push 時に release.yml が jobs=0 / conclusion=failure
の phantom run になっていた問題を Option A2 で修正。

build-windows job 直下に defaults.run.shell: ${{ matrix.shell }} を
追加し、9 step から shell: ${{ matrix.shell }} 行を削除。matrix.shell
構造 + #737 dual-shell 検証能力を維持しつつ schema valid 化、
+3/-9 = -6 net line の最小変更。

Codex /codex:rescue で root cause 確定 (agentId a9a21c7545477c99c)、
brainstorming session brave-heisenberg-5730dd で Idios 確認の上
Option A2 採用。

設計: docs/superpowers/specs/2026-05-19-issue-786-release-yml-phantom-run-fix-design.md
plan: docs/superpowers/plans/2026-05-19-issue-786-release-yml-phantom-run-fix-plan.md
Refs #786

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

注意: `Refs #786` は OK だが `Closes #786` / `Fixes #786` / `Resolves #786` は **Iron Law 4 違反**。手動 close は Phase 3 で実施。

- [ ] **Step 4: commit 成功を確認**

Run:

```bash
git log --oneline -3
```

Expected: 最新 commit に `fix(workflow): #786 release.yml phantom run を defaults.run.shell で解消` が出る。

---

### Task 6: Iron Law 6 Pre-flight Step 4 (並行 PR 重複再確認) + Step 5 (/codex:adversarial-review)

**Files:**

- なし (gh / Codex 操作)

- [ ] **Step 1: Step 4 並行 PR 重複再確認**

Run:

```bash
gh pr list --search "#786" --state all --json number,title,state,headRefName,createdAt --limit 10
```

Expected: 本 worktree の `claude/brave-heisenberg-5730dd` branch 以外で #786 関連 PR がゼロ件。1 件以上検出された場合 STOP し AskUserQuestion で「既存 PR に統合 / 重複として close / continue」を user に問う (Iron Law 6 Step 4 のハードゲート機能、L2 workflow §「PR 作成 Pre-flight」)。

- [ ] **Step 2: Step 5 `/codex:adversarial-review` を invoke**

Skill tool で `codex:adversarial-review` を invoke (Iron Law 6 サブ条 C2)。focus 文字列に Iron Law 3 / encoding / GPU fallback / 同 issue 過去 PR root cause を含める。

prompt 例:

> develop-0.3.0 branch の本 commit (release.yml 修正、+3/-9 net line) を adversarial-review してほしい。
>
> focus: (1) Iron Law 3 scope creep (release.yml 以外への染み出し)、(2) encoding boundary (Python subprocess / Rust Tauri / Windows code page の 3 層 audit、本 PR は workflow YAML のみで該当しないはずだが念のため)、(3) GPU fallback path への影響 (release.yml が GPU encoder 検出 path に影響しないか)、(4) 同 issue (#786) の過去 PR root cause 再発 (本件は初対応 issue、PR #775 で生んだ matrix.shell schema invalid を Option A2 で fix、retrospective 振り返り)、(5) defaults.run.shell が schema valid であることの再確認 (公式 docs reference 込み)、(6) build-windows job 以外への波及 (version-check / release job の bash step が無変更で残存していることの確認)
>
> 制約: NO WRITE / NO CODE EDIT / NO COMMIT (review only)。BLOCKED 報告で Claude に handback。

- [ ] **Step 3: Codex finding を triage**

Codex report を読み:

- **重大 issue (= scope 内、PR 修正必要)** → 該当 task に追加 finding として作業
- **scope 外 finding (= Iron Law 3 の Red Flag)** → 独断修正せず、別 issue 候補として記録
- **問題なし** → そのまま Task 7 PR 作成へ進む

判断が曖昧な finding は AskUserQuestion で Idios に triage を仰ぐ (Iron Law 5)。

---

### Task 7: PR 作成 (base=develop-0.3.0)

**Files:**

- なし (gh 操作)

- [ ] **Step 1: branch を origin に push**

Run:

```bash
git push -u origin claude/brave-heisenberg-5730dd
```

Expected: `* [new branch] claude/brave-heisenberg-5730dd -> claude/brave-heisenberg-5730dd` または既存 branch なら fast-forward push。

- [ ] **Step 2: PR 作成 (Self-Test Report 本文付き)**

Run:

```bash
gh pr create --base develop-0.3.0 --title "fix(workflow): #786 release.yml phantom run を defaults.run.shell で解消" --body-file - <<'EOF'
## 期待値

`develop-0.3.0` への push (および pull_request / workflow_dispatch / release tag push) で `release.yml` の `build-windows` job が pwsh / powershell 両 matrix で実行され、`allaganeye-windows-v<version>` + `allaganeye-baseline-v<version>` artifact が生成される。

## 現状

`develop-0.3.0` で 8 連続 push (`c3ea76d` 〜 `6e00fe05`) が `conclusion=failure` / `jobs_count=0` / `name=".github/workflows/release.yml"` の phantom run。GitHub Actions 診断: "This run likely failed because of a workflow file issue."

## ユーザー影響 / 重要性

`build-windows` job が動かないことで:
- PR #785 (#752 PyInstaller --onedir 移行) の post-merge plan Step 1 (PyInstaller frozen build empirical 検証 + smoke Lv A/B/integrity exit 7 + `baseline.json` artifact) が未達
- 結果として #752 受け入れ条件「file count reduction ≥ 80%」が実測未確定
- **v0.3.0 release blocker 相当**

## 修正内容

Codex `/codex:rescue` (session `brave-heisenberg-5730dd`、agentId `a9a21c7545477c99c`) で root cause 確定:

> `shell: ${{ matrix.shell }}` は GitHub Actions schema-invalid。`jobs.<job_id>.steps[*].shell` field は matrix context をサポートしない (公式 [context availability table](https://docs.github.com/en/actions/learn-github-actions/contexts))。workflow 起動前 schema validation で `Unrecognized named-value: 'matrix'` reject → jobs=0 / conclusion=failure。

修正は Option A2 (最小変更、+3/-9 = -6 net line):

- `build-windows` job 直下に `defaults.run.shell: ${{ matrix.shell }}` 追加 (`jobs.<job_id>.defaults.run` は matrix context 参照可)
- 各 step の `shell: ${{ matrix.shell }}` 行を削除 (9 箇所)

matrix.shell 構造 + #737 dual-shell 検証能力 (PS 5.1 silent regression 検知、#729 系) を維持。

`version-check` / `release` job の `shell: bash` step は ubuntu-latest 上で意図的 bash 指定のため touch しない。

## Self-Test Report

### Machine-verified (PR 作成時点 / local 検証)

- [x] `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8').read())"` → `YAML OK`
- [x] `grep -cE 'shell:.*matrix' .github/workflows/release.yml` → `0` (修正前は 9)
- [x] `grep -n 'shell: bash' .github/workflows/release.yml` → 3 件残存 (version-check の `Resolve and verify version` / release の `Create release archive` / `Extract release notes`、意図通り)
- [x] `bash scripts/check-markdownlint.sh` → `0 errors` (plan / spec doc)

### Machine-verified (PR 作成後 CI で実証 → CI 完了後に本文 update)

- [ ] PR の pull_request trigger CI で `build-windows (pwsh)` と `build-windows (powershell)` が両方 `success` (jobs_count > 0、phantom run 解消の実証)
- [ ] PR の CI で `allaganeye-windows-v<version>` + `allaganeye-baseline-v<version>` artifact 生成

(CI 完了後、本 section の `[ ]` を `[x]` に更新して `gh pr edit` で PR 本文を update する)

### Machine-unverifiable (PR merge 後 / 別 phase で検証)

- post-merge の develop-0.3.0 push trigger で release.yml が再度 success すること (本 PR Phase 2 Task 10 で実証)
- PR #785 post-merge plan Step 1 (baseline.json metric から file count reduction ≥ 80% 検証) は本 PR merge 後の Phase 3 で実証

## Iron Law 6 Pre-flight

- [x] Step 0 ハードゲート (gh pr list --search "#786" --state open): 重複ゼロ
- [x] Step 1 base 同期 (git fetch origin develop-0.3.0): 完了
- [x] Step 2 取り込み未済 commit (git log HEAD..origin/develop-0.3.0): ゼロ件
- [x] Step 3 touched files: `.github/workflows/release.yml` + spec / plan doc 2 file (release.yml 以外は documentation のみ)
- [x] Step 4 並行 PR 重複再確認 (gh pr list --search "#786" --state all): ゼロ
- [x] Step 5 `/codex:adversarial-review`: focus (Iron Law 3 / encoding / GPU fallback / 同 issue 過去 PR root cause / defaults.run.shell 妥当性 / 他 job 波及) で実施、findings は本 PR 内 / 別 issue にトリアージ済

## References

- 設計: [docs/superpowers/specs/2026-05-19-issue-786-release-yml-phantom-run-fix-design.md](docs/superpowers/specs/2026-05-19-issue-786-release-yml-phantom-run-fix-design.md)
- plan: [docs/superpowers/plans/2026-05-19-issue-786-release-yml-phantom-run-fix-plan.md](docs/superpowers/plans/2026-05-19-issue-786-release-yml-phantom-run-fix-plan.md)
- Refs #786 #785 #752 #775 #737

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

注意: `Closes #786` / `Fixes #786` / `Resolves #786` は **Iron Law 4 違反** で使わない。`Refs #786` のみ。

- [ ] **Step 3: PR URL を取得**

Run:

```bash
gh pr view --json url --jq '.url'
```

Expected: PR URL を出力。これを以降の task で参照。

---

### Task 8: PR の CI で build-windows job 成功確認 (artifact 生成も)

**Files:**

- なし (CI 確認のみ)

- [ ] **Step 1: PR の CI run を待つ (~10-30 分)**

Run:

```bash
gh pr checks --watch
```

Expected: 全 check が `pass` または `fail`。`build-windows (pwsh)` と `build-windows (powershell)` の両 matrix job が表示されること (= phantom run でなければ表示される)。

- [ ] **Step 2: build-windows job の jobs_count > 0 を確認 (phantom run 解消の実証)**

Run:

```bash
PR_NUM=$(gh pr view --json number --jq '.number')
RUN_ID=$(gh run list --workflow release.yml --branch claude/brave-heisenberg-5730dd --limit 1 --json databaseId --jq '.[0].databaseId')
gh api repos/Idios/kobutachan-allaganeye/actions/runs/$RUN_ID/jobs --jq '{total_count, jobs: [.jobs[] | {name, conclusion}]}'
```

Expected:

```json
{
  "total_count": 3,
  "jobs": [
    {"name": "version-check", "conclusion": "success"},
    {"name": "build-windows (pwsh)", "conclusion": "success"},
    {"name": "build-windows (powershell)", "conclusion": "success"}
  ]
}
```

`total_count > 0` で phantom run 解消、`conclusion=success` で build-windows 動作確認。

- [ ] **Step 3: artifact 生成を確認**

Run:

```bash
gh run view $RUN_ID
```

Expected: `Artifacts: allaganeye-windows-v0.3.0, allaganeye-baseline-v0.3.0` が表示される (`if: matrix.shell == 'pwsh' && (...)` ガードで pwsh matrix のみが生成)。

- [ ] **Step 4: build-windows fail の場合**

`build-windows` のいずれかが `fail` の場合:

- log を確認 (`gh run view $RUN_ID --log-failed | head -200`)
- schema invalid (Codex finding が外れ、別の root cause) → spec を見直し、別 task で再 fix
- 実 step runtime fail (Verify GUI bundled / smoke test / etc.) → 該当 step の修正を本 PR 内で行う (Iron Law 3 (A) PR 内修正優先) もしくは別 issue 起票
- 判断が曖昧なら AskUserQuestion で Idios に triage を仰ぐ (Iron Law 5)

- [ ] **Step 5: CI success 確定後、PR 本文の Self-Test Report を update**

Task 7 Step 2 の PR 本文には「Machine-verified (PR 作成後 CI で実証 → CI 完了後に本文 update)」section で 2 項目を `[ ]` で残してある。Step 1-3 で全 pass 確認できた段階で、本文の該当行を `[x]` に置換し `gh pr edit` で update。

Run:

```bash
PR_NUM=$(gh pr view --json number --jq '.number')
gh pr view $PR_NUM --json body --jq '.body' > .tmp/pr-body.md
# Edit tool で .tmp/pr-body.md の 2 行を [ ] → [x] に書き換え
# その後:
gh pr edit $PR_NUM --body-file .tmp/pr-body.md
rm .tmp/pr-body.md
```

Expected: `gh pr view $PR_NUM --json body --jq '.body' | grep '\[x\] PR の pull_request trigger CI'` で 1 件 match。

---

## Phase 2: PR レビュー + merge

### Task 9: `/iterate-review` でレビュー fix ループ自走

**Files:**

- なし (skill 起動)

- [ ] **Step 1: `/iterate-review <PR#>` を skill で起動**

Skill tool で `iterate-review` を invoke、args に `<PR#>` を渡す (Step 7-Step 3 で取得した PR 番号)。

Expected: skill が自動で `/review-pr` を fresh subagent で実行、findings を構造化 return、主セッションが (A) 修正 / (B)(C) handoff / push / CI wait を行い、Step 5b 表が全ゼロまたは Round 5 / 発散検知まで繰り返す。

- [ ] **Step 2: skill 完了時に summary comment が PR に投稿されることを確認**

Run:

```bash
gh pr view <PR#> --json comments --jq '.comments[-1] | {author: .author.login, body: .body[:200]}'
```

Expected: 最新 comment が `/iterate-review` の summary。

- [ ] **Step 3: skill が出した未消化 finding を triage**

skill が converge せず Round 5 / 発散検知で終了した場合、残 findings を:

- (A) 本 PR 内追加修正 (Recommended、デフォルト)
- (B) 別 issue 起票 (限定例外)
- (C) 既存 issue 追記 (限定例外)
のいずれかに振り分け。AskUserQuestion で Idios に確認 (Iron Law 5)。

---

### Task 10: merge 実行 + merge 後の develop-0.3.0 push trigger で再 success 確認

**Files:**

- なし (gh / git 操作)

- [ ] **Step 1: PR の CI / review が full pass であることを確認**

Run:

```bash
PR_NUM=$(gh pr view --json number --jq '.number')
gh pr view $PR_NUM --json statusCheckRollup,reviewDecision,mergeable --jq '{rollup: [.statusCheckRollup[] | {name, conclusion}], review: .reviewDecision, mergeable}'
```

Expected: 全 check `success`, `mergeable: "MERGEABLE"`。`reviewDecision` は self-review なら `null`、external review 経由なら `APPROVED`。

- [ ] **Step 2: Idios に merge 承認を求める (Iron Law 5)**

merge は repository に visible / hard-to-reverse な action なので Idios の明示承認を取る。

AskUserQuestion で「PR `#<num>` を develop-0.3.0 に merge してよいか?」を確認:

```text
options:
- Yes、squash merge で実行 (Recommended)
- Yes、merge commit で実行
- No、保留 (理由ヒアリング)
```

- [ ] **Step 3: merge 実行**

Idios が approve した場合のみ実行。

Run (squash merge):

```bash
gh pr merge $PR_NUM --squash --delete-branch=false
```

Expected: `✓ Squashed and merged pull request #<num>`. branch 削除は手動で後ほど (develop-0.3.0 への直接的影響を避ける)。

- [ ] **Step 4: merge 後の develop-0.3.0 push trigger で release.yml が success することを確認**

Run (merge 完了後 1-2 分待ってから):

```bash
sleep 60  # GitHub Actions の trigger 反映待ち
gh run list --branch develop-0.3.0 --workflow release.yml --limit 3 --json databaseId,conclusion,headSha,createdAt
```

Expected: 最新 run の `conclusion=success` (in_progress なら `gh run watch <id>` で待機)、phantom run 解消の本番実証。

- [ ] **Step 5: 直近 success run の artifact 生成も確認**

Run:

```bash
LATEST_RUN=$(gh run list --branch develop-0.3.0 --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view $LATEST_RUN
```

Expected: `Artifacts: allaganeye-windows-v0.3.0, allaganeye-baseline-v0.3.0` が表示される。

メモ: 次 task で必要なので `LATEST_RUN` の値を記録 (= Task 11 で使う baseline artifact の source run)。

---

## Phase 3: PR #785 検証 + #752/#786 close

### Task 11: baseline.json artifact 取得 (gh run download)

**Files:**

- 一時 download 先: `.tmp/baseline/baseline.json` (作業後削除)

- [ ] **Step 1: 一時 download dir を作成**

Run:

```bash
mkdir -p .tmp/baseline
```

- [ ] **Step 2: `allaganeye-baseline-v0.3.0` artifact を download**

Run:

```bash
gh run download $LATEST_RUN -n allaganeye-baseline-v0.3.0 -D .tmp/baseline/
```

Expected: `.tmp/baseline/baseline.json` が download される。

- [ ] **Step 3: baseline.json の内容を確認**

Read tool で `.tmp/baseline/baseline.json` を読む。

Expected: JSON structure (file count by top-dir / extension)。スキーマ詳細は `scripts/measure-portable-zip-baseline.ps1` の `-Format Json` 出力を参照。

---

### Task 12: file count metric 抽出 + Before/After table 計算

**Files:**

- なし (data 解析)

- [ ] **Step 1: 修正後 (After) の total file count を抽出**

Read tool で `.tmp/baseline/baseline.json` を読み、`total_file_count` または equivalent field を確認。スキーマが不明な場合は `python -c "import json; print(json.dumps(json.load(open('.tmp/baseline/baseline.json')), indent=2))"` で全体構造を表示。

Expected: integer (推定 ~150-300、Idios PR #785 post-merge comment 記載の expected range)。

- [ ] **Step 2: 修正前 (Before) の total file count を確定**

source: `#752` issue 本文 or PR #785 PR 本文 に記載されている修正前 file count (推定 ~2500)。

Run:

```bash
gh issue view 752 --json body --jq '.body' | grep -iE 'file.*count|ファイル数' | head -5
gh pr view 785 --json body --jq '.body' | grep -iE 'file.*count|before|after' | head -10
```

Expected: 修正前 file count (~2500 と推測されている)。具体値が見つからない場合は AskUserQuestion で Idios に確認 (Iron Law 5)。

- [ ] **Step 3: reduction % を計算**

reduction % = (Before - After) / Before * 100

example: (2500 - 200) / 2500 * 100 = 92%

- [ ] **Step 4: Before/After table を markdown で作成**

format:

```markdown
| Metric | Before (元 ZIP) | After (PyInstaller --onedir) | Reduction |
|---|---:|---:|---:|
| Total file count | 2500 | 200 | 92% |
| Top-dir count | ... | ... | ... |
| Major extensions (.py) | ... | ... | ... |
```

詳細 metric (top-dir / extension breakdown) は baseline.json schema に従って追記。

---

### Task 13: PR #785 に Empirical Validation Report comment 投稿

**Files:**

- なし (gh 操作)

- [ ] **Step 1: comment body を作成**

format:

```markdown
## Empirical Validation Report (#786 release.yml phantom run 解消後の post-merge plan Step 1 実証)

#786 で `release.yml` の phantom run を解消後 (PR #<本 PR num>、merge 後 develop-0.3.0 push trigger run <LATEST_RUN>)、PR #785 の post-merge plan Step 1 を以下の通り完遂。

### 検証結果 (逐条)

- [x] **PyInstaller --onedir frozen build**: 成功 (`Verify allaganeye-gui.exe is bundled` step pass)
- [x] **CI smoke Lv A** (`allaganeye.bat --version`): exit 0 + 'allaganeye' marker 確認
- [x] **CI smoke Lv B** (`allaganeye.bat detect tests/fixtures/smoke_3s.mp4`): exit 0 or 4 (期待値どちらか)
- [x] **CI smoke integrity-fall-through** (`_internal/allaganeye/audio/refs/fanfare.npz` 削除 → `allaganeye.bat --version`): exit 7
- [x] **`allaganeye-baseline-v0.3.0` artifact**: 生成済 (run <LATEST_RUN>)

### Before/After table (#752 受け入れ条件「file count reduction ≥ 80%」)

<Task 12 Step 4 で作成した table を貼る>

### #752 受け入れ条件 verdict

- file count reduction: **<reduction %>%**
- threshold: 80%
- **verdict**: <PASS or FAIL>

<PASS の場合> /close-issue #752 で正式 close する (本 comment 投稿後の次 task)。
<FAIL の場合> #752 受け入れ条件の再評価 (lower target / 追加最適化 issue 起票) を Idios と相談する。

### references

- 本 PR (release.yml 修正): #<本 PR num>
- 元 #786: <issue URL>
- baseline run: <https://github.com/Idios/kobutachan-allaganeye/actions/runs/$LATEST_RUN>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

`<reduction %>` / `<verdict>` / `<本 PR num>` / `<issue URL>` / `<LATEST_RUN>` は Task 11/12 の実値で置換。

- [ ] **Step 2: gh pr comment で投稿**

Run (HEREDOC で UTF-8 安全):

```bash
gh pr comment 785 --body-file - <<EOF
<上記 body>
EOF
```

memory feedback (`feedback_gh_command_ja_heredoc.md`): Windows + Git Bash で日本語含む gh コマンド body は `--body-file -` + HEREDOC が canonical。inline `--body "..."` は cp932 で破損する。

- [ ] **Step 3: comment 投稿成功を確認**

Run:

```bash
gh pr view 785 --json comments --jq '.comments[-1] | {author: .author.login, createdAt, body: .body[:300]}'
```

Expected: 最新 comment が Empirical Validation Report で本人 (Idios or Claude integration account) の投稿。

---

### Task 14: #752 受け入れ条件再検証 + /close-issue #752

**Files:**

- なし (gh / skill 操作)

- [ ] **Step 1: Task 13 verdict を確認**

Task 13 Step 1 で計算した reduction % が **≥ 80%** かを再確認。

- PASS → Step 2 へ
- FAIL → Step 4 (受け入れ条件再評価) へ

- [ ] **Step 2 (PASS path): `/close-issue #752` を skill で起動**

Skill tool で `close-issue` を invoke、args に `752` を渡す。

Expected: skill が merge 後 base ブランチで受け入れ条件再検証 (本 PR の baseline.json metric を根拠として参照)、未消化チェックボックスや残タスクをトリアージし、Idios 承認で `gh issue close 752` を実行。

- [ ] **Step 3 (PASS path): #752 close 完了確認**

Run:

```bash
gh issue view 752 --json state,closedAt --jq '{state, closedAt}'
```

Expected: `{state: "CLOSED", closedAt: "..."}`。

- [ ] **Step 4 (FAIL path): #752 受け入れ条件再評価**

reduction % が < 80% だった場合:

- Idios に AskUserQuestion で「(a) 80% target を維持し追加最適化 issue 起票 / (b) target を実測値に下方修正 / (c) #752 を一旦 close せず保留」の 3 択を問う (Iron Law 5)
- Idios 判断に従って follow-up issue 起票 or target 修正

---

### Task 15: `/close-issue #786` (本 issue close)

**Files:**

- なし (skill 操作)

- [ ] **Step 1: 本 issue #786 の受け入れ条件 (spec §受け入れ条件) を逐条 check (Iron Law 1)**

spec の受け入れ条件 6 項目を逐条検証:

- [ ] release.yml 修正: `defaults.run.shell` 追加 + 9 step の `shell:` 行削除 (Task 3-5 で完遂、本 PR diff で確認)
- [ ] YAML syntax check 通過: Task 4 Step 1 で `YAML OK` 確認済
- [ ] CI 上で build-windows job 実行成功: Task 8 (PR CI) + Task 10 Step 4 (merge 後 develop-0.3.0 push CI) 両方で確認済
- [ ] artifact 生成: Task 8 Step 3 + Task 10 Step 5 で `allaganeye-windows-v0.3.0` + `allaganeye-baseline-v0.3.0` 確認済
- [ ] PR #785 post-merge plan Step 1 完遂: Task 13 Step 1 の Empirical Validation Report 5 検証で確認済
- [ ] #752 metric 反映: Task 13 で PR #785 に comment 投稿済
- [ ] #752 受け入れ条件再検証: Task 14 で確認済 (PASS なら `/close-issue #752` 完了、FAIL なら follow-up 起票)

全項目 `[x]` なら Step 2 へ。`[ ]` 残あれば該当 task に戻って完遂。

- [ ] **Step 2: `/close-issue #786` を skill で起動**

Skill tool で `close-issue` を invoke、args に `786` を渡す。

Expected: skill が merge 後 base ブランチ (develop-0.3.0) で受け入れ条件再検証、未消化 task をトリアージ、Idios 承認で `gh issue close 786` を実行。

- [ ] **Step 3: #786 close 完了確認**

Run:

```bash
gh issue view 786 --json state,closedAt --jq '{state, closedAt}'
```

Expected: `{state: "CLOSED", closedAt: "..."}`。

- [ ] **Step 4: 一時 file の削除 (cleanup)**

Run:

```bash
rm -rf .tmp/baseline
```

- [ ] **Step 5: 全体完了レポートを本 session に出力**

Claude が text で:

- 本 PR (`#<num>`) merge / close 状況
- #752 close 状況 (PASS or follow-up issue 起票)
- #786 close 状況
- follow-up issue 一覧 (もしあれば)
- 次の作業候補 (例: v0.3.0 release prep、別 issue)

を要約。

---

## Out of scope (本 plan で touch しない)

- main release.yml の同期 backport (元 Option A): v0.3.0 release タイミングの自然 merge で main へ反映される flow を信じる
- #737 PS 5.1 silent regression 検知の強化: 既に develop-0.3.0 で実装済
- release.yml 全体構造の整理 / 簡素化: scope creep、別 issue で
- GitHub Actions schema-level validation の CI 追加 (actionlint 等): scope creep、Task 15 完了後の follow-up issue 候補として記載のみ
- PR #775 R3-1 訂正の修正 (= main paths filter で gating 仮説は誤りだった旨を doc 化): scope creep、別 issue で

## 想定 follow-up issue (本 plan 完了後に Idios が判断して起票)

- actionlint CI 統合 (本件のような schema-invalid を local PR check 段階で検出)
- l2-workflow.md / PR #775 retrospective に「shell: ${{ matrix.shell }} は invalid」の knowledge 記録 (memory `feedback_*.md` に記録するのも valid)
