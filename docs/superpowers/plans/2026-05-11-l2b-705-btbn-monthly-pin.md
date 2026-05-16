# #705 BtbN autobuild URL 陳腐化対策 (monthly pin 切替) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/build-portable-zip.ps1` の `$FFmpegBuildTag` を BtbN daily autobuild (`autobuild-2026-05-06-13-32`、~14 日 retention) から **monthly snapshot** (`autobuild-2026-04-30-13-44`、~24 ヶ月 retention) に切替え、Portable ZIP build の URL retention buffer を ~50 倍に拡大する。Pester regression test で monthly pattern を enforce し daily への rollback を防ぐ。

**Architecture:** 単一 build script の 3 定数 (`$FFmpegBuildTag` / `$FFmpegAsset` / `$FFmpegSha256`) 値置換 + 関連 comment block 書き換え + ci.yml / release.yml の同期 (cache key + URL + SHA256 等 5 箇所) + 3 doc の整合 + 1 個の新 Pester `Describe` block + 1 個の新 Format-ReadmeContent test fixture。新規関数 / 新規 dependency なし。touched files = 6 (script 1 + Tests.ps1 1 + yml 2 + doc 3)。

**Tech Stack:** PowerShell 7.x (`Invoke-Download` の `Invoke-WebRequest` + `Get-FileHash` SHA256 verify)、Pester 5 (既存)、bash (CI Linux side: `curl` + `sha256sum`)、`gh api` (BtbN release fetch)。

**Spec:** [`docs/superpowers/specs/2026-05-11-l2b-cleanup-design.md`](../specs/2026-05-11-l2b-cleanup-design.md) §2 (commit `1e372f1`)

**並行可能性:** 同 Lane IV-e の #704 plan ([2026-05-11-l2b-704-pester-bom.md](2026-05-11-l2b-704-pester-bom.md)) と並行実行可。両 PR とも `Tests.ps1` 末尾に `Describe` block を append するため、後着 PR は `git merge origin/develop-0.2.0` で rebase 吸収する (spec §3 conflict 回避策)。

**前提**: brainstorming 時 (2026-05-11) に empirical 取得済の値を本 plan で固定使用:

| 項目 | 値 |
| --- | --- |
| 新 `$FFmpegBuildTag` | `autobuild-2026-04-30-13-44` |
| 新 `$FFmpegAsset` | `ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1` |
| 新 `$FFmpegSha256` (win64) | `e27598e612078f25d3e9cf245ce5042990f2602146e5a6f8287b143b0dce0e95` |
| 新 ci.yml linux64 asset | `ffmpeg-n8.1-11-g75d37c499d-linux64-lgpl-shared-8.1.tar.xz` |
| 新 ci.yml linux64 SHA256 | `b31223cb8074205dd9f908aa032f68826adaefbaee40fcb6be8e34f9b8cb72c4` |
| FFmpeg ref (README 表示) | `g75d37c499d` (OLD format、Get-FFmpegSourceRef 自動抽出) |

Task 1 で final verify する (drift 想定低、empirical 24h 経過なし)。

---

## File Structure

