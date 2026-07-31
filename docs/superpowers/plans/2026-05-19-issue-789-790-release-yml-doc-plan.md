# issue #789 / #790 release.yml doc 整合性 + retrospective 追補 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR #788 deferred findings (issue #789 / #790) を 1 PR で bundled 対応する。release.yml に shell 戦略コメント + R3-1 訂正 retrospective note を追加し、retrospective spec doc に post-spec §9 を追補する。doc only / P3-low / 機能影響ゼロ。

**Architecture:** 2 file (`.github/workflows/release.yml` + `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md`) に doc edit のみ。memory file は任意 (PR 外)。検証は yaml.safe_load + grep + markdownlint で structural validation。

**Tech Stack:** GitHub Actions YAML / markdownlint-cli2 / Python yaml module (validation のみ) / git。

**Spec reference:** `docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md`

---

## File Structure

| File | 役割 | 状態 |
| --- | --- | --- |
| `.github/workflows/release.yml` | Release workflow (PR #788 で `defaults.run.shell` 構造に整理済) | Modify (2 箇所のコメント追加) |
| `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` | v0.2.0 / v0.2.1 retrospective 機構化 + Codex 統合 spec doc (612 行、§1-§8 構成) | Modify (末尾に §9 追加) |
| `docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md` | 本 PR の design doc | Created (commit `61386a1`、本 plan の元) |
| `docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md` | 本 plan doc | Create |
| `~/.claude/projects/.../memory/feedback_github_actions_step_shell_matrix.md` | shell × matrix 不互換 lesson learned (任意) | Create (PR 外) |
| `~/.claude/projects/.../memory/MEMORY.md` | memory index (任意) | Modify (1 行追記、PR 外) |

機能 file (`allaganeye/**`, `gui/**`, `scripts/**`, `tests/**`) は **一切 touch しない**。

---

## Task 1: plan doc を commit

**Files:**

- Create: `docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md`

- [ ] **Step 1: 本 plan doc を作成済確認**

Run: `git status docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md`

Expected: `Untracked files: docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md` (writing-plans skill が本 plan 自体を作成済)

- [ ] **Step 2: markdownlint で 0 errors を確認**

Run: `bash scripts/check-markdownlint.sh 2>&1 | tail -5`

Expected: `Summary: 0 error(s)` (192 files、本 plan 追加で +1 file)

- [ ] **Step 3: plan doc を commit**

```bash
git add docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md
git commit -m "$(cat <<'EOF'
docs(plans): #789 #790 release.yml doc 整合性 + retrospective 追補 plan (focused-ritchie-804caa)

design (docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md
commit 61386a1) に対応する implementation plan。Task 2-7 で release.yml + spec
doc + memory (任意) を順次 commit する手順を bite-sized で記述。

session: focused-ritchie-804caa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: release.yml L28-34 R3-1 訂正 inline comment に retrospective note 追記 (#790)

**Files:**

- Modify: `.github/workflows/release.yml:28-34`

- [ ] **Step 1: 現状 L28-34 を Read で確認**

Run: Read `.github/workflows/release.yml` offset=27 limit=10

Expected: L28 が `# R3-1 訂正 (重要): R2 fix の empirical 検証は **post-merge (develop-0.3.0 → main` で開始し、L34 が `# 0 jobs 維持 (= conclusion=failure だが functional 影響ゼロ) を担保。` で終わる (改変されていないこと)。

- [ ] **Step 2: L34 直下に retrospective note を Edit で追記**

L34 末尾 (`# 0 jobs 維持 (= conclusion=failure だが functional 影響ゼロ) を担保。`) を `old_string` に指定し、その後に retrospective note 7 行を `new_string` で追加。

```python
# Edit tool で以下を実行:
# old_string =
"""# 0 jobs 維持 (= conclusion=failure だが functional 影響ゼロ) を担保。"""

# new_string =
"""  # 0 jobs 維持 (= conclusion=failure だが functional 影響ゼロ) を担保。
  #
  # Retrospective (issue #786 / PR #788): 上記 R3-1 訂正の「main paths filter で
  # gating」仮説は **誤り** だった。真の root cause = `shell: ${{ matrix.shell }}` が
  # GitHub Actions schema-invalid (`jobs.<job_id>.steps[*].shell` field は matrix
  # context をサポートしない、公式 context availability table 参照)。Codex
  # /codex:rescue (agentId a9a21c7545477c99c) で独立調査により確定。PR #788 で
  # `build-windows.defaults.run.shell: ${{ matrix.shell }}` 移行 + step 個別
  # `shell: ${{ matrix.shell }}` 削除 (9 箇所) により解消。R2 fix の paths filter
  # 撤去自体は別目的 (push trigger を strict 判定にして無関係 path push の run 抑止)
  # で benefit があるため維持しているが、phantom run の真因ではなかった。詳細は
  # PR #786 / #788 / docs/superpowers/specs/2026-05-17-...-design.md §9 を参照。"""
```

- [ ] **Step 3: YAML 構文 validation**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8').read()); print('YAML OK')"`

Expected: `YAML OK`

YAML エラーが出たら **commit せず Edit 結果を再確認** (空白インデント・末尾改行を Read で再確認)。

- [ ] **Step 4: structural drift check**

Run:

```bash
grep -nE 'defaults:|shell: \$\{\{ matrix' .github/workflows/release.yml
```

Expected: 2 行のみ (L113 付近 `defaults:` / L115 付近 `shell: ${{ matrix.shell }}`)。PR #788 から不変。

Run:

```bash
grep -n 'shell: bash' .github/workflows/release.yml
```

Expected: 3 件 (`Resolve and verify version` / `Create release archive` / `Extract release notes from CHANGELOG` step、L82 / L403 / L410 付近)。本 task の追記で行番号が +9 行ずれることを許容。

- [ ] **Step 5: Task 2 を commit**

```bash
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
docs(workflow): #790 release.yml R3-1 訂正に retrospective note 追記

PR #775 期間中に出した「main paths filter で gating」R3-1 訂正仮説は誤りで、
真の root cause が `shell: ${{ matrix.shell }}` schema-invalid だったことを
issue #786 → PR #788 で確定したため、L28-34 inline comment 末尾に retrospective
note を 9 行追記。R2 fix (paths filter 撤去) は別目的で維持している旨も明示。

Refs #790 / #786 / #788

session: focused-ritchie-804caa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: release.yml build-windows shell 戦略コメント追加 (#789)

**Files:**

- Modify: `.github/workflows/release.yml` (build-windows job の `name:` 行と `defaults:` 行の間、Task 2 の追記で行番号が +9 ずれているはず)

- [ ] **Step 1: 現状の build-windows block を Read で確認**

Run: `grep -n 'name: build-windows\|defaults:\|strategy:' .github/workflows/release.yml`

Expected: build-windows job 内の `strategy:` / `name: build-windows (${{ matrix.shell }})` / `defaults:` 3 行が連続する区間が 1 箇所のみヒット。

- [ ] **Step 2: shell 戦略コメントを Edit で追記**

```python
# Edit tool で以下を実行:
# old_string =
"""name: build-windows (${{ matrix.shell }})
defaults:"""

# new_string =
"""    name: build-windows (${{ matrix.shell }})
    # build-windows job は matrix.shell (pwsh / powershell dual matrix) を
    # `defaults.run.shell` 経由で適用する。GitHub Actions schema 仕様で
    # `jobs.<job_id>.steps[*].shell` field は matrix context をサポートしない
    # ため (PR #788 / issue #786 で確定)、step 個別の `shell:` 指定では matrix.shell
    # を展開できない。`defaults.run.shell` field は matrix context 参照可能。
    # version-check / release job は ubuntu-latest 上で意図的に `shell: bash`
    # を step 個別指定しているが、これは shell variation 不要なため。
    defaults:"""
```

- [ ] **Step 3: YAML 構文 validation**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8').read()); print('YAML OK')"`

Expected: `YAML OK`

- [ ] **Step 4: structural drift check (Task 2 と同条件)**

Run:

```bash
grep -nE 'defaults:|shell: \$\{\{ matrix' .github/workflows/release.yml
```

Expected: 2 行のみ (Task 2 と同位置の `defaults:` / `shell: ${{ matrix.shell }}`)。本 task のコメント追加では `defaults:|shell: matrix` パターンに新規 hit を作っていないこと。

Run:

```bash
grep -c 'jobs.<job_id>.steps\[\*\].shell' .github/workflows/release.yml
```

Expected: 2 件 (Task 2 で追記した retrospective note 内の 1 件 + 本 task で追記したコメント内の 1 件)。両方で同じ表現を使うことで spec doc §9 / memory file への一貫性を保つ。

- [ ] **Step 5: Task 3 を commit**

```bash
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
docs(workflow): #789 release.yml build-windows shell 戦略をコメントで明示化

build-windows job が defaults.run.shell で matrix.shell を展開し、version-check
/ release job が step 個別 `shell: bash` を使う、という使い分けの理由を 7 行コメント
で明示。step level shell field が matrix context を unsupported な GitHub Actions
schema 仕様 (PR #788 / issue #786 で確定) を canonical knowledge として記録。

Refs #789

session: focused-ritchie-804caa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: retrospective spec doc §9 追補 (#790)

**Files:**

- Modify: `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` (末尾追記、現状 L612 が file 末尾)

- [ ] **Step 1: 現状 spec doc の末尾を Read で確認**

Run: Read `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` offset=595 limit=20

Expected: L599 が `## 8. 関連リンク`、L612 が file 末尾。それ以降に既存 section なし。

- [ ] **Step 2: §9 を末尾に Edit で追記**

末尾行 (`gh issue close <num>` 等、Read で確認した最終行) を `old_string` に指定し、その直後に §9 を `new_string` で追加。

Edit pattern (`old_string` = spec doc の現在の最終行、`new_string` = 最終行 + 改行 + §9 content):

```markdown
## 9. v0.2.x 系 release.yml phantom run retrospective (post-spec 追補)

本節は本 spec doc 確定 (2026-05-17) 後に PR #775 → issue #786 → PR #788 の
ループで判明した release.yml phantom run の真因と、本 spec doc の Risk Register
(§7.1) R3 とは独立した「R3-1 訂正の訂正」を retrospective として記録する。

### 9.1 経緯

- PR #775 (本 spec doc を produce した PR) で release.yml の paths filter 撤去 (R2 fix)
  + 各 job entry に `if:` gating を追加 (Round 1 Finding 3 fix)
- PR #775 期間中 (`/iterate-review` Round 2 → Round 3) に「`push.paths` filter は
  default branch (main) の workflow 定義で評価される known behavior があるため、
  R2 fix の empirical 検証は post-merge 以降の future push でしかできない」と R3-1 訂正
- PR #775 merge 後 develop-0.3.0 で 8 連続 phantom run (`conclusion=failure` /
  `jobs_count=0` / 診断 "This run likely failed because of a workflow file issue.")
- issue #786 で Codex `/codex:rescue` (session `brave-heisenberg-5730dd`、
  agentId `a9a21c7545477c99c`) が真因を独立調査で確定

### 9.2 真因 (Codex finding)

`shell: ${{ matrix.shell }}` が GitHub Actions schema-invalid。`jobs.<job_id>.steps[*].shell`
field は matrix context をサポートしない (公式 [context availability table](https://docs.github.com/en/actions/learn-github-actions/contexts))。
workflow 起動前 schema validation で `Unrecognized named-value: 'matrix'` reject
→ jobs=0 / conclusion=failure となる。R3-1 訂正の「main paths filter で gating」
仮説とは無関係で、main の paths filter 残存とは独立した workflow schema 違反だった。

### 9.3 修正 (PR #788)

`build-windows` job 直下に `defaults.run.shell: ${{ matrix.shell }}` を追加し
(`jobs.<job_id>.defaults.run` field は matrix context 参照可能)、各 step 個別の
`shell: ${{ matrix.shell }}` 行を削除 (9 箇所)。matrix.shell 構造と #737 dual-shell
検証能力 (PS 5.1 silent regression 検知) を維持。`version-check` / `release` job の
`shell: bash` step 3 件は ubuntu-latest 上の意図的 bash 指定で touch しない。

### 9.4 spec doc への implication

- §7.1 R3 (Codex 独断 fix の risk) と本節 R3-1 訂正は **別物**。R3 は本 spec doc が
  対象とする risk、R3-1 訂正は PR #775 review process 中に生まれた誤った仮説で
  本 spec doc 範囲外
- 本節は PR #775 → #786 → #788 のループで得た「workflow schema 違反 phantom run」の
  empirical 知見を spec doc 末尾に追補することで、将来同種事象 (phantom run /
  jobs_count=0 / schema-invalid 仮説) が再発した時に正しい原因仮説を辿れるようにする
- 横展開教訓: workflow YAML で `${{ matrix.* }}` を含む field は GitHub Actions
  公式 context availability table を必ず確認する。step level `shell` は不可、
  job level `defaults.run.shell` は可、`env` block は両方可、等

### 9.5 関連

- 起源 PR: PR #775 (R3-1 訂正の元)
- 真因確定 issue: #786
- 真因修正 PR: #788
- doc 整合性 issue: #789 / #790 (本節 + release.yml inline comment retrospective note)
- Codex rescue session: `brave-heisenberg-5730dd` / agentId `a9a21c7545477c99c`
- GitHub Actions context availability: <https://docs.github.com/en/actions/learn-github-actions/contexts>
```

- [ ] **Step 3: markdownlint で 0 errors 確認**

Run: `bash scripts/check-markdownlint.sh 2>&1 | tail -5`

Expected: `Summary: 0 error(s)` (192 files)。

markdownlint が違反を報告した場合、`docs/markdownlint-guide.md` を参照して fix。よく出る違反:

- MD038 (Spaces inside code span elements): code span 内に leading/trailing space を入れていないか確認
- MD026 (Trailing punctuation in heading): `### 9.1 経緯` 等の見出し末尾に `.` を付けていないか
- MD025 (Multiple top-level headings): `## 9.` を使い、`# 9.` ではないこと

- [ ] **Step 4: section 番号一意性確認**

Run: `grep -n '^## ' docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md`

Expected: 9 行 (`## 1. 背景` 〜 `## 9. v0.2.x 系 release.yml phantom run retrospective (post-spec 追補)`)。重複番号なし。

Run: `grep -n '^### ' docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md | tail -10`

Expected: 末尾に `### 9.1 経緯` / `### 9.2 真因 (Codex finding)` / `### 9.3 修正 (PR #788)` / `### 9.4 spec doc への implication` / `### 9.5 関連` の 5 行がある。

- [ ] **Step 5: Task 4 を commit**

```bash
git add docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md
git commit -m "$(cat <<'EOF'
docs(specs): #790 2026-05-17 retrospective spec に §9 post-spec 追補

PR #775 確定後の issue #786 → PR #788 ループで判明した release.yml phantom run の
真因 (`shell: ${{ matrix.shell }}` schema-invalid) と「R3-1 訂正の訂正」を §9 として
spec doc 末尾に追補。§7.1 Risk Register R3 (Codex 独断 fix risk) とは別物である旨を
§9.4 で明示。横展開教訓 (matrix context availability table 参照習慣) も記録。

Refs #790 / #786 / #788 / #775

session: focused-ritchie-804caa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 全体 validation (spec §5.1 全 check 走査)

**Files:** なし (validation のみ)

- [ ] **Step 1: YAML 構文 validation**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8').read()); print('YAML OK')"`

Expected: `YAML OK`

- [ ] **Step 2: structural drift check (PR #788 から不変)**

Run:

```bash
grep -nE 'defaults:|shell: \$\{\{ matrix' .github/workflows/release.yml
```

Expected: 2 行 (`defaults:` / `shell: ${{ matrix.shell }}`)。PR #788 から不変。

Run:

```bash
grep -n 'shell: bash' .github/workflows/release.yml
```

Expected: 3 件 (`Resolve and verify version` / `Create release archive` / `Extract release notes from CHANGELOG`)、PR #788 から不変。

- [ ] **Step 3: markdownlint 全 file**

Run: `bash scripts/check-markdownlint.sh 2>&1 | tail -5`

Expected: `Summary: 0 error(s)` (193 files: 既存 191 + plan + design)。

- [ ] **Step 4: git diff stat (scope creep check)**

Run: `git diff --stat origin/develop-0.3.0..HEAD`

Expected:

- `.github/workflows/release.yml` (+16-18 行、Task 2 + Task 3 の合計)
- `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` (+40-50 行、Task 4)
- `docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md` (+319 行、design doc / commit 61386a1 既出)
- `docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md` (+本 plan 行数、Task 1)

機能 file (`allaganeye/**`, `gui/**`, `scripts/**`, `tests/**`) の touch が 0 件 であること。

```bash
git diff --stat origin/develop-0.3.0..HEAD | grep -E 'allaganeye/|gui/|scripts/|tests/'
```

Expected: 出力なし (0 行)。

- [ ] **Step 5: branch / commit graph 確認**

Run: `git log --oneline origin/develop-0.3.0..HEAD`

Expected: 5 commit 程度 (design doc / plan doc / Task 2 / Task 3 / Task 4)。順序は時系列で違和感ないこと。

---

## Task 6: Iron Law 6 Pre-flight Step 0-5 + PR 作成

**Files:** なし (PR 作成のみ)

- [ ] **Step 1: Pre-flight Step 0 ハードゲート (元 issue 検索、<1s)**

Run: `gh pr list --search "#789" --state open`

Expected: `[]` または empty list (重複 PR ゼロ)。

Run: `gh pr list --search "#790" --state open`

Expected: `[]` または empty list。

`#789 OR #790` で別 PR が存在する場合は STOP し AskUserQuestion で確認。

- [ ] **Step 2: Pre-flight Step 1 base 同期**

Run: `git fetch origin develop-0.3.0`

Expected: fetch 完了 (no error)。

- [ ] **Step 3: Pre-flight Step 2 取り込み未済 commit**

Run: `git log HEAD..origin/develop-0.3.0 --oneline`

Expected: 出力なし (= base から divergence なし、本 worktree が origin/develop-0.3.0 の最新を反映済)。divergence あれば rebase してから次へ。

- [ ] **Step 4: Pre-flight Step 3 touched files 交差判定**

Run:

```bash
git diff --name-only origin/develop-0.3.0..HEAD
```

Expected: 下記 4 file のみ:

- `.github/workflows/release.yml`
- `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md`
- `docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md`
- `docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md`

origin/develop-0.3.0 で merge 済の touched files との交差で、本 PR と conflict しそうなものがあれば AskUserQuestion で確認。

- [ ] **Step 5: Pre-flight Step 4 並行 PR 重複再確認**

Run: `gh pr list --search "#789" --state all`

Run: `gh pr list --search "#790" --state all`

Expected: 本 PR 以外の関連 PR ゼロ。`/iterate-review` Round 後の重複作成も無いことを確認。

- [ ] **Step 6: Pre-flight Step 5 Codex adversarial-review**

Run: `/codex:adversarial-review` を invoke (focus: 「Iron Law 3 scope creep / encoding boundary / R3-1 retrospective note の誤情報 / spec doc §9 と §7.1 R3 の混乱可能性 / 同 issue 過去 PR の root cause 再発」を明示)。

Expected: high/critical 指摘ゼロ、または medium 以下のみ (medium 1 件以下は (A) PR 内修正、高 finding は LGTM 不可)。

Codex がトークン枯渇 / network fail で起動できない場合は `superpowers:requesting-code-review` subagent を fallback (skill report に「Codex fallback notice」必須記載、CLAUDE.md §Codex 運用 §Token 枯渇時の fallback 参照)。

- [ ] **Step 7: branch push**

Run: `git push -u origin claude/focused-ritchie-804caa`

Expected: push 成功。CI が pull_request trigger を待たないので、PR 作成後に CI が走る。

- [ ] **Step 8: PR 作成**

Run:

```bash
gh pr create --base develop-0.3.0 --title "docs(workflow): #789 #790 release.yml shell 戦略 + R3-1 訂正 retrospective 追補" --body "$(cat <<'EOF'
## 期待値

PR #788 `/iterate-review` Round 1 で deferred した 2 件 (issue #789 / #790) を 1 PR で
bundled 対応する。release.yml に shell 指定戦略コメント + R3-1 訂正 retrospective note
が追加され、retrospective spec doc に §9 post-spec retrospective が追補される。
doc only / P3-low / 機能影響ゼロ。

## 現状

- `.github/workflows/release.yml` L28-34 R3-1 訂正 inline comment は「main paths filter
  で gating」仮説のまま (誤り、PR #786 → #788 で確定済)
- `.github/workflows/release.yml` build-windows job の `defaults.run.shell` 採用理由が
  実装内コメント無し (PR #788 履歴を遡らないと読み解けない)
- `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` に
  R3-1 訂正の retrospective 記録なし

## ユーザー影響 / 重要性

- 将来 release.yml を編集する人 (Claude / Idios) が誤った原因仮説 (main paths filter)
  を参照して二度手間になるリスク (P3-low、機能影響なし)
- shell 指定戦略の自由度 (matrix context unsupported) が implicit knowledge のまま

## 修正内容

詳細設計: `docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md`
実装 plan: `docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md`

- `.github/workflows/release.yml` L28-34 R3-1 訂正 inline comment 末尾に retrospective
  note 9 行追記 (#790)。「main paths filter 仮説は誤り、真因 = schema-invalid」を明示
- `.github/workflows/release.yml` build-windows `name:` 行と `defaults:` 行の間に shell
  戦略コメント 7 行追記 (#789)。step level shell field が matrix context unsupported な
  GitHub Actions schema 仕様を canonical knowledge として記録
- `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` 末尾に
  §9「v0.2.x 系 release.yml phantom run retrospective (post-spec 追補)」を追加 (#790)。
  §7.1 R3 (Codex 独断 fix risk) と R3-1 訂正は別物である旨を §9.4 で明示

機能 file (`allaganeye/**`, `gui/**`, `scripts/**`, `tests/**`) の touch なし。

## Self-Test Report

### Machine-verified (PR 作成時点 / local 検証)

- [x] `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8').read())"` → YAML OK
- [x] `grep -nE 'defaults:|shell: \$\{\{ matrix' .github/workflows/release.yml` → 2 行 (PR #788 から不変)
- [x] `grep -n 'shell: bash' .github/workflows/release.yml` → 3 件 (Resolve and verify version / Create release archive / Extract release notes from CHANGELOG、不変)
- [x] `bash scripts/check-markdownlint.sh` → 0 errors (193 files)
- [x] `git diff --stat origin/develop-0.3.0..HEAD` → 4 files (release.yml + spec doc + design doc + plan doc)、機能 file 0 件
- [x] `grep -n '^## ' docs/superpowers/specs/2026-05-17-...-design.md` → 9 行 (重複なし、§9 追加成功)

### Machine-unverifiable (実機 / 主観評価)

- 実機検証 trigger 表対象 path (`gpu_detector.py` / `audio/*.py` / `video/detector.py` / `gui/src-tauri/**`) の touch なし → 実機検証不要 (Idios への AskUserQuestion なし)
- spec doc §9 の文章が「将来 phantom run 類似事象が発生した時に正しい原因仮説を辿れる」readability を満たすか (subjective、`/iterate-review` で評価)

## Iron Law 6 Pre-flight

- [x] Step 0 ハードゲート: `gh pr list --search "#789" --state open` / `#790` ともに重複ゼロ
- [x] Step 1 base 同期: `git fetch origin develop-0.3.0` 完了
- [x] Step 2 取り込み未済 commit: `git log HEAD..origin/develop-0.3.0 --oneline` → ゼロ件
- [x] Step 3 touched files 交差判定: release.yml + spec doc 2 件 + plan doc、機能 file 交差なし
- [x] Step 4 並行 PR 重複再確認: `gh pr list --search "#789 OR #790" --state all` で本 PR のみ
- [x] Step 5 `/codex:adversarial-review`: 実施 (thread `<adversarial-review-thread-id>`)、high/critical 指摘ゼロ

## References

- 設計: [docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md](docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md)
- plan: [docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md](docs/superpowers/plans/2026-05-19-issue-789-790-release-yml-doc-plan.md)
- 起源 PR: #788 (deferred 元)
- 関連 issue: #789 #790
- 真因確定 PR: #786
- Refs #788 #786 #789 #790 #775

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL が返る。`Closes` / `Fixes` / `Resolves` keyword は body に含まない (Iron Law 4)。

- [ ] **Step 9: PR URL を Idios に報告**

PR URL を report。`/iterate-review <PR#>` を起動するか、CI 待ちかを Idios に確認。

---

## Task 7: (任意 / PR 外) memory file 新規作成

PR とは独立。本 task は PR merge 後でも before でも実施可能。memory は project git tree 外なので commit しない。

**Files:**

- Create: `C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\feedback_github_actions_step_shell_matrix.md`
- Modify: `C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\MEMORY.md` (1 行追記)

- [ ] **Step 1: memory file 新規作成**

```python
# Write tool で以下を作成:
# file_path = C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\feedback_github_actions_step_shell_matrix.md
# content =
"""---
name: GitHub Actions step.shell × matrix context 不互換
description: `${{ matrix.* }}` を step 個別 shell field で使うと schema-invalid で phantom run 化する。job level defaults.run.shell を使う
type: feedback
---

GitHub Actions workflow YAML で `jobs.<job_id>.steps[*].shell` field は matrix
context をサポートしない。`shell: ${{ matrix.shell }}` と書くと workflow 起動前
schema validation で reject されて `conclusion=failure` / `jobs_count=0` の
phantom run が記録される (診断: "This run likely failed because of a workflow file issue.")。

**Why**: 公式 [context availability table](https://docs.github.com/en/actions/learn-github-actions/contexts)
で `jobs.<job_id>.steps[*].shell` は matrix unsupported と明記。default branch
の workflow 定義で evaluate される known behavior と相まって、main paths filter
仮説等の二次原因と誤認しやすい (PR #775 R3-1 訂正で実際に誤推定した)。

**How to apply**: matrix context を shell に展開したい時は `jobs.<job_id>.defaults.run.shell`
を使う。step level の `shell:` field は literal 値 (`bash` / `pwsh` / `powershell` 等)
のみ。phantom run / jobs_count=0 / startup_failure を観測したら、まず
`${{ matrix.* }}` を step level field で使っていないか workflow YAML を grep する。

確定: Codex `/codex:rescue` agentId `a9a21c7545477c99c` / PR #786 #788 / 2026-05-19。
"""
```

- [ ] **Step 2: MEMORY.md に index 行追記**

MEMORY.md の最終行を Edit で 1 行追記:

```python
# Edit tool で以下を実行:
# old_string = "- [長い既存 doc に新節を追加する前は全文を topic keyword で grep](feedback_grep_full_doc_before_section_add.md) — l2-workflow.md など 500+ 行の doc は新節案を書く前に grep -n '^## ' (head なし) で全 section 確認 + topic keyword grep。先頭だけ見て新節追加すると既存節と重複 (PR #783 Task 1 で実証、revert + enhance に方針変更コスト発生)"
# new_string = "- [長い既存 doc に新節を追加する前は全文を topic keyword で grep](feedback_grep_full_doc_before_section_add.md) — l2-workflow.md など 500+ 行の doc は新節案を書く前に grep -n '^## ' (head なし) で全 section 確認 + topic keyword grep。先頭だけ見て新節追加すると既存節と重複 (PR #783 Task 1 で実証、revert + enhance に方針変更コスト発生)\n- [GitHub Actions step.shell × matrix 不互換](feedback_github_actions_step_shell_matrix.md) — `${{ matrix.* }}` を step shell で使うと phantom run 化。defaults.run.shell に逃がす"
```

- [ ] **Step 3: memory 整合性確認**

Run: `wc -l C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\MEMORY.md`

Expected: 既存行数 + 1 (1 行追加)。

memory file は git commit しない (project 外、user 個別)。

---

## Self-Review

### Spec coverage

| spec §6 受け入れ基準 | 対応 task |
| --- | --- |
| §6.1 build-windows shell 戦略コメント 5-6 行 | Task 3 Step 2 |
| §6.1 step level / defaults.run.shell / version-check 等の説明 | Task 3 Step 2 (コメント内容) |
| §6.1 PR #788 / issue #786 back-reference | Task 3 Step 2 (コメント内容) |
| §6.1 既存 L106-108 (M1 dual-matrix) を touch しない | Task 3 Step 2 (`old_string` = `name:...defaults:` のみ、M1 コメントは old_string に含めない) |
| §6.2 R3-1 訂正 inline comment 末尾に retrospective note | Task 2 Step 2 |
| §6.2 既存 R3-1 訂正 comment を書き換えない | Task 2 Step 2 (`old_string` = 末尾行のみ、L28-33 は touch しない) |
| §6.2 retrospective note の必須記載項目 | Task 2 Step 2 (コメント内容、Codex agentId / PR #786 #788 / spec §9 back-ref 含む) |
| §6.2 spec doc §9 追加 (§8 関連リンクの後ろ) | Task 4 Step 2 |
| §6.2 §9.1-§9.5 構成 | Task 4 Step 2 (5 subsection 全て含む) |
| §6.2 §9.4 で §7.1 R3 と R3-1 訂正の別物明記 | Task 4 Step 2 (§9.4 内容) |
| §6.2 memory file (任意 / PR 外) | Task 7 |
| §6.3 機能 file touch なし | Task 5 Step 4 |
| §6.3 shell: bash step (L82/L403/L410) touch なし | Task 2 Step 4 / Task 3 Step 4 (grep で 3 件確認) |
| §6.3 local check (§5.1) 全 pass | Task 5 Step 1-3 |
| §6.3 Iron Law 6 Pre-flight 全 pass | Task 6 Step 1-6 |
| §6.3 (A) PR 内修正優先で iterate-review 完走 | Task 6 Step 9 (PR URL 報告後、Idios judgment) |

全項目に対応 task あり。gap なし。

### Placeholder scan

- TBD / TODO / FIXME / 「あとで」「未定」 → 本 plan 内に **0 件** (writing-plans skill が禁止するパターン)
- 「Add appropriate error handling」「handle edge cases」等の vague step → なし
- 「Similar to Task N」(code 省略) → なし。Task 2 / 3 / 4 のコメント内容はそれぞれ full text を記述
- 行番号 references (L28-34 / L82 / L106-108 / L112 / L113 / L403 / L410 / L599 / L612) → 全件 spec doc §1-3 と一致確認済

### Type consistency (doc only のため file path / git command syntax の一貫性)

- `.github/workflows/release.yml` path 表記 全 task で統一
- `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` path 全 task で統一
- git commit message format (`docs(scope): #issue 内容` + Co-Authored-By + session) Task 2 / 3 / 4 で統一
- grep pattern (`defaults:|shell: \$\{\{ matrix` / `shell: bash`) Task 2 / 3 / 5 で同一
- agentId `a9a21c7545477c99c` (Codex rescue) は Task 2 / 4 / 7 で同じ

問題なし。

---

## 補足: failure modes / 復旧手順

| failure | 兆候 | 対処 |
| --- | --- | --- |
| Task 2/3 Edit で `old_string` not found | Edit tool が "not unique" or "not found" エラー | Read で該当行を確認し、空白・改行・全角/半角を厳密に一致させる。再 Edit |
| Task 2/3 後の YAML 構文 error | `python -c "import yaml; ..."` が `yaml.YAMLError` を raise | 直前の Edit を git checkout で巻き戻し、空白インデント・末尾改行・コメント prefix `#` を Read で再確認 |
| Task 4 後の markdownlint MD038 violation | `Spaces inside code span elements` | inline code 内の leading/trailing space を除去 (例: \`    name:\` → \`name:\` + 別途空白 indent 説明) |
| Task 5 で機能 file touch 検出 | Task 5 Step 4 の機能 path grep が 1 件以上ヒット | STOP し、commit 履歴を `git log --stat` で確認。誤って touch していたら `git checkout origin/develop-0.3.0 -- <path>` で revert |
| Task 6 Step 6 Codex adversarial-review が high finding | high / critical 指摘 | (A) PR 内修正、または scope creep risk あれば AskUserQuestion で「PR 内修正 / 別 issue / 無視」の 3 択 |
| Task 6 Step 1/5 で重複 PR 検出 | `gh pr list --search "#789 OR #790"` で本 PR 以外がヒット | STOP し AskUserQuestion で確認 (Iron Law 6 Pre-flight Step 0 / 4 違反防止) |

---

## 関連リンク

- 設計: `docs/superpowers/specs/2026-05-19-issue-789-790-release-yml-doc-design.md` (commit `61386a1`)
- 起源 PR: #788 (`/iterate-review` Round 1 で deferred、本 plan の発端)
- 関連 issue: #789 / #790
- 真因確定 PR: #786 (PR #788 の元)
- 起源 spec doc: `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md`
- Codex rescue session: `brave-heisenberg-5730dd` / agentId `a9a21c7545477c99c`
- CLAUDE.md §Codex 運用 §Token 枯渇時の fallback (Task 6 Step 6 fallback の根拠)
- l2-workflow.md §PR 作成 Pre-flight (Task 6 Step 1-6 の根拠)
