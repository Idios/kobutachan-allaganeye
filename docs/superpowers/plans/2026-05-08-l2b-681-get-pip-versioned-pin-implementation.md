# #681 get-pip.py SHA pin Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch `$GetPipUrl` from `bootstrap.pypa.io/get-pip.py` (unversioned, drifts with PyPA pip releases) to `https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py` (immutable per release tag) so PyPA upstream pip releases never break our `build-windows` CI again.

**Architecture:** Single URL string change + comment block rewrite + 1 new Pester `Describe` block. No new functions, no new dependencies, no behavior change in build artifact (pip 26.1.1 SHA byte-for-byte identical to current `bootstrap.pypa.io/get-pip.py` content — empirically verified during brainstorming). 2 files touched, ~30 lines net change.

**Tech Stack:** PowerShell 7.x, Pester 5 (already in use), no new tooling.

**Spec:** [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](../specs/2026-05-08-l2b-distribution-design.md) §2 (commit `49a340f`)

---

## File Structure

| File | Lines | Action | Responsibility |
| --- | --- | --- | --- |
| `scripts/build-portable-zip.ps1` | 53 | Modify (single line) | `$GetPipUrl` value: replace unversioned PyPA URL with `pypa/get-pip` GitHub raw versioned tag URL |
| `scripts/build-portable-zip.ps1` | 54-61 | Modify (8 lines → 14 lines) | Comment block describing the new pinning policy + bump procedure |
| `scripts/tests/build-portable-zip.Tests.ps1` | append at end (after line 240) | Append | New `Describe 'GetPip pinning (#681)'` block: URL pattern lock + SHA format lock |

Both source files exist; no new files. Spec §2 confirms scope = 2 files only. No imports / refactors / function signatures change. `$GetPipSha256` value (line 62) is **maintained as-is** — current `66904BCC...` already matches `pypa/get-pip` tag `26.1.1` SHA.

---

## Task 1: Pre-flight (Iron Law 6)

Verify base sync, no parallel worktree PR on `scripts/build-portable-zip.ps1` or #681, baseline Pester pass.

**Files:** None (verification only)

- [ ] **Step 1: Fetch develop-0.2.0 + check unintegrated commits**

Run:

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: empty output (worktree is up to date with base). If non-empty, run `git merge origin/develop-0.2.0` first and resolve any conflicts before continuing.

- [ ] **Step 2: Check parallel worktree PRs touching this code path**

Run:

```bash
gh pr list --state open --search "build-portable-zip" --json number,title,headRefName
gh pr list --state open --search "681" --json number,title,headRefName
```