| File | Lines | Action | Responsibility |
| --- | --- | --- | --- |
| `scripts/build-portable-zip.ps1` | 70-81 | Modify | `$FFmpegBuildTag` / `$FFmpegAsset` / `$FFmpegSha256` 値置換 + comment block (line 70-76) を「monthly only / `checksums.sha256` 参照」に書き換え |
| `scripts/tests/build-portable-zip.Tests.ps1` | append at end (after `Describe 'GetPip pinning (#681)'` 閉じ `}`) | Append | 新 `Describe 'BtbN pinning policy (#705)'` block: `$FFmpegBuildTag` の monthly pattern + `$FFmpegAsset` lgpl-shared variant lock |
| `scripts/tests/build-portable-zip.Tests.ps1` | line 233 付近 (`Describe 'Format-ReadmeContent'` 内) | Append | 新 `It` block: `g75d37c499d` ref (#705 specific fixture) で README 出力を verify |
| `.github/workflows/ci.yml` | 22 / 29-34 / 40 | Modify (3 箇所) | Cache key SHA256 / Download URL + 旧 comment 削除 + 新 comment / Install SHA256 を新 linux64 値に同期 |
| `.github/workflows/release.yml` | 99 | Modify (1 箇所) | Cache key SHA256 を新 win64 値に同期 |
| `docs/release-process.md` | 既存 BtbN 記述 (line 72-75 / 152) | Modify | 「monthly snapshot only、daily 禁止」policy 明記、新 tag 値反映 |
| `docs/developer-setup.md` | §9 (line 379-413) | Modify | FFmpeg subsection の hardcoded tag (line 392) bump、bump 手順に「monthly only + `checksums.sha256` 参照」明記 |
| `docs/quickstart.md` | 151 | Modify | hardcoded `n8.1.1` → `g75d37c499d` (OLD format ref) に更新、または generic 化 |

`Get-FFmpegSourceRef` 関数本体 (`scripts/build-portable-zip.ps1:128-`) は **touch 不要** (OLD/NEW 両 format 対応済、本 plan では既存挙動を再利用)。

---

## Task 1: Pre-flight (Iron Law 6 + brainstorming empirical drift 再 verify)

base sync 確認、並行 worktree PR 重複確認、BtbN 上流 monthly tag の存続確認 + asset SHA drift 確認。

**Files:** None (verification only)

- [ ] **Step 1: Fetch develop-0.2.0 + check unintegrated commits**

Run:

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: empty output。非空なら `git merge origin/develop-0.2.0` で取り込み + 該当 file (`scripts/build-portable-zip.ps1` / yml / doc) に conflict ないか verify。

- [ ] **Step 2: Check parallel worktree PRs touching this code path or #705**

Run:

```bash
gh pr list --state open --search "705" --json number,title,headRefName
gh pr list --state open --search "BtbN" --json number,title,headRefName
gh pr list --state open --search "build-portable-zip" --json number,title,headRefName
```

Expected: empty (本 brainstorming 時点 0 件、再確認必須)。1 件以上見つかれば本 PR scope 競合 verify。

- [ ] **Step 3: BtbN monthly tag drift final verify (empirical 再取得)**

Run:

```bash
gh api 'repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-04-30-13-44' --jq '.tag_name + " " + .created_at + " assets:" + (.assets | length | tostring)'
```

Expected: `autobuild-2026-04-30-13-44 2026-04-27T00:23:08Z assets:49` (brainstorming 時点と同値)。tag が消滅していたら本 plan 中止し、Idios `AskUserQuestion` で次月 monthly survivor (`autobuild-2026-05-31-*` が出ていれば そちら) に切替判断。

- [ ] **Step 4: SHA256 drift verify (`checksums.sha256` から再取得)**

Run:

```bash
curl -sL 'https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-04-30-13-44/checksums.sha256' \
  | grep -E 'win64-lgpl-shared-8\.1\.zip$|linux64-lgpl-shared-8\.1\.tar\.xz$' \
  | grep -E 'g75d37c499d'
```

Expected:

```text
e27598e612078f25d3e9cf245ce5042990f2602146e5a6f8287b143b0dce0e95  ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1.zip
b31223cb8074205dd9f908aa032f68826adaefbaee40fcb6be8e34f9b8cb72c4  ffmpeg-n8.1-11-g75d37c499d-linux64-lgpl-shared-8.1.tar.xz
```

SHA mismatch 時は STOP し、本 plan 全体の SHA 値を新値に更新 (BtbN が monthly tag の asset を再 build した可能性、極めて稀)。一致なら以下 task で固定値を使用。

- [ ] **Step 5: Baseline Pester / Python pass**

Run:

```pwsh
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/ -PassThru | Select-Object -Property TotalCount, PassedCount, FailedCount"
```

Expected: `FailedCount: 0`。**Record `TotalCount`** for Task 4 regression check (新 case 2 + Format-ReadmeContent fixture 1 = +3 case)。

```bash
pytest 2>&1 | tail -5
```

Expected: `passed` line 0 fail。本 plan は Python file を touch しないが ci.yml の linux64 FFmpeg を新版に bump するため Python jobs 影響を受けるため baseline 確認必須。

---

## Task 2: 新 Pester `Describe` block + Format-ReadmeContent fixture (TDD Red)

3 個の新 Pester `It` を append (2 個 = 新 `Describe 'BtbN pinning policy (#705)'` / 1 個 = 既存 `Describe 'Format-ReadmeContent'` 内の新 fixture)。Task 3 で実装する前に Red を確認する。

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (file 末尾 + Format-ReadmeContent block 末尾)

- [ ] **Step 1: 新 `Describe 'BtbN pinning policy (#705)'` block を file 末尾に append**

Open `scripts/tests/build-portable-zip.Tests.ps1` で file 末尾 (現存最終 `Describe 'GetPip pinning (#681)'` の閉じ `}` の **次行**) に以下を append:

```pwsh

Describe 'BtbN pinning policy (#705)' {
  It 'pins $FFmpegBuildTag to a BtbN monthly snapshot (end-of-month daily survivor)' {
    # BtbN GCs daily autobuild tags after ~14 days but keeps end-of-month
    # snapshots (autobuild-YYYY-MM-{29,30,31}-*) for ~24 months. Pinning to
    # a monthly snapshot gives the Portable ZIP build a ~24-month retention
    # buffer instead of ~14 days. See #705 for the empirical study.
    # Allowed day suffixes: 28 (Feb non-leap fallback), 29-31.
    $FFmpegBuildTag | Should -Match '^autobuild-\d{4}-\d{2}-(28|29|30|31)-\d{2}-\d{2}$'
  }

  It 'pins $FFmpegAsset to a win64-lgpl-shared variant matching the build tag epoch' {
    # Defense-in-depth: catches accidental rollback to a stale asset name
    # that doesn't exist in the new monthly tag.
    $FFmpegAsset | Should -Match '^ffmpeg-n[\d.]+(-\d+-g[0-9a-f]+)?-win64-lgpl-shared-[\d.]+$'
  }
}
```

- [ ] **Step 2: 新 Format-ReadmeContent fixture (#705 ref) を既存 `Describe 'Format-ReadmeContent'` 内末尾に append**

`scripts/tests/build-portable-zip.Tests.ps1` の `Describe 'Format-ReadmeContent'` block 内、最後の `It` の閉じ `}` の次行 (現状 line 240 付近、`Describe 'Format-ReadmeContent'` の閉じ `}` の **直前**) に以下を append:

```pwsh

  It 'embeds OLD-format dev ref as commit hash for #705 monthly pin (g75d37c499d)' {
    # #705 monthly pin uses BtbN OLD asset naming (n8.1-11-g75d37c499d-...)
    # because BtbN's release tag (n8.1.1) wasn't yet baked into the
    # 2026-04-30 monthly snapshot. Get-FFmpegSourceRef returns the commit
    # hash via the OLD-format regex, and Format-ReadmeContent renders it as
    # `(commit g75d37c499d)`. This fixture pins that behavior so a future
    # monthly bump that switches back to NEW format (n<patch>) won't silently
    # regress this exact ref representation.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-04-30-13-44' `
      -FFmpegSourceRef 'g75d37c499d'
    $readme | Should -Match '\(commit g75d37c499d\)'
    $readme | Should -Not -Match '\(ref g75d37c499d\)'
  }
```

**実装位置の判定**: `Describe 'Format-ReadmeContent'` の閉じ `}` を find するため `grep -n "^}" scripts/tests/build-portable-zip.Tests.ps1 | head -10` で各 `Describe` の closing brace 行を確認し、該当 block の閉じ `}` の **直前** に挿入。

- [ ] **Step 3: red 確認 (Pester run、3 case が fail を確認)**

Run:

```pwsh
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -PassThru | Select-Object -Property TotalCount, PassedCount, FailedCount"
```

Expected: `FailedCount: 1` (Step 1 で追加した 'pins `$FFmpegBuildTag` to a BtbN monthly snapshot' が daily `autobuild-2026-05-06-13-32` にマッチしないため fail)。`PassedCount` = baseline + 2 (`$FFmpegAsset` lgpl-shared variant test と `g75d37c499d` ref fixture は実装無しでも条件 satisfy で pass)。

**正確に 1 個だけ fail** していることを confirm。`FailedCount > 1` なら Step 2 fixture または Step 1 regex に bug があるため STOP。

- [ ] **Step 4: Commit Pester test 追加 (red 状態で commit)**

```bash
git add scripts/tests/build-portable-zip.Tests.ps1
git commit -m "test(installer): #705 BtbN monthly pin policy + ref fixture を追加 (TDD red)

Tests.ps1 末尾に Describe 'BtbN pinning policy (#705)' block (2 case) を append。
Format-ReadmeContent block に g75d37c499d ref の fixture を 1 case append。
本 commit 時点で daily pin (autobuild-2026-05-06-13-32) なので monthly pattern
test が fail (FailedCount: 1)。Task 3 で monthly pin に切替えて green 化。

Refs #705

session-id: focused-lichterman-5e413f"
```

---

## Task 3: build script 更新 (`scripts/build-portable-zip.ps1`、Green)

`$FFmpegBuildTag` / `$FFmpegAsset` / `$FFmpegSha256` の 3 定数を新 monthly 値に置換、comment block (line 70-76) を「monthly only / `checksums.sha256` 参照」に書き換え。

**Files:**

- Modify: `scripts/build-portable-zip.ps1` line 70-81 (comment + 4 定数、empirical 確認済)

- [ ] **Step 1: `scripts/build-portable-zip.ps1` の line 70-81 を新内容に置換**

旧内容 (現状、commit `080bf5e` 時点):

```pwsh
# FFmpeg is pinned to a specific BtbN autobuild so the same allaganeye tag ships
# the same binary and the LGPLv3 license applies uniformly across CI and Portable ZIP.
# We use the shared variant (wrapper exe + individual avcodec/avfilter/... DLLs)
# rather than the static build to keep Portable ZIP size down (~200 MB vs ~330 MB).
# To update: bump $FFmpegBuildTag / $FFmpegAsset / $FFmpegSha256 together.
# CI workflows (`.github/workflows/ci.yml`) must be updated with the matching
# linux64-lgpl-shared asset at the same build tag; see docs/developer-setup.md § 9.
$FFmpegVersion = '8.1'
$FFmpegBuildTag = 'autobuild-2026-05-06-13-32'
$FFmpegAsset = 'ffmpeg-n8.1.1-win64-lgpl-shared-8.1'
$FFmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$FFmpegBuildTag/$FFmpegAsset.zip"
$FFmpegSha256 = '16F409AB737538778F9CD4BFC69953E2E1DC2558F6DC5CA17CC72083D60DC735'
```

新内容 (置換後):

```pwsh
# FFmpeg is pinned to a BtbN MONTHLY snapshot (the end-of-month daily that
# survives BtbN's ~14-day GC of regular dailies, kept for ~24 months). Daily
# autobuilds are GC'd after ~14 days, so daily pins go 404 in less than a
# month. Only autobuild-YYYY-MM-{28,29,30,31}-* tags survive long enough for
# the Portable ZIP build to remain reproducible. See #705.
# We use the LGPLv3 shared variant (wrapper exe + individual
# avcodec/avfilter/... DLLs) rather than the static build to keep Portable ZIP
# size down (~200 MB vs ~330 MB).
#
# To bump (typically once per year, well before the 24-month retention runs out):
#   1. Pick the latest monthly survivor from
#      https://github.com/BtbN/FFmpeg-Builds/releases (a tag matching
#      autobuild-YYYY-MM-{28,29,30,31}-*; daily tags are forbidden by the
#      `BtbN pinning policy (#705)` Pester regression test).
#   2. Fetch checksums.sha256 from that release and grep for the win64 +
#      linux64 lgpl-shared-8.1 assets to get both SHA256 values:
#        curl -sL "https://github.com/BtbN/FFmpeg-Builds/releases/download/<tag>/checksums.sha256" \
#          | grep -E 'win64-lgpl-shared-8\.1\.zip$|linux64-lgpl-shared-8\.1\.tar\.xz$'
#   3. Update the win64 SHA256 below and `$FFmpegBuildTag` / `$FFmpegAsset`,
#      and update the matching linux64 SHA256 + URL in
#      `.github/workflows/ci.yml` (3 steps: Cache, Download, Install) and the
#      win64 SHA256 in `.github/workflows/release.yml` (Cache step). All four
#      locations must move together (drift is caught by the cache key
#      mismatch). See `docs/developer-setup.md` § 9 for the full checklist.
#   4. Verify regressions:
#        Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1
#        pwsh -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive
$FFmpegVersion = '8.1'
$FFmpegBuildTag = 'autobuild-2026-04-30-13-44'
$FFmpegAsset = 'ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1'
$FFmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$FFmpegBuildTag/$FFmpegAsset.zip"
$FFmpegSha256 = 'E27598E612078F25D3E9CF245CE5042990F2602146E5A6F8287B143B0DCE0E95'
```

**SHA256 は uppercase で記載** (既存値 `16F409AB...` のフォーマットと整合、`Invoke-Download` 内 `.ToUpperInvariant()` で normalize されるが、source 上のフォーマット統一)。

`$FFmpegVersion = '8.1'` は major.minor の系列 ('8.1') を表すため n8.1 + 11 commits でも 不変 (既存挙動)。

- [ ] **Step 2: green 確認 (Pester full pass)**

Run:

```pwsh
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -PassThru | Select-Object -Property TotalCount, PassedCount, FailedCount"
```

Expected: `FailedCount: 0`、`TotalCount` = baseline + 3 (Task 2 で追加した 3 case 全 pass)。

`Get-FFmpegSourceRef` が新 OLD format `ffmpeg-n8.1-11-g75d37c499d-...` から `g75d37c499d` を抽出し、`Format-ReadmeContent` が `(commit g75d37c499d)` を render することで Task 2 Step 2 fixture も pass。

- [ ] **Step 3: ローカル Portable ZIP build dry-run (実 download + SHA verify)**

Run:

```pwsh
pwsh -NoProfile -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive
```

Expected:

- 出力に `Downloading https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-04-30-13-44/ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1.zip` 表示
- 出力に `SHA256 verified: E27598E612078F25D3E9CF245CE5042990F2602146E5A6F8287B143B0DCE0E95` 表示 (Step 1 の値と一致)
- script 末尾 `Build complete` または同等の success message
- exit code 0

`build/portable/allaganeye-v0.2.0-test/` 配下に payload が展開されていることを `ls build/portable/allaganeye-v0.2.0-test/ | head -20` で confirm。

build cache `$env:ALLAGANEYE_BUILD_CACHE_DIR` を使う場合、Step 3 後に `rm -rf $env:ALLAGANEYE_BUILD_CACHE_DIR` でキャッシュ削除し再実行で「実 DL からの SHA verify」を再 verify 推奨。

- [ ] **Step 4: Commit build script 更新**

```bash
git add scripts/build-portable-zip.ps1
git commit -m "fix(installer): #705 BtbN pin を monthly snapshot に切替 (~24ヶ月 retention)