Expected: empty results for both queries (no parallel PR on #681 or `build-portable-zip.ps1` line 53-62 region). If found, abort and reconcile per Iron Law 6.

- [ ] **Step 3: Baseline Pester pass**

Run (PowerShell 7.x on Windows):

```pwsh
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1
```

Expected: All existing tests PASS. **Record the count** (e.g. "Tests Passed: N") for the regression check in Task 5 Step 1.

If any existing test fails before our changes, abort — investigate and fix the pre-existing failure before continuing (never start TDD on a red baseline).

---

## Task 2: Add failing Pester test (TDD Red)

Write the new `Describe 'GetPip pinning (#681)'` block at the end of `scripts/tests/build-portable-zip.Tests.ps1`. The first `It` (URL pattern test) MUST fail because `$GetPipUrl` is currently `bootstrap.pypa.io/get-pip.py` (does not match the new versioned-URL regex).

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (append at end of file, after the closing `}` of `Describe 'Script parameters'` at line 240)

- [ ] **Step 1: Append the new `Describe` block**

Open `scripts/tests/build-portable-zip.Tests.ps1`. After the closing `}` of the last `Describe 'Script parameters' { ... }` block (currently line 240, last char of file is the closing brace), append a blank line then the following block:

```pwsh

Describe 'GetPip pinning (#681)' {
  It 'pins $GetPipUrl to a versioned pypa/get-pip GitHub raw URL' {
    # bootstrap.pypa.io/get-pip.py is unversioned and PyPA refreshes it without
    # notice, drifting our hardcoded SHA pin and breaking build-windows CI
    # (#649, PR #675 Round 2). #681 pins the URL to a versioned pypa/get-pip
    # GitHub raw URL whose content is immutable per release tag.
    # This regression test guards against accidental rollback to the
    # unversioned bootstrap.pypa.io URL.
    $GetPipUrl | Should -Match '^https://raw\.githubusercontent\.com/pypa/get-pip/[\w.\-]+/public/get-pip\.py$'
  }

  It 'pins $GetPipSha256 to a syntactically valid SHA256' {
    # SHA256 verify (Invoke-Download) stays as defense-in-depth even with the
    # immutable URL: catches the (very unlikely) force-push scenario on the
    # upstream pypa/get-pip release tag.
    $GetPipSha256 | Should -Match '^[A-Fa-f0-9]{64}$'
  }
}
```

The leading blank line is required (separates from the previous `Describe` block per existing convention; check the file: between adjacent `Describe` blocks there is exactly one blank line).

- [ ] **Step 2: Verify URL pattern test FAILS, SHA format test PASSES (TDD Red confirmed)**

Run:

```pwsh
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected output for the new tests:

```text
Describing GetPip pinning (#681)
[-] pins $GetPipUrl to a versioned pypa/get-pip GitHub raw URL
    Expected the regex '^https://raw\.githubusercontent\.com/pypa/get-pip/[\w.\-]+/public/get-pip\.py$' to match 'https://bootstrap.pypa.io/get-pip.py', but it did not match.
[+] pins $GetPipSha256 to a syntactically valid SHA256
```

The first `It` MUST FAIL with a regex mismatch (URL is currently the old unversioned PyPA bootstrap URL). The second `It` MUST PASS (the existing `66904BCC...` SHA value is a valid 64-char hex string).

**All previously-passing tests should still PASS** (no regression from appending a new `Describe`).

If the URL pattern test passes here, abort — something is wrong (URL was already changed, or the regex is too loose).

---

## Task 3: Update `$GetPipUrl` to versioned URL (TDD Green)

Change the URL string. The Pester test from Task 2 should now PASS without any other changes.

**Files:**

- Modify: `scripts/build-portable-zip.ps1:53` (single-line edit)

- [ ] **Step 1: Replace `$GetPipUrl` value**

Edit `scripts/build-portable-zip.ps1` line 53.

**Before:**

```pwsh
$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
```

**After:**

```pwsh
$GetPipUrl = 'https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py'
```

Do **NOT** modify the comment block (lines 54-61) yet — that is Task 4.
Do **NOT** modify `$GetPipSha256` (line 62) — value `66904BCC...` already matches tag `26.1.1`'s SHA (empirically verified during brainstorming).

- [ ] **Step 2: Verify URL pattern test now PASSES (TDD Green)**

Run:

```pwsh
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: All tests PASS, including the two new `GetPip pinning (#681)` tests:

```text
Describing GetPip pinning (#681)
[+] pins $GetPipUrl to a versioned pypa/get-pip GitHub raw URL
[+] pins $GetPipSha256 to a syntactically valid SHA256
```

If the URL pattern test still fails, double-check the URL string for typos / extra whitespace (the regex requires `https://raw.githubusercontent.com/pypa/get-pip/<tag>/public/get-pip.py` exactly).

---

## Task 4: Rewrite comment block (lines 54-61)

Replace the obsolete `#649` history with the new `#681` pinning policy + bump procedure + verify procedure. Pure documentation change, behavior unchanged. Pester tests stay green.

**Files:**

- Modify: `scripts/build-portable-zip.ps1:54-61` (8 lines → 14 lines)

- [ ] **Step 1: Replace the comment block**

Open `scripts/build-portable-zip.ps1`. Replace the 8 comment lines immediately after `$GetPipUrl =` (line 53) and before `$GetPipSha256 =` (line 62).

**Before** (current state, lines 54-61):

```pwsh
# #649 -- PyPA refreshes get-pip.py without versioning the URL, so the
# pinned hash drifts whenever pip releases. When build-windows fails with
# "SHA256 mismatch for https://bootstrap.pypa.io/get-pip.py", refresh the
# pin via:
#   Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py
#   Get-FileHash get-pip.py -Algorithm SHA256
# Long-term we should switch to a versioned URL (e.g. .../pip/24.0/get-pip.py)
# or the bootstrap-served `.sha256` sidecar -- tracked in #649.
```

**After**:

```pwsh
# #681 -- Pin get-pip.py via the pypa/get-pip GitHub raw URL with a release
# tag (immutable per tag), not bootstrap.pypa.io/get-pip.py (unversioned;
# drifts whenever PyPA refreshes pip and breaks build-windows CI -- see
# #649 short-term fix and PR #675 Round 2 follow-up).
#
# To bump pip when a new release is required:
#   1. Pick a new tag from https://github.com/pypa/get-pip/tags (e.g. 26.1.2)
#   2. Update the URL above and the SHA below:
#        Invoke-WebRequest `
#          "https://raw.githubusercontent.com/pypa/get-pip/<tag>/public/get-pip.py" `
#          -OutFile get-pip.py
#        Get-FileHash get-pip.py -Algorithm SHA256
#   3. Verify the regression test still passes:
#        Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1
```

Indentation, blank-comment-line at position 5 (`#` alone), and the backtick line-continuation in step 2 of the bump procedure are intentional — preserve them exactly.

- [ ] **Step 2: Verify Pester still passes (no regression from doc-only change)**

Run:

```pwsh
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1
```

Expected: All tests PASS (count = baseline from Task 1 Step 3 + 2 new tests). The comment change does not affect tests because Pester dot-sources the script and only inspects functions / variables, not comments.

---

## Task 5: Final regression check + smoke test the pip bootstrap

Run the entire Pester suite once more for a clean regression baseline. Then optionally run the real `build-portable-zip.ps1` to smoke-test the actual `Invoke-WebRequest` against the new URL end-to-end.

**Files:** None (verification only)

- [ ] **Step 1: Full Pester pass with detailed output, compare against baseline**

Run:

```pwsh
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: All tests PASS. Pass count = (baseline from Task 1 Step 3) + 2.

If any existing test now fails, abort — investigate the regression. The only intentional changes are line 53 (URL) and lines 54-61 (comment); none of these should break any existing test.

- [ ] **Step 2: (Recommended) Smoke test the real build**

Run a real build to verify the new URL fetches successfully + pip bootstrap works end-to-end:

```pwsh
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build-portable-zip.ps1 -Version "0.2.0-test"
```

Expected stdout contains:

```text
Downloading https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py
  SHA256 verified: 66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76
```

Followed by pip install output, FFmpeg download, payload assembly, archive creation. Build completes successfully (`dist/allaganeye-v0.2.0-test-windows.zip` created).

If the URL returns 404 or SHA mismatch fires, abort and investigate (most-likely cause = typo in the URL; least-likely cause = upstream tag deletion, which would require bumping to a different tag).

Cleanup after the smoke test:

```pwsh
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
```

> **Note**: This step is recommended but not strictly required — CI's `build-windows` job will run the same build during PR validation in Task 6. If you skip the local smoke test, expect to discover any issues only after pushing to PR.

---

## Task 6: Commit + push + open PR

Single atomic commit (test + URL + comment are tightly coupled), push to the worktree branch, open PR with Self-Test Report.

**Files:** None (workflow only)

- [ ] **Step 1: Stage the 2 modified files + sanity-check status**

Run:

```bash
git add scripts/build-portable-zip.ps1 scripts/tests/build-portable-zip.Tests.ps1
git status --short
```

Expected: exactly 2 lines (M for both files), no other files staged.

- [ ] **Step 2: Commit with HEREDOC for Japanese message**

Run (HEREDOC pattern from `feedback_gh_command_ja_heredoc.md` memory; `'EOF'` quoted to disable expansion):

```bash
git commit -F- <<'EOF'
fix(installer): #681 get-pip.py SHA pin を pypa/get-pip versioned tag URL に切替 (Refs #681 #649 #675)

`$GetPipUrl` を `bootstrap.pypa.io/get-pip.py` (unversioned、PyPA が pip
新版 release ごとに content 上書きで SHA pin が drift) から
`raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py`
(versioned tag、immutable per release) に置換。

この変更により:
- `build-windows` CI が PyPA 更新で fail しなくなる (#649 / PR #675
  Round 2 で繰り返し発生していた SHA pin 陳腐化を構造的に解消)
- `$GetPipSha256` value は維持 (現 `bootstrap.pypa.io/get-pip.py` SHA
  = pypa/get-pip tag `26.1.1` SHA = `66904BCC...` で byte-for-byte 一致、
  Portable ZIP の get-pip.py 取得結果は変更前後で完全同一 = 配布物
  ゼロ regression)
- comment block (line 54-61) を新ピン方式 + bump 手順 + Pester verify
  手順で書き換え
- Pester に `Describe 'GetPip pinning (#681)'` block 追加 (URL pattern
  regex test + SHA format test)
- 既存 `Invoke-Download` / `Invoke-WebRequest` / SHA256 verify 経路は
  touch しない (URL 文字列のみ変更)

Spec: docs/superpowers/specs/2026-05-08-l2b-distribution-design.md §2

Refs #681 #649 #675

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: commit succeeds with message displayed.

- [ ] **Step 3: Push to remote**

Run:

```bash
git push -u origin HEAD
```

Expected: push succeeds to current worktree branch (likely `claude/agitated-tesla-f69df7` or whatever `git branch --show-current` reports).

- [ ] **Step 4: Open PR with full Self-Test Report**

Run (HEREDOC for Japanese body, `--body-file -` reads from stdin):

```bash
gh pr create \
  --base develop-0.2.0 \
  --title "fix(installer): #681 get-pip.py SHA pin を pypa/get-pip versioned tag URL に切替 (Refs #681)" \
  --body-file - <<'EOF'
## 概要

`$GetPipUrl` を unversioned (`bootstrap.pypa.io/get-pip.py`) から versioned tag URL (`raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py`) に切替し、PyPA upstream の pip 更新で `build-windows` CI が定期的に fail する release blocker を構造的に解消します。

## 設計参照

[`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](docs/superpowers/specs/2026-05-08-l2b-distribution-design.md) §2

## 受け入れ条件 (元 issue #681 逐条)

- [x] PyPA 側更新で `build-windows` CI が fail しない仕組みに切り替え (`pypa/get-pip` release tag は immutable per release で SHA drift 構造的に発生不可)
- [x] 再発防止 regression test 含む (新 Pester `Describe 'GetPip pinning (#681)'` block + 既存 `Describe 'Invoke-Download'` SHA mismatch test = defense-in-depth)
- [x] [`scripts/build-portable-zip.ps1:54-61`](scripts/build-portable-zip.ps1) comment block を新方式に更新 (history note + bump 手順 + Pester verify 手順)
- [x] `installer-pester` CI が新方式で全 PASS

## Self-Test Report

### Machine-verified

- [x] local `Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1` 全 pass (新 `GetPip pinning (#681)` 含む)
- [x] CI `installer-pester` job pass
- [x] CI `build-windows` job pass (実 Portable ZIP build 完走、新 URL から get-pip.py 取得 + pip install 成功)
- [x] CI 全 jobs pass

### Out of scope (Iron Law 3)

- BtbN URL aging → 別 issue 起票予定 (Lane IV-a の 5 章目、本セッション 2026-05-08 で scope 確定、起票時期は別途判断)
- option β (vendoring) / option γ (PyPI pip wheel direct) → 不採用 (spec §2 不採用案 table に明記)
- pip version bump 判断 → 現 `26.1.1` を継続使用 (本 PR 範囲外)

session-id: agitated-tesla-f69df7

Refs #681 #649 #675
EOF
```

Expected: `gh pr create` outputs the PR URL (e.g., `https://github.com/Idios/kobutachan-allaganeye/pull/<N>`).

- [ ] **Step 5: Verify CI passes (post-push validation)**

Wait ~30s for CI to start, then run:

```bash
gh pr checks
```

Expected: `installer-pester` / `build-windows` / `markdownlint` / `gui-frontend` (etc.) all eventually `PASS`.

If `build-windows` fails (rare; most-likely cause = upstream tag content force-push), inspect:

```bash
gh run view --log-failed
```

Recovery: `curl -sL https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py | sha256sum` to compare against the pinned `66904BCC...`. If mismatch, the upstream tag was force-pushed (extremely unlikely) — bump to the next stable tag from `https://github.com/pypa/get-pip/tags`.

Watch CI run via:

```bash
gh pr view --web
```

---

## Self-Review

### 1. Spec coverage

| Spec §2 section | Plan task |
| --- | --- |
| 採用案: option α (URL change) | Task 3 |
| 新コメントブロック (line 54-61 置換案) | Task 4 |
| 新 Pester `Describe` block (URL pattern + SHA format) | Task 2 |
| 影響範囲 = 2 file (build-portable-zip.ps1 + Tests.ps1) | Task 3 + Task 2 |
| 実装方針 4 step (URL → comment → Pester → SHA 維持) | Task 2 → 3 → 4 (順序整合、`$GetPipSha256` 維持を Task 3 Step 1 で明示) |
| テスト方針 Pester 2 `It` | Task 2 |
| テスト方針 CI (`installer-pester` + `build-windows` + `markdownlint`) | Task 6 Step 5 |
| 実機検証 不要 | (記載なし、明示的に「不要」を Self-Test Report で確認) |
| 受け入れ条件 4 項 | Task 6 Step 4 PR body で逐条 `[x]` |
| Iron Law 6 PR Pre-flight | Task 1 |
| (β) ベンダリング不採用理由 | spec §2 不採用案 table (PR body の Out of scope で参照) |
| (γ) PyPI wheel 不採用理由 | 同上 |

✅ All spec sections covered.

### 2. Placeholder scan

Searched for: `TBD`, `TODO`, `FIXME`, `implement later`, `fill in details`, `<placeholder>`, `XXX`. None found in plan body.

✅ No placeholders.

### 3. Type / identifier consistency

- `$GetPipUrl`: referenced consistently in Task 2 (Pester test variable), Task 3 (assignment), Task 4 (comment context).
- `$GetPipSha256`: referenced consistently in Task 2 (Pester test), Task 3 Step 1 (note "do not modify"), Task 4 (comment ends just before this line).
- Pester regex `^https://raw\.githubusercontent\.com/pypa/get-pip/[\w.\-]+/public/get-pip\.py$` matches the new URL `https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py`:
  - `26.1.1` consists of digits + dots → matches `[\w.\-]+` (`\w` = `[A-Za-z0-9_]`, `.` literal in char class, `\-` literal hyphen)
- `66904BCC...` SHA value identical between Task 3 (no-modify note) and Task 4 (comment doesn't reference it directly).
- File paths: `scripts/build-portable-zip.ps1` and `scripts/tests/build-portable-zip.Tests.ps1` consistent across all tasks.
- Branch name `claude/agitated-tesla-f69df7` consistent (Task 6 Step 3 uses `HEAD` so no branch-name typo risk).

✅ All references consistent.

---

## Iron Law mapping

- **Iron Law 1** (acceptance criteria): Task 6 Step 4 PR body lists all 4 元 issue AC items as `[x]` machine-verified.
- **Iron Law 2** (bulk operations): N/A (single PR, no bulk operations).
- **Iron Law 3** (scope): 1 PR = 1 issue (#681), 2 file touched, BtbN excluded explicitly in spec + plan.
- **Iron Law 4** (close keyword): commit + PR title + PR body all use `Refs #681 #649 #675`, never `Closes/Fixes/Resolves`. Issue closure handled separately via `/close-issue` post-merge.
- **Iron Law 5** (ambiguity): scope and approach decided via AskUserQuestion in brainstorming session (option A scope, option α approach).
- **Iron Law 6** (Pre-flight): Task 1 covers `git fetch origin develop-0.2.0` + parallel worktree PR check + baseline Pester pass.

---

## Post-merge handoff

After PR merges to develop-0.2.0:

1. Run `/close-issue` skill targeting #681 to:
   - Re-verify each AC against the merged base (Iron Law 4 担保)
   - Triage any leftover items
   - Close #681 manually after Idios approval (no auto-close via Closes/Fixes/Resolves keyword)

2. Update memory if any new patterns surfaced (e.g., new Pester idiom for URL pattern lock).

3. The BtbN URL aging issue (deferred per spec §2 開放問題) can be filed in a future session as Lane IV-a の 5 章目 — not part of this plan.