scripts/build-portable-zip.ps1 line 70-81 の \$FFmpegBuildTag /
\$FFmpegAsset / \$FFmpegSha256 を BtbN daily autobuild
(autobuild-2026-05-06-13-32、~14日 retention) から monthly snapshot
(autobuild-2026-04-30-13-44、~24ヶ月 retention) に切替え。

empirical 調査結果 (本 spec brainstorming 時、focused-lichterman-5e413f):
- daily tag retention: ~14日 (現 pin は ~25-30日で 404 確実)
- monthly survivor (各月末日 daily) retention: ~24ヶ月
- 全37 tag 中、最古は autobuild-2024-06-30 (~23ヶ月前)

新 SHA256 は checksums.sha256 sidecar から取得 (release ごと 1 file 提供)。
comment block を「monthly only / checksums.sha256 参照 / yearly bump」方針
に書き換え。Get-FFmpegSourceRef は OLD/NEW 両 format 対応済のため touch
不要。Pester regression test (BtbN pinning policy + g75d37c499d fixture)
は前 commit で red 状態で append 済、本 commit で green 化。

Refs #705

session-id: focused-lichterman-5e413f"
```

---

## Task 4: ci.yml / release.yml 更新

CI workflow 2 file の 4 箇所を新 SHA256 + 新 URL に同期。

**Files:**

- Modify: `.github/workflows/ci.yml` line 22 (cache key) + line 29-34 (Download URL + comment) + line 40 (Install SHA256)
- Modify: `.github/workflows/release.yml` line 99 (cache key)

- [ ] **Step 1: ci.yml line 22 (Cache key) を更新**

旧:

```yaml
          key: btbn-ffmpeg-linux64-lgpl-shared-8.1-ec7546052026c12079e5bc4c69ff811c40f5b44610d8854cca17dda8e192529f
```

新:

```yaml
          key: btbn-ffmpeg-linux64-lgpl-shared-8.1-b31223cb8074205dd9f908aa032f68826adaefbaee40fcb6be8e34f9b8cb72c4
```

cache key に SHA256 を埋め込んでいるため、SHA256 変更で cache が自動 invalidate される。

- [ ] **Step 2: ci.yml line 24-34 の Download step (URL + comment) を更新**

旧:

```yaml
      - name: Download FFmpeg archive (cache miss)
        if: steps.cache-ffmpeg.outputs.cache-hit != 'true'
        shell: bash
        run: |
          set -euo pipefail
          # BtbN は nightly autobuild を一定期間で削除するため URL pin が陳腐化する。
          # 上流が `n8.1.1` (FFmpeg patch release) に切り替わった (2026-05-06 build)。
          # BtbN URL aging の長期対応は別 issue で追跡予定 (Lane IV-a の 5 章目)。
          # #681 は get-pip.py SHA pin の versioned URL 切替に scope 限定 (PR #703)。
          # 本 PR (#683) では BtbN 側の短期 fix のみ実施。
          curl -fsSL -o /tmp/ffmpeg.tar.xz "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-05-06-13-32/ffmpeg-n8.1.1-linux64-lgpl-shared-8.1.tar.xz"
```

新:

```yaml
      - name: Download FFmpeg archive (cache miss)
        if: steps.cache-ffmpeg.outputs.cache-hit != 'true'
        shell: bash
        run: |
          set -euo pipefail
          # BtbN は daily autobuild を ~14 日で GC するため、daily pin は ~14 日で 404 する。
          # 各月末日 daily (autobuild-YYYY-MM-{28,29,30,31}-*) は ~24 ヶ月保持されるため
          # monthly snapshot に pin する (#705 で確定、本 PR で daily → monthly に切替)。
          # 2026-04-30 monthly は upstream FFmpeg n8.1 + 11 commits (g75d37c499d、OLD format)。
          # bump 手順 + checksums.sha256 取得方法は scripts/build-portable-zip.ps1 line 70-95 参照。
          curl -fsSL -o /tmp/ffmpeg.tar.xz "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-04-30-13-44/ffmpeg-n8.1-11-g75d37c499d-linux64-lgpl-shared-8.1.tar.xz"
```

- [ ] **Step 3: ci.yml line 36-48 の Install step の `FFMPEG_SHA256` を更新**

旧:

```yaml
      - name: Install ffmpeg (BtbN LGPLv3 n8.1 shared, pinned)
        shell: bash
        run: |
          set -euo pipefail
          FFMPEG_SHA256="ec7546052026c12079e5bc4c69ff811c40f5b44610d8854cca17dda8e192529f"
```

新:

```yaml
      - name: Install ffmpeg (BtbN LGPLv3 n8.1 shared, pinned monthly)
        shell: bash
        run: |
          set -euo pipefail
          FFMPEG_SHA256="b31223cb8074205dd9f908aa032f68826adaefbaee40fcb6be8e34f9b8cb72c4"
```

step 名も `pinned monthly` に更新し、tag が monthly snapshot であることを明示。

- [ ] **Step 4: release.yml line 99 (Cache key) を更新**

旧:

```yaml
          key: btbn-ffmpeg-win64-lgpl-shared-8.1-16f409ab737538778f9cd4bfc69953e2e1dc2558f6dc5ca17cc72083d60dc735
```

新:

```yaml
          key: btbn-ffmpeg-win64-lgpl-shared-8.1-e27598e612078f25d3e9cf245ce5042990f2602146e5a6f8287b143b0dce0e95
```

build-portable-zip.ps1 の `$FFmpegSha256` (Task 3 Step 1 で更新済) と同じ値であることを再 verify (`grep e27598e612 scripts/build-portable-zip.ps1 .github/workflows/release.yml` で 2 箇所一致確認)。

- [ ] **Step 5: yaml syntax check (workflow lint)**

Run:

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo CI_OK
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))" && echo RELEASE_OK
```

Expected: 両方 `CI_OK` / `RELEASE_OK` 表示 (yaml parse 成功)。

(オプション) GitHub Actions 構文 lint を厳密に行うなら `actionlint` を使う:

```bash
which actionlint && actionlint .github/workflows/ci.yml .github/workflows/release.yml
```

actionlint 未インストールなら skip 可 (CI 側で actionlint 等は走らないため必須ではない)。

- [ ] **Step 6: Commit CI yml 更新**

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "ci: #705 ci.yml + release.yml の BtbN pin を monthly snapshot に同期

ci.yml:
- Cache FFmpeg archive cache key の SHA256 を新 linux64 値に更新
- Download FFmpeg archive の URL + comment を新 monthly tag/asset に更新
- Install ffmpeg の FFMPEG_SHA256 を新 linux64 値に更新
- step 名に 'pinned monthly' を追記

release.yml:
- Cache FFmpeg archive cache key の SHA256 を新 win64 値に更新
  (build-portable-zip.ps1 の \$FFmpegSha256 と同値)

build-portable-zip.ps1 (前 commit) と CI 側 4 箇所が drift しないよう、
本 commit で同期完了。

Refs #705

session-id: focused-lichterman-5e413f"
```

---

## Task 5: doc 整合更新 (3 doc)

`docs/release-process.md` / `docs/developer-setup.md` § 9 / `docs/quickstart.md` § 10 を新方針に整合。

**Files:**

- Modify: `docs/release-process.md` (line 72-75 一帯 + 必要なら追加 section)
- Modify: `docs/developer-setup.md` § 9 (line 392 + 397-405 の手順 + line 413 quickstart 参照行)
- Modify: `docs/quickstart.md` line 151

- [ ] **Step 1: `docs/quickstart.md` line 151 を更新**

旧:

```markdown
  - 対応 FFmpeg ソース ref: [git.ffmpeg.org](https://git.ffmpeg.org/ffmpeg.git) の release tag `n8.1.1` (v8.1 系列)
```

新:

```markdown
  - 対応 FFmpeg ソース ref: [git.ffmpeg.org](https://git.ffmpeg.org/ffmpeg.git) の commit `g75d37c499d` (n8.1 + 11 commits、v8.1 系列)
```

将来の bump で release tag (例: `n8.1.1`) に戻る可能性があるため、表現を「commit OR tag」両対応にしたければ:

```markdown
  - 対応 FFmpeg ソース ref: [git.ffmpeg.org](https://git.ffmpeg.org/ffmpeg.git) の n8.1 系列 commit `g75d37c499d` (`scripts/build-portable-zip.ps1` の `$FFmpegAsset` から自動抽出)
```

を選択 (本 plan ではこちらを採用、将来 bump 時の文言変更頻度を下げる)。

- [ ] **Step 2: `docs/developer-setup.md` § 9 の FFmpeg subsection (line 392) を更新**

旧 line 392:

```markdown
### FFmpeg (現在 BtbN LGPLv3 n8.1 shared / `autobuild-2026-05-06-13-32` に固定)
```

新:

```markdown
### FFmpeg (現在 BtbN LGPLv3 n8.1 shared / `autobuild-2026-04-30-13-44` monthly snapshot に固定)
```

line 396-405 の bump 手順を以下に置換:

旧:

````markdown
更新手順:

1. [BtbN/FFmpeg-Builds/releases](https://github.com/BtbN/FFmpeg-Builds/releases) で新しい `autobuild-YYYY-MM-DD-HH-MM` タグを選ぶ
1. 必要な 2 資産 (win64-lgpl-shared-8.1.zip / linux64-lgpl-shared-8.1.tar.xz) の SHA256 を取得:

   ```bash
   gh api repos/BtbN/FFmpeg-Builds/releases/tags/<タグ名> \
     --jq '.assets[] | select(.name | test("n8[.]1.*(win64-lgpl-shared-8[.]1[.]zip|linux64-lgpl-shared-8[.]1[.]tar[.]xz)$")) | {name, digest}'
   ```

1. 以下を**同一タグ・同一 autobuild 系列で**更新 (下表参照)。major version 系列変更 (例: 8.x → 9.x) 時は docs の major version 記述も揃える。cache key に SHA256 が埋め込まれているので、SHA256 を変更すれば CI / release 両方のキャッシュが自動で invalidate される
1. ローカルで Portable ZIP ビルドが緑になることを確認 (`pwsh ./scripts/build-portable-zip.ps1 -Version <version>`) し、PR で CI の `build-windows` と `python` ジョブ両方が通ることを確認する
````

新:

````markdown
更新手順 (#705 monthly snapshot policy):

1. [BtbN/FFmpeg-Builds/releases](https://github.com/BtbN/FFmpeg-Builds/releases) で **monthly snapshot** = タグ名が `autobuild-YYYY-MM-{28,29,30,31}-*` (各月末日 daily が survive したもの) を選ぶ。**daily 中間タグ (例: `autobuild-2026-05-06-13-32`) は禁止** (~14 日で BtbN GC、Pester `BtbN pinning policy (#705)` regression test で reject される)。
1. その release の `checksums.sha256` から win64 + linux64 の 2 資産 SHA256 を取得:

   ```bash
   curl -sL "https://github.com/BtbN/FFmpeg-Builds/releases/download/<タグ名>/checksums.sha256" \
     | grep -E 'win64-lgpl-shared-8\.1\.zip$|linux64-lgpl-shared-8\.1\.tar\.xz$'
   ```

   2 行出力 = 各 asset の SHA256 + ファイル名。BtbN naming は monthly snapshot のタイミングで OLD format (`ffmpeg-n<ver>-<count>-g<commit>-...`) と NEW format (`ffmpeg-n<ver>-...`) のどちらにもなりうる。`Get-FFmpegSourceRef` は両対応済 (`scripts/tests/build-portable-zip.Tests.ps1` の `Describe 'Get-FFmpegSourceRef'` 参照)。
1. 以下 **4 箇所** を**同一タグ・同一 SHA256 系列で**更新 (下表参照)。major version 系列変更 (例: 8.x → 9.x) 時は docs の major version 記述も揃える。cache key に SHA256 が埋め込まれているので、SHA256 を変更すれば CI / release 両方のキャッシュが自動で invalidate される。
1. ローカルで Portable ZIP build が緑になることを確認 (`pwsh ./scripts/build-portable-zip.ps1 -Version <version> -SkipArchive`) し、PR で CI の `build-windows` と `python` と `installer-pester` ジョブが全て通ることを確認する
````

table line 413 を更新:

旧:

```markdown
| `docs/quickstart.md` §10 | 対応 FFmpeg ソース ref (例: `n8.1.1` release tag、または旧 format での commit hash `7f5c90f77e`) の記述 (upstream ref 変更時) |
```

新:

```markdown
| `docs/quickstart.md` §10 | 対応 FFmpeg ソース ref (commit hash の場合は `g<commit>`、release tag の場合は `n<version>`) の記述 (upstream ref 変更時) |
```

- [ ] **Step 3: `docs/release-process.md` の line 72-75 + line 152 を更新**

旧 line 73:

```markdown
    - ダウンロードする外部バイナリ (Python embed / get-pip.py / FFmpeg) はスクリプト内に **SHA256 ダイジェストをハードコードして検証** する。ダイジェスト不一致時はビルドを fail。FFmpeg は BtbN の `autobuild-YYYY-MM-DD-HH-MM` タグと特定アセット名を URL にピン留めして再現性を確保する (`latest` タグは日次更新の可動ポインタなので不可)
```

新 line 73 (1 行追加 + monthly policy 明記):

```markdown
    - ダウンロードする外部バイナリ (Python embed / get-pip.py / FFmpeg) はスクリプト内に **SHA256 ダイジェストをハードコードして検証** する。ダイジェスト不一致時はビルドを fail。FFmpeg は BtbN の **monthly snapshot タグ** (`autobuild-YYYY-MM-{28,29,30,31}-*`、~24 ヶ月 retention) と特定アセット名を URL にピン留めして再現性を確保する (`latest` タグは日次更新の可動ポインタなので不可、daily 中間タグは ~14 日で GC されるため不可。詳細 #705)
```

line 152 は `n8.1` 表記 (major.minor 系列) のため touch 不要 (本 plan で n8.1 系列内変更 = 8.1+11 commits、major.minor 不変)。

- [ ] **Step 4: markdownlint pass**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 errors。`docs/quickstart.md` / `docs/developer-setup.md` / `docs/release-process.md` の編集が markdownlint MD028 / MD056 等に抵触しないことを verify (memory `feedback_markdownlint_typical_fixes.md` 参照、本 plan は table 編集を含むため特に MD056 escape 確認)。

- [ ] **Step 5: Commit doc 更新**

```bash
git add docs/release-process.md docs/developer-setup.md docs/quickstart.md
git commit -m "docs: #705 BtbN pin の monthly snapshot policy を 3 doc に反映

- docs/release-process.md: 'monthly snapshot のみ pin、daily 禁止' policy を line 73 に明記
- docs/developer-setup.md §9: FFmpeg subsection を新 monthly tag/asset に bump、bump 手順を 'monthly only + checksums.sha256 参照' に書き換え、4 箇所更新を明示
- docs/quickstart.md §10: FFmpeg ref を commit/tag 両対応の表現に更新

Refs #705

session-id: focused-lichterman-5e413f"
```

---

## Task 6: ローカル full pass (CI 相当)

PR 提出前に installer-pester / python / markdownlint 相当を full run。

**Files:** None (verification only)

- [ ] **Step 1: Pester full pass**

Run:

```pwsh
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/ -Output Detailed -PassThru | Select-Object -Property TotalCount, PassedCount, FailedCount"
```

Expected: `FailedCount: 0`、`TotalCount` = Task 1 Step 5 baseline + 3 (新 case 2 + Format-ReadmeContent fixture 1)。

- [ ] **Step 2: Portable ZIP build full dry-run (Iron Law 6 path 別自動チェック)**

Run:

```pwsh
pwsh -NoProfile -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive
```

Expected: exit 0、新 monthly URL から DL + SHA verify pass + payload 展開成功。Task 3 Step 3 と同条件、CI yml 更新後に再実行することで「ローカル + CI 両 path で同 SHA で pass」を verify。

- [ ] **Step 3: pytest (Linux CI side の代替 baseline 確認)**

Run:

```bash
pytest 2>&1 | tail -5
```

Expected: Task 1 Step 5 と同 result。本 plan は Python file を touch しないため不変想定だが、CI yml 経由の linux64 FFmpeg bump で実際に挙動変化がないか verify。

- [ ] **Step 4: markdownlint**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 errors。Task 5 Step 4 を再度実行 (build script + yml + doc 全部 commit 後の最終 check)。

- [ ] **Step 5: ruff / ruff format / pyright (Python path 該当判定)**

本 PR は Python file を touch しないが、CI yml 経由の Python ENV 影響を受ける可能性があるため:

- ruff / ruff format / pyright は **不要** (Iron Law 6 path 別自動チェック判定、Python file 不変)
- ただし Self-Test Report で「Python file 不変、CI 側 python job が PR で実行される」と明記

- [ ] **Step 6: GUI チェック (該当判定)**

本 PR は `gui/**` および `gui/src-tauri/**` に touch しないため:

- npm lint / typecheck / test / build / cargo check は **不要**

---

## Task 7: PR 作成 Pre-flight + PR 作成 (Iron Law 6 再実行)

PR 作成直前の base sync / 並行 PR 重複 final check + PR 作成 + 実機検証依頼。

- [ ] **Step 1: base sync 再 fetch + 取り込み未済 confirm**

Run:

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 空 (Task 1 Step 1 から状況不変想定)。変化があれば `git merge origin/develop-0.2.0` で取り込み、conflict あれば解決後 Task 6 再実行。

- [ ] **Step 2: 並行 worktree PR 再確認 (#704 plan との TES.ps1 衝突含む)**

Run:

```bash
gh pr list --state open --search "705" --json number,title,headRefName
gh pr list --state open --search "BtbN" --json number,title,headRefName
gh pr list --state open --search "build-portable-zip" --json number,title,headRefName
gh pr list --state open --search "Tests.ps1" --json number,title,headRefName
```

Expected: 0 件 (#704 plan の PR が既に open ならそれは予期される、本 PR と Tests.ps1 末尾 append が conflict する可能性のみ確認)。

issue #704 plan の PR が先に merge されていれば Task 1 Step 1 の `git merge origin/develop-0.2.0` で `Tests.ps1` の末尾 append が rebase 吸収される (新 #705 `Describe` block を `#704 Describe` block の後にずらす)。

- [ ] **Step 3: PR 作成**

```bash
gh pr create --base develop-0.2.0 --title "fix(installer): #705 BtbN pin を monthly snapshot に切替 (~24ヶ月 retention)" --body-file - <<'EOF'
## 概要

`scripts/build-portable-zip.ps1` の `$FFmpegBuildTag` を BtbN daily autobuild
(`autobuild-2026-05-06-13-32`、~14 日 retention) から **monthly snapshot**
(`autobuild-2026-04-30-13-44`、~24 ヶ月 retention) に切替え、Portable ZIP build の
URL retention buffer を ~50 倍に拡大する。Pester regression test で monthly pattern
を enforce し daily への rollback を防ぐ。

## empirical 調査結果 (本 spec brainstorming 時、focused-lichterman-5e413f)

issue #705 本文の「BtbN は最新 30 件程度のみ保持」前提は誤りで、実際は:

| 種別 | 保持期間 |
| --- | --- |
| daily | ~14 日 |
| monthly survivor (各月末日 daily) | ~24 ヶ月 |
| 全 release 数 | 37 (2024-06-30〜2026-05-10) |

`checksums.sha256` sidecar も release ごと 1 file 提供 (~5 KB、49 asset 網羅) 確認。
詳細は spec §0 末尾の empirical 調査 summary 参照。

## 受け入れ条件 (元 issue #705 逐条)

- [x] BtbN `.sha256` sidecar 提供有無の WebFetch 調査 — `checksums.sha256` 1 file が release ごと提供 (brainstorming 時 verify 済)
- [x] BtbN autobuild tag retention 実績調査 — daily ~14日 / monthly ~24ヶ月 (brainstorming 時 verify 済)
- [x] 修正方針 (i)-(iv) の採用判断 — (α) monthly pin に確定 (brainstorming 時 AskUserQuestion で承認、spec §2 採用案)
- [x] `scripts/build-portable-zip.ps1` の更新 — line 70-81 を新 monthly 値 + comment block に置換
- [x] `.github/workflows/ci.yml` の整合更新 — line 22 / 29-34 / 40 の 3 箇所更新 (linux64-lgpl-shared 版)
- [x] `.github/workflows/release.yml` の整合更新 — line 99 cache key SHA256 更新 (win64-lgpl-shared 版)
- [x] 再発防止 regression test 追加 — `Describe 'BtbN pinning policy (#705)'` 2 case + Format-ReadmeContent g75d37c499d ref fixture 1 case
- [x] `docs/developer-setup.md` § 9 / `docs/release-process.md` / `docs/quickstart.md` § 10 の整合更新 — 「monthly only / daily 禁止 / checksums.sha256 参照」policy 反映
- [x] `installer-pester` CI が新方式で全 PASS (PR CI で verify)
- [ ] CI `build-windows` job が実 build を完走 (PR CI で verify)

## Self-Test Report

machine-verified:

- [x] `pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/ -PassThru"` → FailedCount 0、TotalCount = baseline + 3 (新 BtbN pinning policy 2 case + Format-ReadmeContent g75d37c499d fixture 1 case)
- [x] `pwsh -NoProfile -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive` → exit 0、新 monthly URL から DL + SHA verify pass + payload 展開成功
- [x] `pytest` → baseline 不変 (Python file 不変)
- [x] `bash scripts/check-markdownlint.sh` → 0 errors
- [x] `python -c 'import yaml; yaml.safe_load(...)'` → ci.yml + release.yml 両方 yaml syntax valid
- [x] `grep e27598e612 scripts/build-portable-zip.ps1 .github/workflows/release.yml` → 2 箇所一致 (drift なし)

該当なし (Iron Law 6 path 別自動チェック判定):

- ruff / ruff format / pyright (Python file 不変)
- npm lint / typecheck / test / build / cargo check (gui/** 不変)

machine-unverifiable (Idios 実機検証必須、Iron Law 6):

- ローカル `pwsh -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive` 実行で payload 完走 (Idios の Windows 11 環境のみ verify 可能、build cache 削除後の実 DL path も含む)
- build した Portable ZIP からサンプル動画分割成功 (FFmpeg ref 変更 `n8.1.1` → `g75d37c499d` の挙動 regression なしを verify、`ALLAGANEYE_SAMPLE_VIDEO_DIR` のサンプル MKV 1 本で `allaganeye split` 実行)

## Iron Law 6 PR Pre-flight 実施済

- [x] `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0` → 取り込み未済 commit なし
- [x] `gh pr list --search "705"` → 並行 worktree PR 重複なし
- [x] `gh api 'repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-04-30-13-44'` → tag 存続確認 (49 assets)、SHA drift なし

## 関連

- 親: #106 (L2b ゼロ環境構築配布)
- spec: docs/superpowers/specs/2026-05-11-l2b-cleanup-design.md §2 (commit 1e372f1)
- plan: docs/superpowers/plans/2026-05-11-l2b-705-btbn-monthly-pin.md
- 並行 plan: docs/superpowers/plans/2026-05-11-l2b-704-pester-bom.md (Lane IV-e #704)
- 先行: PR #703 (#681、Lane IV-a §2 で BtbN URL aging を本 plan に後送りに確定)

Refs #705

session-id: focused-lichterman-5e413f
EOF
```

- [ ] **Step 4: 実機検証依頼 (AskUserQuestion)**

PR 作成後、Idios 実機検証 trigger (Iron Law 6) のため `AskUserQuestion` で:

> 「PR `#<番号>` (#705 BtbN monthly pin) で実機検証をお願いしたい項目: (1) ローカル `pwsh -NoProfile -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive` を実行し、新 monthly URL からの DL + SHA verify + payload 展開成功 + exit 0 を verify。(2) build した payload (`build/portable/allaganeye-v0.2.0-test/`) の `ffmpeg.exe -version` がサンプル MKV 1 本で `allaganeye split` を完走することを verify (FFmpeg ref `n8.1.1` → `g75d37c499d` の挙動 regression check)。実機検証 OK / NG?」

PR 番号は Step 3 の `gh pr create` 出力 URL 末尾から取得。

---

## Task 8: CI watch + review-fix loop

PR push 後、CI 完走 + iterate-review skill による self-review。

- [ ] **Step 1: CI watch**

Run:

```bash
gh pr checks <PR#> --watch
```

Expected: 全 jobs PASS。本 PR の重要 job:

- `python` (linux64 FFmpeg 新 SHA で pytest pass、Iron Law 6 path 別自動チェック該当)
- `installer-pester` (新 Pester regression 3 case + 既存 case 全 pass、Iron Law 6 path 別自動チェック該当)
- `build-windows` (実 Portable ZIP build を新 win64 SHA で完走、release.yml cache key invalidate 確認、acceptance criteria 最終 1 項目)
- `markdownlint` (3 doc 編集 lint pass)

失敗があれば `gh run view <run-id> --log-failed` で確認し fix。

- [ ] **Step 2: /iterate-review 起動**

CI green 後、`/iterate-review <PR#>` を user 起動 (推奨) または agent 起動。subagent dispatch で `/review-pr` を実行し findings を構造化 return → 主セッションが (A) PR 内修正 / (B)(C) handoff / push / CI wait を Round 5 / 発散検知まで繰り返す。

- [ ] **Step 3: 摘出課題の triage + (A) PR 内修正完結**

`/iterate-review` の findings を spec §3 (A) PR 内修正優先 規約に従い triage。

- [ ] **Step 4: 受け入れ条件 LGTM 候補化**

Round 5b 表が全ゼロ + acceptance criteria 全 satisfies (特に「CI `build-windows` job が実 build を完走」の最後の checkbox) → LGTM 候補。Idios の最終承認後 merge。

---

## Task 9: マージ後 close handoff

merge 後、`/close-issue` skill にハンドオフ (本 PR scope では `gh issue close` を実行しない、Iron Law 4)。

- [ ] **Step 1: マージ後の base 同期**

Run:

```bash
git checkout develop-0.2.0
git pull origin develop-0.2.0
```

- [ ] **Step 2: `/close-issue` skill invoke**

Run skill: `/close-issue 705`

skill が:

- マージ後 develop-0.2.0 で受け入れ条件を実測再検証 (`gh api` で BtbN tag confirm + `pwsh -File scripts/build-portable-zip.ps1` build dry-run で実 retention 1 回 verify)
- 未消化 checkbox / 残タスクをトリアージ ((B) 新 issue / (C) 既存 issue 追記)
- Idios 承認後 `gh issue close 705`

- [ ] **Step 3: Idios 実機検証残項目の close**

Idios 実機検証 (build dry-run + サンプル動画分割) を完了し OK 報告 → close-issue skill が close を実行。

---

## Self-Review (writing-plans skill 必須項目)

**1. Spec coverage:** spec §2 受け入れ条件 10 項を全て tasks でカバー:

| spec 受け入れ条件 (#705) | 対応 task |
| --- | --- |
| `.sha256` sidecar 調査 | brainstorming 時 verify 済 (spec §0)、Task 1 Step 4 で final verify |
| BtbN retention 実績調査 | brainstorming 時 verify 済 (spec §0 末尾 table)、Task 1 Step 3 で final verify |
| (i)-(iv) 採用判断 | brainstorming で (α) monthly pin に確定 (spec §2 採用案) |
| build-portable-zip.ps1 更新 | Task 3 |
| ci.yml 整合 | Task 4 Step 1-3 |
| release.yml 整合 | Task 4 Step 4 |
| 再発防止 regression test | Task 2 (3 case 追加) |
| developer-setup.md / release-process.md doc | Task 5 |
| installer-pester PASS | Task 6 Step 1 + Task 8 Step 1 |
| build-windows job 完走 | Task 6 Step 2 (ローカル) + Task 8 Step 1 (CI) |

**2. Placeholder scan:** plan 内に "TBD" / "TODO" / "later" / "appropriate handling" なし。SHA256 / tag / asset 名は brainstorming + Task 1 Step 4 empirical で固定値、yml line 番号は empirical 確認済。

**3. Type / signature consistency:** 変数名 `$FFmpegBuildTag` / `$FFmpegAsset` / `$FFmpegSha256` は build-portable-zip.ps1 (Task 3) と Tests.ps1 (Task 2) と CI yml (Task 4) で完全一致。SHA256 値 `e27598e612...` は build-portable-zip.ps1 (Task 3 Step 1) と release.yml (Task 4 Step 4) と PR 本文 grep 確認 (Task 7 Step 3 Self-Test Report) で 3 箇所一致。SHA256 値 `b31223cb80...` は ci.yml (Task 4 Step 1 + Step 3) で 2 箇所一致。

**4. spec §4 開放問題 解消状況:**

| spec §4 開放問題 (#705) | 解消位置 |
| --- | --- |
| 新 `$FFmpegSha256` (win64) と ci.yml 用 linux64 SHA256 の正確な値 | empirical 取得済: win64 = `e27598e612...`、linux64 = `b31223cb80...` (本 plan 全 task で固定値使用) |
| `Format-ReadmeContent` test 拡張手順 | Task 2 Step 2 (既存 test を保持しつつ #705 specific fixture を 1 case append) |
| `docs/quickstart.md` § 10 の ref 文字列 hardcode 確認 | empirical 確認済 (line 151 hardcoded `n8.1.1`)、Task 5 Step 1 で更新 |
| BtbN bump 手順 doc の文言案 | Task 5 Step 2 (developer-setup.md § 9) + Task 5 Step 3 (release-process.md) で具体文言確定 |
| 実機検証 trigger | Task 7 Step 4 (`AskUserQuestion` で Idios 依頼、PR 作成後実施) |
| writing-plans 着手時の final verify | Task 1 Step 3 + Step 4 (`gh api` + `curl checksums.sha256` で再 verify) |

全項目解消済、writing-plans 持ち越しなし。

---

## 関連 doc / Iron Law

- spec: [docs/superpowers/specs/2026-05-11-l2b-cleanup-design.md](../specs/2026-05-11-l2b-cleanup-design.md) §2 (commit `1e372f1`)
- 並行 plan: [docs/superpowers/plans/2026-05-11-l2b-704-pester-bom.md](2026-05-11-l2b-704-pester-bom.md) (#704)
- 先行 spec: [docs/superpowers/specs/2026-05-08-l2b-distribution-design.md](../specs/2026-05-08-l2b-distribution-design.md) §2 (#681、Lane IV-a §2 で BtbN URL aging を本 plan に後送りに確定)
- Iron Law: `.claude/hooks/session-start.sh` (5 条 + Red Flags)
- l2-workflow: `docs/l2-workflow.md` (Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger)

## 関連 issue

- 親: [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) (L2b ゼロ環境構築配布)
- 本 plan: [#705](https://github.com/Idios/kobutachan-allaganeye/issues/705)
- 先行 PR: [#703](https://github.com/Idios/kobutachan-allaganeye/pull/703) ([#681](https://github.com/Idios/kobutachan-allaganeye/issues/681)、Lane IV-a §2 で BtbN URL aging を本 plan に後送りに確定)
