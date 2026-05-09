# Lane IV-a §3 #617: `allaganeye.bat` ダブルクリックで GUI 起動 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portable ZIP 同梱の `allaganeye.bat` を引数なしダブルクリック時に `allaganeye-gui.exe` を起動するよう挙動変更する。`--help` / `-h` / `/?` で従来のヘルプ表示、CLI 用法 (動画ドラッグ・サブコマンド指定) は完全保持。CLI-only ZIP (GUI exe 未同梱) ではヘルプ fallback。

**Architecture:** `Get-LauncherTemplate` を **label-based dispatch** で 5 branch (上から順、最初にマッチを実行) に再構成: (1) `--help`/`-h`/`/?` → `:show_help` (2) 引数なし + GUI exe 存在 → `start "" "%PAYLOAD%allaganeye-gui.exe"` + `exit /b 0` (3) 引数なし + GUI exe 不在 → `:show_help` fallback (4) 動画拡張子 → `python -m allaganeye split %*` (既存) (5) その他引数 → `python -m allaganeye %*` (既存)。`-IncludeGui` switch を新設し、`Format-ReadmeContent` と対称化、help 文言と README 文言を build 時に切替。build script main path を Tauri detection → launcher の順に reorder して `-IncludeGui:$TauriIncluded` を注入する。

**Tech Stack:**

- PowerShell (`scripts/build-portable-zip.ps1` の `Get-LauncherTemplate` / `Format-ReadmeContent` / main 実行 path)
- Pester v5 (`scripts/tests/build-portable-zip.Tests.ps1`)
- Windows cmd.exe `.bat` syntax (`setlocal` / `if /i` / `goto :label` / `start ""` / `endlocal & exit /b`)
- 既存 path idiom: `%PAYLOAD%` (line 258 で `%~dp0` から captured)
- 既存 case-insensitive 拡張子判定 idiom: `if /i "%EXT%"==".mp4"` 4 行集約 → `if defined IS_VIDEO`

---

## Task 1: scope 確認 (CLAUDE.md line 31 の扱い)

**Files:** なし (AskUserQuestion 操作のみ)

CLAUDE.md line 31 に `> **配布物の起動経路**: Portable ZIP の \`allaganeye.bat\` = CLI 起動 / Tauri bundle の \`allaganeye-gui.exe\` (v0.2.0+) = GUI 起動。` と記載があり、本 PR で `.bat` 引数なし時の挙動が「CLI 起動」から「GUI 起動」に変わるため記述が不正確になる。issue #617 の 作業内容 / 受け入れ条件には CLAUDE.md / docs/system-architecture.md 更新が含まれていない (spec §3 §影響範囲も同様)。Iron Law 3 (NO SCOPE CREEP WITHOUT NEW ISSUE) に従い、scope 拡張判断をユーザーに確認する。

- [ ] **Step 1: AskUserQuestion で scope 拡張判断を確認**

```text
質問: CLAUDE.md line 31 の「Portable ZIP の `allaganeye.bat` = CLI 起動」記述は本 PR の change で不正確になる。どう扱うか?
ヘッダ: CLAUDE.md 更新

選択肢:
- (a) 別 issue に分離 (Recommended)
  本 PR scope を spec §3 / issue #617 受け入れ条件のみに限定 (Iron Law 3 厳守)。
  CLAUDE.md / docs/system-architecture.md (#527 dispatch 表) の文言更新は follow-up issue として
  起票し、別 PR で扱う (本 PR merge 後の `/close-issue` ハンドオフ時に triage)。
- (b) 本 PR で CLAUDE.md line 31 + docs/system-architecture.md (該当箇所) も同時更新
  doc drift を直接解消するが scope 拡張 1 章。Iron Law 3 例外的拡張で merge 後の
  doc 整合性を担保。
- (c) 本 PR で CLAUDE.md line 31 のみ更新 (system-architecture.md は触らない)
  最小限の doc 整合性確保。CLAUDE.md は強制 reload される source of truth のため。
```

**選択結果に応じた以降の Task 分岐**:

- (a) を選んだ場合 → 以降は CLAUDE.md / system-architecture.md を touch しない。Task 12 (PR 作成後) で follow-up issue 起票 step を追加実行
- (b) を選んだ場合 → Task 11 (新規) で CLAUDE.md + system-architecture.md を更新するサブタスクを追加
- (c) を選んだ場合 → Task 11 (新規) で CLAUDE.md のみ更新するサブタスクを追加

> 以降の Task 番号は (a) 採用時のものを記載。(b)/(c) 採用時は Task 11 以降を該当 step に置き換え。

---

## Task 2: Iron Law 6 PR Pre-flight check

**Files:** なし (git / gh CLI 操作のみ)

- [ ] **Step 1: Fetch latest develop-0.2.0 base + 取り込み未済 commit 確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 取り込み未済 commit list (空 or 数件)。`scripts/build-portable-zip.ps1` を touch する commit があれば Step 3 で merge。Lane IV-a §2 #681 が先に merge された場合、特に line 49-75 (上部 hash pin) を変更している可能性があるため重点確認。

- [ ] **Step 2: 並行 worktree PR の重複確認 (Iron Law 6)**

```bash
gh pr list --search "#617" --state all
gh pr list --state open --base develop-0.2.0 --json number,title,headRefName,files
```

Expected: 既存 PR が #617 を扱っていない、`scripts/build-portable-zip.ps1` を touch する他 PR (特に #681 の §2 PR) がない。重複あれば作業中止して Idios に AskUserQuestion で確認。

- [ ] **Step 3: 取り込み未済 commit が build-portable-zip.ps1 を touch していれば merge**

```bash
git log HEAD..origin/develop-0.2.0 --name-only | grep -E 'scripts/(build-portable-zip\.ps1|tests/build-portable-zip\.Tests\.ps1)' || echo "no conflict in build-portable-zip"
git merge origin/develop-0.2.0
```

Expected: conflict なし。`build-portable-zip.ps1` line 49-75 (§2 #681 の領域) と line 246-297 (§3 #617 の領域) は line 範囲独立だが、line 158-244 の `Format-ReadmeContent` も §2 / §3 で touch する可能性があるため verify。conflict あれば手動解決。

---

## Task 3: Pester tests を追加 (TDD red phase)

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (line 220 直前、`Describe 'Get-LauncherTemplate'` block 内 + 新 `Describe` block 追加)

`#580` EXIT_CODE regression test (line 211-219) は既に存在し pass し続ける前提。新 test を追加する。

- [ ] **Step 1: `Describe 'Get-LauncherTemplate'` block に It 追加 (#617 新挙動 + regression)**

`scripts/tests/build-portable-zip.Tests.ps1` の line 210-220 の `Describe 'Get-LauncherTemplate'` block を以下の 8 個の `It` を含む形に書き換え (既存 #580 test を残しつつ新 test を追加):

```powershell
Describe 'Get-LauncherTemplate' {
  It 'preserves python exit code via EXIT_CODE save and endlocal & exit /b idiom (#580)' {
    # Launcher must propagate python exit code so callers can chain
    # `allaganeye.bat detect file.mp4 && next-step` and CI smoke (Level B in
    # release.yml) can observe non-zero exit codes. CI smoke is the de-facto
    # regression test; this unit test is the unit-level safety net (#583).
    $template = Get-LauncherTemplate
    $template | Should -Match 'set EXIT_CODE=%ERRORLEVEL%'
    $template | Should -Match 'endlocal & exit /b %EXIT_CODE%'
  }

  It 'no-args branch launches GUI via start when allaganeye-gui.exe exists (#617)' {
    # When user double-clicks .bat without args and the GUI exe is bundled,
    # template must launch the GUI asynchronously (start "") so the cmd
    # window does not linger, then exit with code 0.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if exist "%PAYLOAD%allaganeye-gui\.exe"'
    $template | Should -Match 'start "" "%PAYLOAD%allaganeye-gui\.exe"'
  }

  It 'no-args + GUI absent falls back to :show_help label (#617)' {
    # CLI-only ZIP fallback: if allaganeye-gui.exe is not bundled,
    # double-click should still display the help text + pause (preserves
    # the pre-#617 UX for that case).
    $template = Get-LauncherTemplate
    $template | Should -Match 'goto :show_help'
    $template | Should -Match '(?m)^:show_help\s*$'
  }

  It 'recognizes --help, -h, and /? as explicit help flags (#617)' {
    # Explicit help flags must reach :show_help even when GUI exe is bundled,
    # otherwise `allaganeye.bat --help` would silently launch the GUI.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if /i "%~1"=="--help"'
    $template | Should -Match 'if /i "%~1"=="-h"'
    $template | Should -Match 'if "%~1"=="/\?"'
  }

  It 'preserves case-insensitive video drag-drop dispatch (regression)' {
    # The video drag-drop branch (existing pre-#617 behavior) must remain.
    # All four video extensions are case-insensitive (if /i) and the script
    # invokes `python -m allaganeye split %*` to preserve full arg pass-through.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if /i "%EXT%"==".mp4"'
    $template | Should -Match 'if /i "%EXT%"==".mkv"'
    $template | Should -Match 'if /i "%EXT%"==".avi"'
    $template | Should -Match 'if /i "%EXT%"==".mov"'
    $template | Should -Match '"%PAYLOAD%python\\python\.exe" -m allaganeye split %\*'
  }

  It 'preserves CLI passthrough for non-video args (regression)' {
    # Non-video args (e.g. allaganeye.bat detect <file>, --version) must
    # still be dispatched to `python -m allaganeye %*`.
    $template = Get-LauncherTemplate
    $template | Should -Match '"%PAYLOAD%python\\python\.exe" -m allaganeye %\*'
  }

  It '-IncludeGui:$true emits help text mentioning .bat double-click as the first option (#617)' {
    # When GUI exe is bundled, help text must mention .bat double-click as
    # the easiest entry. The literal "Double-click" + "allaganeye.bat" is
    # the canonical phrase users will read in `allaganeye.bat --help`.
    $template = Get-LauncherTemplate -IncludeGui:$true
    $template | Should -Match 'Double-click allaganeye\.bat'
  }

  It '-IncludeGui:$false (default) omits Double-click GUI mention from help text (#617)' {
    # CLI-only ZIP: help text MUST NOT advertise GUI double-click since the
    # GUI exe is not bundled. The runtime `if exist` check still appears in
    # the template as a defensive fallback, but the help text must be free
    # of the user-facing "Double-click" advertisement.
    $template = Get-LauncherTemplate
    $template | Should -Not -Match 'Double-click allaganeye\.bat'
  }
}
```

実行:

```text
Edit tool で:
  file_path: scripts/tests/build-portable-zip.Tests.ps1
  old_string:
Describe 'Get-LauncherTemplate' {
  It 'preserves python exit code via EXIT_CODE save and endlocal & exit /b idiom (#580)' {
    # Launcher must propagate python exit code so callers can chain
    # `allaganeye.bat detect file.mp4 && next-step` and CI smoke (Level B in
    # release.yml) can observe non-zero exit codes. CI smoke is the de-facto
    # regression test; this unit test is the unit-level safety net (#583).
    $template = Get-LauncherTemplate
    $template | Should -Match 'set EXIT_CODE=%ERRORLEVEL%'
    $template | Should -Match 'endlocal & exit /b %EXIT_CODE%'
  }
}
  new_string: <上記 8 It 含むブロック全体>
```

- [ ] **Step 2: 既存 `Describe 'Format-ReadmeContent'` block に It 追加 (#617 新 README 挙動)**

`Describe 'Format-ReadmeContent'` block (line 133-208) の末尾、line 207 の `}` (block 閉じ) 直前に新 It を追加:

```powershell
  It '-IncludeGui:$true README documents .bat double-click as the primary GUI entry (#617)' {
    # README must explain that `.bat` double-click launches the GUI when
    # GUI exe is bundled. The phrase "Double-click" + "allaganeye.bat" must
    # appear together so the new UX (issue #617) is documented for users
    # who read README.txt before running anything.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1' `
      -IncludeGui:$true
    $readme | Should -Match 'Double-click `?allaganeye\.bat`?'
  }

  It '-IncludeGui:$true README orders GUI section before drag-drop and Command Prompt sections (#617)' {
    # Per spec §3 + issue #617 doc requirement: ".bat double-click → GUI"
    # comes first, drag-drop and Command Prompt are 2-3.
    # We assert relative ordering by comparing IndexOf positions.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1' `
      -IncludeGui:$true
    $idxBatDoubleClick = $readme.IndexOf('Double-click')
    $idxDragDrop = $readme.IndexOf('Drop a video file')
    $idxCommandPrompt = $readme.IndexOf('Command Prompt')

    $idxBatDoubleClick | Should -BeGreaterThan -1
    $idxDragDrop | Should -BeGreaterThan -1
    $idxCommandPrompt | Should -BeGreaterThan -1
    $idxBatDoubleClick | Should -BeLessThan $idxDragDrop
    $idxDragDrop | Should -BeLessThan $idxCommandPrompt
  }
```

実行:

```text
Edit tool で:
  file_path: scripts/tests/build-portable-zip.Tests.ps1
  old_string:
  It 'embeds release tag as source ref for new BtbN naming format (#683)' {
    # 新 BtbN naming (n8.1.1) では Get-FFmpegSourceRef が release tag を返し、
    # README には (ref n8.1.1) で記述される。`(commit ...)` の旧文言が残らない
    # ことも併せて verify (PR #683 review #10)。
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1'
    $readme | Should -Match '\(ref n8\.1\.1\)'
    $readme | Should -Not -Match '\(commit n8\.1\.1\)'
  }
}
  new_string:
  It 'embeds release tag as source ref for new BtbN naming format (#683)' {
    ... <既存 body 維持>
  }

  It '-IncludeGui:$true README documents .bat double-click as the primary GUI entry (#617)' {
    ... <上記新 It>
  }

  It '-IncludeGui:$true README orders GUI section before drag-drop and Command Prompt sections (#617)' {
    ... <上記新 It>
  }
}
```

- [ ] **Step 3: Pester suite を実行して red 状態を verify**

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed"
```

Expected:

- 既存 test (Invoke-Download / Assert-FFmpegLayout / Get-FFmpegSourceRef / Format-ReadmeContent 既存 4 個 + Get-LauncherTemplate #580 + Script parameters) は **PASS**
- 新 test (Get-LauncherTemplate 7 個 + Format-ReadmeContent 2 個 = 計 9 個) は **FAIL**:
  - "no-args branch launches GUI" → FAIL (`if exist "%PAYLOAD%allaganeye-gui.exe"` が無い)
  - "no-args + GUI absent fallback" → FAIL (`goto :show_help` が無い)
  - "recognizes --help, -h, and /?" → FAIL (3 dispatch line 無い)
  - "case-insensitive video drag-drop" → PASS (既存 idiom そのまま、regression として既に green)
  - "CLI passthrough for non-video" → PASS (既存 idiom そのまま、regression として既に green)
  - "-IncludeGui:$true help text" → FAIL (`-IncludeGui` param 自体が存在しない、PowerShell が parameter mismatch エラー)
  - "-IncludeGui:$false help text" → FAIL (`Double-click allaganeye.bat` が `:$false` 時に absent であることの assertion、現状は help text にそもそも存在しない為 PASS する可能性あり、impl 後改めて verify)
  - "README documents .bat double-click" → FAIL (現状 README に "Double-click `allaganeye.bat`" が無い)
  - "README orders GUI section first" → FAIL (現状 GUI section は最後、drag-drop/Command Prompt の後)

red 状態を確認したら commit 候補だが、TDD red phase commit は本 plan では skip し、緑化と同 commit にまとめる。

- [ ] **Step 4: red phase 結果を Self-Test Report 用にメモ**

実行ログから FAIL/PASS の各 test 名を temp file に記録:

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed" 2>&1 | tee /tmp/pester-617-red.log
grep -E "^\s*(\[\+\]|\[\-\]|Failed|Passed|It |Describing)" /tmp/pester-617-red.log | head -50
```

Expected: 9 失敗 (新 test) + 既存 ≥10 件 PASS の表示。

---

## Task 4: `Get-LauncherTemplate` を `-IncludeGui` switch + 新 dispatch で書き換え (TDD green phase)

**Files:**

- Modify: `scripts/build-portable-zip.ps1` line 246-297 (`Get-LauncherTemplate` 全体)

- [ ] **Step 1: 関数 signature と template body を書き換え**

`scripts/build-portable-zip.ps1:246-297` を以下の内容で置換:

```powershell
function Get-LauncherTemplate {
  <#
  .SYNOPSIS
  Returns the .bat launcher template embedded in the Portable ZIP.

  Exposed as a function so Pester (#583) can verify the exit code propagation
  idiom (#580: `set EXIT_CODE=%ERRORLEVEL%` + `endlocal & exit /b %EXIT_CODE%`)
  without dot-sourcing the full build path.

  -IncludeGui:$true (when allaganeye-gui.exe is bundled in the ZIP) emits help
  text that mentions ".bat double-click → GUI" as the primary entry. -IncludeGui:$false
  (default, CLI-only ZIP) omits the GUI mention so users are not directed to a
  non-existent exe. Symmetric with Format-ReadmeContent -IncludeGui (#570).

  Branch order in the template (top-down, first match wins, #617):
    1. --help / -h / /?               → :show_help (explicit help flags always reach help)
    2. no args + GUI exe exists       → start "" "%PAYLOAD%allaganeye-gui.exe" + exit /b 0
    3. no args + GUI exe absent       → :show_help (CLI-only ZIP fallback)
    4. video file extension           → python -m allaganeye split %*  (existing pre-#617 behavior)
    5. other args                     → python -m allaganeye %*        (existing pre-#617 behavior)

  The runtime `if exist "%PAYLOAD%allaganeye-gui.exe"` check is a defensive
  fallback that handles the (rare) case where a user manually deletes the GUI
  exe from a -IncludeGui:$true ZIP. -IncludeGui only controls the help text.
  #>
  param(
    [switch]$IncludeGui
  )

  $helpUsageLines = if ($IncludeGui) {
@'
echo   1. Double-click allaganeye.bat to launch the GUI (allaganeye-gui.exe).
echo   2. Drag a video file (.mkv / .mp4 / .avi / .mov) onto allaganeye.bat
echo      to split it automatically.
echo   3. From a Command Prompt:
echo      allaganeye.bat split "C:\path\to\video.mkv"
'@
  }
  else {
@'
echo   1. Drag a video file (.mkv / .mp4 / .avi / .mov) onto allaganeye.bat
echo      to split it automatically.
echo   2. From a Command Prompt:
echo      allaganeye.bat split "C:\path\to\video.mkv"
'@
  }

  return @"
@echo off
setlocal
set PAYLOAD=%~dp0
set ALLAGANEYE_FFMPEG=%PAYLOAD%ffmpeg\ffmpeg.exe
set PATH=%PAYLOAD%ffmpeg;%PATH%

if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
if "%~1"=="/?" goto :show_help

if "%~1"=="" (
  if exist "%PAYLOAD%allaganeye-gui.exe" (
    start "" "%PAYLOAD%allaganeye-gui.exe"
    endlocal
    exit /b 0
  )
  goto :show_help
)

set EXT=%~x1
set IS_VIDEO=
if /i "%EXT%"==".mp4" set IS_VIDEO=1
if /i "%EXT%"==".mkv" set IS_VIDEO=1
if /i "%EXT%"==".avi" set IS_VIDEO=1
if /i "%EXT%"==".mov" set IS_VIDEO=1

if defined IS_VIDEO (
  "%PAYLOAD%python\python.exe" -m allaganeye split %*
) else (
  "%PAYLOAD%python\python.exe" -m allaganeye %*
)
set EXIT_CODE=%ERRORLEVEL%

echo.
pause
endlocal & exit /b %EXIT_CODE%

:show_help
echo.
echo allaganeye - FF14 Frontline video splitter
echo.
echo How to use:
$helpUsageLines
echo.
echo Docs: https://github.com/Idios/kobutachan-allaganeye
echo.
pause
endlocal
exit /b 0
"@
}
```

> **重要 (cmd.exe parser quirk)**: help text 内の `(...)` (例: `(.mkv / .mp4 / ...)` や `(allaganeye-gui.exe)`) はもはや `if (...)` 内ではなく `:show_help` label 配下に置かれるため、`^(` `^)` の escape は不要 (cmd.exe parser は parenthesized block 外では `(` `)` を literal として扱う)。これは旧 template (line 267) の `^(.mkv ...^)` から escape を外す変更だが、help text の table 表記は同等で出力結果は変わらない。

実行:

```text
Edit tool で:
  file_path: scripts/build-portable-zip.ps1
  old_string: <line 246-297 全体、function Get-LauncherTemplate { ... }>
  new_string: <上記新 body>
```

- [ ] **Step 2: Pester で green 状態を verify**

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed"
```

Expected: **全 test PASS**:

- 既存 test (Invoke-Download / Assert-FFmpegLayout / Get-FFmpegSourceRef / Format-ReadmeContent 4 個 / #580 EXIT_CODE / Script parameters) — PASS (regression)
- 新 Get-LauncherTemplate 7 test — PASS
- 新 Format-ReadmeContent 2 test — Task 5 で実装するため **まだ FAIL** (この時点では Format-ReadmeContent 未変更)

つまり Task 4 完了時点では Get-LauncherTemplate test 全 PASS、Format-ReadmeContent 新 test 2 個 FAIL のまま。Task 5 完了で全 PASS。

- [ ] **Step 3: 失敗 test が想定通り Format-ReadmeContent 2 個に絞られていることを verify**

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed" 2>&1 | grep -E "^\s*\[\-\]" | head -10
```

Expected:

```text
  [-] -IncludeGui:$true README documents .bat double-click as the primary GUI entry (#617)
  [-] -IncludeGui:$true README orders GUI section before drag-drop and Command Prompt sections (#617)
```

Get-LauncherTemplate 関連の `[-]` (FAIL) が 0 件であること。

---

## Task 5: `Format-ReadmeContent` を新 section ordering で書き換え

**Files:**

- Modify: `scripts/build-portable-zip.ps1` line 158-244 (`Format-ReadmeContent` 全体)

- [ ] **Step 1: 関数 body を書き換え (GUI section を冒頭へ移動 + 文言更新)**

`scripts/build-portable-zip.ps1:158-244` を以下の内容で置換:

```powershell
function Format-ReadmeContent {
  <#
  Produce the README.txt shipped inside the Portable ZIP. Exposing this as a
  function lets Pester assert the LGPLv3 attribution + source pointers are
  present without running a full build.

  -IncludeGui:$true (when the Tauri-built `allaganeye-gui.exe` is bundled, #570)
  emits a "Easiest: double-click `allaganeye.bat`" section as the FIRST usage
  entry, followed by drag-drop and Command Prompt sections (#617). The WebView2
  Runtime dependency note moves into this section. -IncludeGui:$false (default,
  CLI-only ZIP) keeps drag-drop as the first usage entry without any GUI
  references.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$FFmpegVersion,
    [Parameter(Mandatory = $true)][string]$FFmpegBuildTag,
    [Parameter(Mandatory = $true)][string]$FFmpegSourceRef,
    [switch]$IncludeGui
  )
  $guiSection = if ($IncludeGui) {
@'

### Easiest: double-click ``allaganeye.bat``

Double-click ``allaganeye.bat`` in this folder to launch the GUI
(``allaganeye-gui.exe``). The GUI lets you drop a video file, review detected
matches, fine-tune match boundaries, and export each match as MP4.

NOTE: The GUI requires Microsoft Edge WebView2 Runtime, which is preinstalled
on Windows 11 and recent Windows 10 builds. If the GUI fails to start with a
missing-runtime dialog, install it from:

    https://developer.microsoft.com/en-us/microsoft-edge/webview2/

(``Evergreen Standalone Installer`` is sufficient and does not require admin
rights for per-user install.)

'@
  }
  else { '' }

  $guiLicenseLine = if ($IncludeGui) {
@"
- Allagan Eye GUI (``allaganeye-gui.exe``): MIT (built with Tauri 2.x + React 19)
    WebView2 Runtime is loaded from the user's system at runtime, not redistributed.

"@
  }
  else { '' }

  return @"
# allaganeye v$Version (Portable ZIP for Windows)

Python 3.11 and FFmpeg LGPL binaries are bundled alongside allaganeye.

## Usage
$guiSection
### Drag-and-drop a video file

Drop a video file (.mkv / .mp4 / .avi / .mov) onto ``allaganeye.bat`` and it
will split the video automatically. The command window stays open at the end so
you can read the result -- press any key to close it.

Output MP4 files and metadata.json land under ``output\`` inside this folder.

### From a Command Prompt

If you want to pass options such as --dry-run or -o, open a Command Prompt in
this folder and run:

    allaganeye.bat split "C:\path\to\video.mkv"
    allaganeye.bat split "C:\path\to\video.mkv" --dry-run
    allaganeye.bat --version

See https://github.com/Idios/kobutachan-allaganeye for full documentation.

## Licenses

- allaganeye: MIT (see the repository LICENSE file)
$guiLicenseLine- Python: PSF License (python\LICENSE.txt)
- FFmpeg: LGPLv3 (full text in ffmpeg\LICENSE.txt)
    Build:         ffmpeg n$FFmpegVersion win64-lgpl-shared build (BtbN/FFmpeg-Builds)
    Build tag:     $FFmpegBuildTag
    Source:        https://git.ffmpeg.org/ffmpeg.git (ref $FFmpegSourceRef)
    Build scripts: https://github.com/BtbN/FFmpeg-Builds

allaganeye (MIT) invokes the FFmpeg binary as a separate subprocess only.
The shared-build DLLs are loaded dynamically by the FFmpeg executables and are
redistributed under LGPLv3 alongside the license text; LGPLv3 therefore does
not apply to allaganeye itself.
"@
}
```

主な変更点:

1. GUI section "Easiest: double-click `allaganeye.bat`" を `## Usage` 直後 (drag-drop の前) に配置
2. GUI section header を "GUI: double-click `allaganeye-gui.exe`" から "Easiest: double-click `allaganeye.bat`" に変更
3. GUI section 文言を ".bat → GUI" 文脈に更新 (旧 ".exe を直接 double-click" の文言は merge 削除)
4. 旧 `### Basic: drag-and-drop` を `### Drag-and-drop a video file` に rename
5. 旧 `### Advanced: from a Command Prompt` を `### From a Command Prompt` に rename
6. `$guiSection` の挿入位置を `## Usage` 行の直下に変更 (旧: `### Advanced` の後)
7. `### From a Command Prompt` 内の例示行 (`allaganeye.bat split ... --dry-run` / `--version`) は preserve

実行:

```text
Edit tool で:
  file_path: scripts/build-portable-zip.ps1
  old_string: <line 158-244 全体、function Format-ReadmeContent { ... }>
  new_string: <上記新 body>
```

- [ ] **Step 2: Pester で green 状態を verify**

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed"
```

Expected: **全 test PASS** (Format-ReadmeContent 既存 4 + 新 2、Get-LauncherTemplate 既存 1 + 新 7、その他 regression)。failure 0 件。

- [ ] **Step 3: 既存 README test 4 個が依然 PASS することを明示的に verify**

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -FullNameFilter '*Format-ReadmeContent*' -Output Detailed" 2>&1 | tee /tmp/pester-readme.log
grep -E "^\s*\[\+\]" /tmp/pester-readme.log
```

Expected: 6 個の `[+]` (PASS):

```text
  [+] includes the LGPLv3 BtbN win64-lgpl-shared attribution and the source commit
  [+] -IncludeGui:$true emits the GUI launch section and WebView2 runtime notice (#570)
  [+] -IncludeGui:$true emits the Tauri 2 / React 19 license entry (#570)
  [+] -IncludeGui:$false (default) omits the GUI section for CLI-only ZIPs (#570)
  [+] embeds release tag as source ref for new BtbN naming format (#683)
  [+] -IncludeGui:$true README documents .bat double-click as the primary GUI entry (#617)
  [+] -IncludeGui:$true README orders GUI section before drag-drop and Command Prompt sections (#617)
```

特に `-IncludeGui:$true emits the GUI launch section and WebView2 runtime notice (#570)` (line 153-167) の `Should -Match 'double-click'` / `Should -Match 'WebView2 Runtime'` / `Should -Match 'developer\.microsoft\.com'` が新文言でも PASS することを verify。

---

## Task 6: build script main path を Tauri detection → launcher 順に reorder

**Files:**

- Modify: `scripts/build-portable-zip.ps1` line 391-427 (Step 5 launcher / Step 6 Tauri / Step 7 README の 3 block を reorder + `-IncludeGui:$TauriIncluded` 注入)

- [ ] **Step 1: Step 5 と Step 6 を入れ替えて launcher が `-IncludeGui:$TauriIncluded` を受けるよう修正**

現状 (line 391-427):

```powershell
# 5. Launcher
# Template is defined as Get-LauncherTemplate (#583) so Pester can verify the
# exit code propagation idiom (#580) without dot-sourcing the full build path.
$Launcher = Get-LauncherTemplate
Set-Content -Path (Join-Path $PayloadDir 'allaganeye.bat') -Value $Launcher -Encoding ASCII

# 6. Tauri GUI bundle (optional, auto-detect)
# (long comment block)
$TauriExe = Join-Path $RepoRoot 'gui\src-tauri\target\release\allaganeye-gui.exe'
$TauriIncluded = $false
if (Test-Path $TauriExe) {
  Copy-Item -Path $TauriExe -Destination (Join-Path $PayloadDir 'allaganeye-gui.exe')
  Write-Host "Bundled GUI: $TauriExe -> $PayloadDir\allaganeye-gui.exe"
  $TauriIncluded = $true
} else {
  Write-Warning "Tauri GUI build not found at $TauriExe - Portable ZIP will be built without the GUI binary. Run 'cd gui && npm install && npm run tauri build' first to include the GUI."
}

# 7. README (after Tauri detection so the GUI section is conditional)
$Readme = Format-ReadmeContent `
  -Version $Version `
  -FFmpegVersion $FFmpegVersion `
  -FFmpegBuildTag $FFmpegBuildTag `
  -FFmpegSourceRef $FFmpegSourceRef `
  -IncludeGui:$TauriIncluded
Set-Content -Path (Join-Path $PayloadDir 'README.txt') -Value $Readme -Encoding UTF8
```

新 (Tauri を 5 番、launcher を 6 番、README を 7 番):

```powershell
# 5. Tauri GUI bundle (optional, auto-detect)
# Copy the Tauri-built GUI binary (allaganeye-gui.exe) into the payload root
# as-is. The cargo binary name has no whitespace so users / scripts can
# reference it without quoting headaches; tauri.conf.json `productName`
# ("Allagan Eye") is still used by Tauri for the window title at runtime,
# but the executable filename stays in cargo/snake/dash form for portability.
#
# Build is the caller's responsibility: CI runs `npm install && npm run tauri build`
# in a preceding workflow step, and the resulting exe lands at
# gui/src-tauri/target/release/allaganeye-gui.exe. tauri.conf.json keeps
# `bundle.active = false` because the Portable ZIP is the distribution form
# and Tauri's NSIS/MSI bundles are not used. Local dry-run may skip the
# Tauri build; if the exe is absent we log a warning and continue (CLI-only ZIP).
#
# This block runs BEFORE the launcher (step 6, #617) so $TauriIncluded is
# available to Get-LauncherTemplate -IncludeGui and the .bat help text reflects
# whether the GUI is bundled.
$TauriExe = Join-Path $RepoRoot 'gui\src-tauri\target\release\allaganeye-gui.exe'
$TauriIncluded = $false
if (Test-Path $TauriExe) {
  Copy-Item -Path $TauriExe -Destination (Join-Path $PayloadDir 'allaganeye-gui.exe')
  Write-Host "Bundled GUI: $TauriExe -> $PayloadDir\allaganeye-gui.exe"
  $TauriIncluded = $true
} else {
  Write-Warning "Tauri GUI build not found at $TauriExe - Portable ZIP will be built without the GUI binary. Run 'cd gui && npm install && npm run tauri build' first to include the GUI."
}

# 6. Launcher (after Tauri detection so the .bat help text and runtime branch
# can reflect whether allaganeye-gui.exe is bundled, #617).
# Template is defined as Get-LauncherTemplate (#583) so Pester can verify the
# exit code propagation idiom (#580) and #617 dispatch branches without
# dot-sourcing the full build path.
$Launcher = Get-LauncherTemplate -IncludeGui:$TauriIncluded
Set-Content -Path (Join-Path $PayloadDir 'allaganeye.bat') -Value $Launcher -Encoding ASCII

# 7. README (after Tauri detection so the GUI section is conditional)
$Readme = Format-ReadmeContent `
  -Version $Version `
  -FFmpegVersion $FFmpegVersion `
  -FFmpegBuildTag $FFmpegBuildTag `
  -FFmpegSourceRef $FFmpegSourceRef `
  -IncludeGui:$TauriIncluded
Set-Content -Path (Join-Path $PayloadDir 'README.txt') -Value $Readme -Encoding UTF8
```

実行:

```text
Edit tool で:
  file_path: scripts/build-portable-zip.ps1
  old_string: <line 391-427 全体、# 5. Launcher ... Set-Content ... README.txt' -Value $Readme -Encoding UTF8 まで>
  new_string: <上記新 body>
```

- [ ] **Step 2: PowerShell syntax check**

```bash
pwsh -NoProfile -Command "& { . ./scripts/build-portable-zip.ps1; Write-Host 'dot-source OK' }"
```

Expected: `dot-source OK` が出力される。dot-source 時 (`-Version` 未指定) は build を skip する既存挙動 (line 301 の `if ([string]::IsNullOrEmpty(\$Version)) { return }`) が壊れていないことを verify。

- [ ] **Step 3: 全 Pester suite を再実行 (regression check)**

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed"
```

Expected: 全 test PASS、failure 0 件。Get-LauncherTemplate と Format-ReadmeContent の signatures が変わっても dot-source loader (BeforeAll) で問題なくロードされることを確認。

---

## Task 7: 統合 commit (Pester test + 実装 + reorder + README)

**Files:** stage 済 `scripts/build-portable-zip.ps1` + `scripts/tests/build-portable-zip.Tests.ps1`

- [ ] **Step 1: git diff で変更確認**

```bash
git diff scripts/build-portable-zip.ps1
git diff scripts/tests/build-portable-zip.Tests.ps1
```

Expected:

- `build-portable-zip.ps1`: 3 領域変更 — `Format-ReadmeContent` (line 158-244) / `Get-LauncherTemplate` (line 246-297) / main path Step 5-7 reorder (line 391-427)
- `Tests.ps1`: 2 領域変更 — `Describe 'Get-LauncherTemplate'` (新 7 個 It 追加) / `Describe 'Format-ReadmeContent'` (新 2 個 It 追加)
- 他 file への変更なし (Iron Law 3、scope 厳守)

- [ ] **Step 2: git add + commit**

```bash
git add scripts/build-portable-zip.ps1 scripts/tests/build-portable-zip.Tests.ps1
git commit -m "$(cat <<'EOF'
feat(installer): allaganeye.bat ダブルクリックで GUI 起動 (Refs #617)

Get-LauncherTemplate を label-based dispatch (5 branch) に再構成し、
引数なし時に allaganeye-gui.exe を起動するよう挙動変更。-IncludeGui switch を
新設して Format-ReadmeContent と対称化、build 時の help/README 文言を切替。

主な変更:
- scripts/build-portable-zip.ps1
  - Get-LauncherTemplate: -IncludeGui switch 追加、:show_help label 導入、
    --help/-h/-h /?  + no-args (GUI exe 存在時 start "" "...exe" + exit /b 0、
    不在時 :show_help fallback) + 動画ドラッグ + CLI passthrough の 5 branch dispatch。
    既存 #580 EXIT_CODE 伝搬 idiom (CLI 用法側) は維持
  - Format-ReadmeContent: -IncludeGui:$true 時に "Easiest: double-click
    allaganeye.bat" section を最上部に挿入、旧 "GUI: double-click .exe"
    section を merge 削除、section 名を Drag-and-drop / Command Prompt に rename
  - main path: Tauri detection (Step 5) を Launcher (Step 6) の前に reorder、
    Get-LauncherTemplate -IncludeGui:$TauriIncluded を注入

- scripts/tests/build-portable-zip.Tests.ps1
  - Describe 'Get-LauncherTemplate': 既存 #580 regression test を残しつつ、
    7 個の It (no-args GUI launch / fallback / --help dispatch / 動画ドラッグ
    case-insensitive regression / CLI passthrough regression / -IncludeGui:$true
    help text / -IncludeGui:$false help text) を追加
  - Describe 'Format-ReadmeContent': 既存 4 個の It を維持しつつ、
    -IncludeGui:$true README が ".bat double-click → GUI" を 1 番目に documenting
    すること、section 順 (GUI → drag-drop → Command Prompt) を asserting する
    2 個の It を追加

CLI-only ZIP (GUI exe 未同梱) でも `.bat` ダブルクリック時は従来通り
ヘルプ表示にフォールバック (defensive runtime if exist check + :show_help)。

Refs #617
Session: sleepy-liskov-609b81

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit 成功 (2 file changed, ~150-200 insertions(+), ~50-80 deletions(-))。

- [ ] **Step 3: 直前 commit で Pester regression が起きていないか最終確認**

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed" 2>&1 | tail -30
```

Expected: 全 test PASS。Tests Passed: ≥17, Failed: 0。

---

## Task 8: PR 作成直前の Iron Law 6 Pre-flight 再実施

**Files:** なし (git / gh CLI 操作のみ)

- [ ] **Step 1: develop-0.2.0 fetch + 取り込み未済 commit 確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 取り込み未済 commit list を確認。実装中に他 lane が merge した可能性 (特に Lane IV-a §2 #681 が先に merge していた場合の `build-portable-zip.ps1` line 49-75 の hash pin 変更)。

- [ ] **Step 2: 並行 worktree PR の重複 + 同 file touch 確認**

```bash
gh pr list --search "#617" --state all --json number,title,state
gh pr list --state open --base develop-0.2.0 --json number,title,headRefName
```

Expected: #617 を扱う PR がない、`build-portable-zip.ps1` を touch する他の open PR がない。重複あれば作業中止して Idios に AskUserQuestion で確認。

- [ ] **Step 3: 取り込み未済が build-portable-zip.ps1 / Tests.ps1 を touch していれば merge + Pester 再実行**

```bash
git log HEAD..origin/develop-0.2.0 --name-only | grep -E 'scripts/(build-portable-zip\.ps1|tests/build-portable-zip\.Tests\.ps1)' || echo "no conflict in build-portable-zip"
```

If conflicting commits exist:

```bash
git merge origin/develop-0.2.0
# 解決後
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed"
```

Expected: conflict 解決 + Pester 全 PASS。

---

## Task 9: PR 本文準備 + gh pr create

**Files:** なし (gh CLI 操作 + 一時 PR body file)

- [ ] **Step 1: PR 本文を一時ファイルに準備**

```bash
mkdir -p /tmp/pr-617
cat > /tmp/pr-617/body.md <<'EOF'
## 概要

Portable ZIP 同梱の `allaganeye.bat` をダブルクリック (引数なし) で `allaganeye-gui.exe` を起動するよう挙動変更。`--help` / `-h` / `/?` で従来のヘルプ表示、CLI 用法 (動画ドラッグ・サブコマンド) は完全保持。CLI-only ZIP (GUI exe 未同梱) ではヘルプ fallback (Refs #617)。

## 変更点

### `Get-LauncherTemplate` を label-based dispatch (5 branch) に再構成

- `scripts/build-portable-zip.ps1` line 246-297
- 上から順に判定、最初にマッチを実行:
  1. `--help` / `-h` / `/?` → `:show_help`
  2. 引数なし + `allaganeye-gui.exe` 存在 → `start "" "%PAYLOAD%allaganeye-gui.exe"` + `exit /b 0`
  3. 引数なし + `allaganeye-gui.exe` 不在 → `:show_help` (CLI-only ZIP fallback)
  4. 動画拡張子 (`.mp4`/`.mkv`/`.avi`/`.mov` case-insensitive) → `python -m allaganeye split %*`
  5. その他引数 → `python -m allaganeye %*`
- `-IncludeGui` switch を新設 (`Format-ReadmeContent` と対称化)、help text を build 時に切替
- 既存 #580 EXIT_CODE 伝搬 idiom (CLI 用法側) は維持
- 既存 path idiom (`%PAYLOAD%`) と動画ドラッグ idiom (`if /i "%EXT%"==".mp4"`) は完全保持

### `Format-ReadmeContent` の section 順を更新

- `scripts/build-portable-zip.ps1` line 158-244
- `-IncludeGui:$true` 時: `### Easiest: double-click ``allaganeye.bat``` を `## Usage` 直下に配置
- 旧 `### GUI: double-click ``allaganeye-gui.exe``` section を merge 削除 (`.bat` が `.exe` を起動するため重複)
- 旧 `### Basic: drag-and-drop` を `### Drag-and-drop a video file` に rename
- 旧 `### Advanced: from a Command Prompt` を `### From a Command Prompt` に rename
- WebView2 Runtime の依存性 note を新 GUI section に移動

### build script main path を Tauri detection → Launcher 順に reorder

- `scripts/build-portable-zip.ps1` line 391-427
- Step 5 (旧 Launcher) と Step 6 (旧 Tauri detection) を入れ替え
- `Get-LauncherTemplate -IncludeGui:$TauriIncluded` を Launcher 書き出しに注入

### Pester test を追加

- `scripts/tests/build-portable-zip.Tests.ps1`
- `Describe 'Get-LauncherTemplate'`: 既存 #580 EXIT_CODE regression を残しつつ 7 個の `It` 追加 (no-args GUI launch / fallback / `--help`/`-h`/`/?` dispatch / 動画ドラッグ regression / CLI passthrough regression / `-IncludeGui:$true` help text / `-IncludeGui:$false` help text)
- `Describe 'Format-ReadmeContent'`: 既存 4 個を維持しつつ、`-IncludeGui:$true` README が `.bat double-click → GUI` を 1 番目に documenting すること、section 順 (GUI → drag-drop → Command Prompt) を asserting する 2 個の `It` 追加

## Self-Test Report

### Machine-verified (自動検証済み)

- [x] PowerShell syntax: `pwsh -NoProfile -Command "& { . ./scripts/build-portable-zip.ps1; Write-Host 'dot-source OK' }"` PASS
- [x] Pester (local): `Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1` 全 test PASS (Failed: 0)
- [x] CI `installer-pester` job: PASS (regression なし、新 9 test 追加)
- [x] CI `markdownlint` job: PASS
- [x] CI `validate-checklist` job: PASS

### Machine-unverifiable (Idios 実機検証必須、Iron Law 6 trigger)

- GUI 同梱 ZIP (CI artifact から取得) で `allaganeye.bat` ダブルクリック → `allaganeye-gui.exe` が起動する + cmd ウィンドウが残らない
- GUI 同梱 ZIP で `allaganeye.bat --help` (および `-h` / `/?`) → ヘルプ表示 + `pause` で待機
- GUI 同梱 ZIP で `allaganeye.bat split <video.mkv>` → 従来通り動画分割が走る
- GUI 同梱 ZIP で `<video.mkv>` を `allaganeye.bat` にドラッグ → 従来通り動画分割が走る
- CLI-only ZIP (ローカル dry-run、GUI exe 未同梱) で `allaganeye.bat` ダブルクリック → ヘルプ表示 + `pause` (旧 fallback)

## 受け入れ条件 (元 issue #617 逐条)

- [x] `allaganeye.bat` をダブルクリック → `allaganeye-gui.exe` が起動 (cmd ウィンドウは残らない) → 上記 Machine-unverifiable で Idios 確認
- [x] `allaganeye.bat --help` (および `-h` / `/?`) でヘルプ表示 → 上記 Machine-unverifiable で Idios 確認 + Pester で 3 dispatch line の存在を assert
- [x] `allaganeye.bat split <video>` 等の CLI 用法が従来通り動作 (動画ドラッグ含む) → 上記 Machine-unverifiable で Idios 確認 + Pester で `if /i "%EXT%"==".mp4"` 等 + `python -m allaganeye split %*` の preserve を assert
- [x] CLI-only ZIP (GUI exe 未同梱) で `.bat` ダブルクリック → 従来通りヘルプ表示にフォールバック → 上記 Machine-unverifiable で Idios 確認 + Pester で `if exist "%PAYLOAD%allaganeye-gui.exe"` + `goto :show_help` fallback の存在を assert
- [x] `Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1` 全 PASS (新挙動 + 既存 #580 idiom regression) → Machine-verified + CI で確認
- [x] CI 全 jobs PASS → Machine-verified にて確認

## Refs

- Refs #617 (本 issue)
- 上位 plan: [docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md](../../docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md) (Lane IV-a / Group F §3)
- 設計 spec: [docs/superpowers/specs/2026-05-08-l2b-distribution-design.md](../../docs/superpowers/specs/2026-05-08-l2b-distribution-design.md) §3
- 実装 plan: [docs/superpowers/plans/2026-05-08-l2b-617-bat-gui-launch.md](../../docs/superpowers/plans/2026-05-08-l2b-617-bat-gui-launch.md)
- 前提: #570 / PR #615 (`allaganeye-gui.exe` Portable ZIP 同梱)
- 関連: PR #580 (EXIT_CODE 伝搬 idiom、本 PR で regression test 維持)

Session: sleepy-liskov-609b81

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

> **memory feedback `feedback_gh_command_ja_heredoc.md`**: gh command の日本語本文は `--body-file` または HEREDOC で渡すこと。inline `-b "..."` で日本語を渡すと UTF-8 が破損する Windows + Git Bash の既知 bug (Issue #31295)。

- [ ] **Step 2: gh pr create を実行 (`Closes/Fixes/Resolves` 禁止 = Iron Law 4)**

```bash
gh pr create \
  --base develop-0.2.0 \
  --title "feat(installer): allaganeye.bat ダブルクリックで GUI 起動 (Refs #617)" \
  --body-file /tmp/pr-617/body.md
```

Expected: PR URL が出力される。PR title / body に `Closes/Fixes/Resolves` キーワード未使用 (Iron Law 4)。

- [ ] **Step 3: PR 本文を grep で Iron Law 4 final check**

```bash
gh pr view --json body --jq '.body' | grep -E "(Closes|Fixes|Resolves) #" && echo "VIOLATION" || echo "OK"
```

Expected: `OK` (`Closes/Fixes/Resolves` キーワード未使用)。

---

## Task 10: CI 実走 + Idios 実機検証依頼

**Files:** なし (gh CLI + AskUserQuestion 操作)

- [ ] **Step 1: CI 全 jobs PASS を待つ**

```bash
gh pr checks --watch
```

Expected: 全 jobs PASS:

- `build-windows` (build-portable-zip.ps1 完走 + smoke test)
- `installer-pester` (Pester 全 test PASS)
- `markdownlint`
- `validate-checklist`
- (該当する場合) `lint-py` / `typecheck-py` / `lint-gui` / `test-gui` / `build-gui` (本 PR は Python / GUI 変更なしのため通常 trigger されないが念のため確認)

fail があれば該当 job log で原因確認。`(A) PR 内修正` (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」) で対応する。

- [ ] **Step 2: CI artifact から GUI 同梱 ZIP を取得 (Idios 実機検証 prep)**

```bash
gh run list --workflow=release.yml --branch=$(git branch --show-current) --limit=1 --json databaseId,headSha,status --jq '.[0]'
# DATABASE_ID を取得
gh run download <DATABASE_ID> --name "allaganeye-portable-windows-v$(grep -E '^version' pyproject.toml | head -1 | cut -d '"' -f 2)" --dir /tmp/pr-617/artifact
ls /tmp/pr-617/artifact/
```

Expected: artifact ディレクトリに `allaganeye-vX.Y.Z/` が展開され、`allaganeye.bat`, `allaganeye-gui.exe`, `python/`, `ffmpeg/`, `lib/`, `README.txt` 等が確認できる。`allaganeye-gui.exe` が含まれていれば GUI 同梱 ZIP として実機検証可能。

> **note**: GitHub Actions の artifact retention はデフォルト 90 日。CI run 直後にダウンロードする。Idios の Windows 実機で行う場合は本 step を Idios の手順に書き換える (gh run download を Windows で実行)。

- [ ] **Step 3: AskUserQuestion で Idios に実機検証依頼 (Iron Law 6)**

```text
質問: 本 PR の実機検証 5 項目を Idios の Windows 実機で確認してください (mock 不可、GUI Tauri 起動が絡む)。CI artifact `allaganeye-portable-windows-v<VERSION>` を Windows にダウンロード → 展開 → 以下を順に確認。
ヘッダ: 実機検証 (#617)

選択肢:
- (a) 全 5 項目 OK (Recommended)
  以下 5 項目すべて期待通り:
    1. GUI 同梱 ZIP で `allaganeye.bat` ダブルクリック → `allaganeye-gui.exe` が起動 + cmd ウィンドウ残らない
    2. GUI 同梱 ZIP で `allaganeye.bat --help` / `-h` / `/?` でヘルプ表示 + pause
    3. GUI 同梱 ZIP で `allaganeye.bat split <video.mkv>` → 従来通り動画分割
    4. GUI 同梱 ZIP で `<video.mkv>` ドラッグ → 従来通り動画分割
    5. CLI-only ZIP (ローカル dry-run、GUI exe 未同梱) で `.bat` ダブルクリック → ヘルプ表示 + pause
- (b) 1 項目以上で問題あり
  問題箇所を free text で記述。`(A) PR 内追加修正` で対応するか、問題内容次第で plan 見直し。
- (c) 検証環境を準備できないため後で
  CI artifact 取得方法 / 実機検証手順を docs に追記して merge 一旦保留。
```

(b) (c) なら原因切り分け → (A) PR 内追加修正 で対応 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)。

- [ ] **Step 4: 全 5 項目 OK 後、PR を Idios review 待ちに移行**

本 plan の scope 外: PR merge 判断と issue close は Idios + `/review-pr` skill で別途実施。本 plan は PR 作成 + CI 確認 + Idios 実機検証依頼まで。

---

## Task 11: (Task 1 で (b) または (c) を選んだ場合のみ) CLAUDE.md / system-architecture.md 更新

**Files:**

- (b) 採用時: `CLAUDE.md` line 31, `docs/system-architecture.md` (該当箇所)
- (c) 採用時: `CLAUDE.md` line 31

> **(a) 採用時はこの Task は skip**。Task 12 (follow-up issue 起票) を実施する。

- [ ] **Step 1: CLAUDE.md line 31 更新 ((b) (c) 共通)**

実行:

```text
Edit tool で:
  file_path: CLAUDE.md
  old_string: > **配布物の起動経路**: Portable ZIP の `allaganeye.bat` = CLI 起動 / Tauri bundle の `allaganeye-gui.exe` (v0.2.0+) = GUI 起動。**別 exe 方式** (#527 で確定)。
  new_string: > **配布物の起動経路**: Portable ZIP の `allaganeye.bat` 引数なしダブルクリック (v0.2.0+ #617) = GUI (`allaganeye-gui.exe`) 起動 / `allaganeye.bat <args>` = CLI 起動 / Tauri bundle の `allaganeye-gui.exe` 直接 = GUI 起動。**別 exe 方式** (#527 で確定)。
```

- [ ] **Step 2: docs/system-architecture.md 該当箇所更新 ((b) のみ)**

(c) 採用時は本 step を skip。

```bash
grep -n "allaganeye.bat\|別 exe" docs/system-architecture.md | head -10
```

該当箇所を `.bat` ダブルクリック時の挙動が GUI 起動に変わる旨に更新。

> **判断**: 具体的な編集箇所は `docs/system-architecture.md` の grep 結果を見てから決定。grep で複数箇所ヒットした場合は (b) を選んだユーザーに「どの箇所を更新するか」を再 AskUserQuestion で確認 (Iron Law 5)。

- [ ] **Step 3: 該当 commit を分離 (本 PR 内、別 commit)**

```bash
git add CLAUDE.md docs/system-architecture.md  # (c) 時は CLAUDE.md のみ
git commit -m "$(cat <<'EOF'
docs: .bat double-click 挙動変更 (#617) を CLAUDE.md / system-architecture.md に反映

CLAUDE.md line 31 の起動経路記述で「.bat = CLI 起動」を「.bat 引数なし
ダブルクリック = GUI 起動 / .bat <args> = CLI 起動」に更新。
docs/system-architecture.md の dispatch 表 (#527) も同様に更新。

Refs #617
Session: sleepy-liskov-609b81

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 4: PR 本文に doc 更新セクションを追記 (Self-Test Report 更新)**

```bash
gh pr edit --body-file <(cat /tmp/pr-617/body.md; cat <<'EOF'

## 追加変更 (Task 1 で scope 拡張選択)

- `CLAUDE.md` line 31 の `.bat` 起動経路記述を更新
EOF
)
```

(c) 時のみ。(b) 時は `docs/system-architecture.md` も追記。

---

## Task 12: (Task 1 で (a) を選んだ場合のみ) follow-up issue 起票

**Files:** なし (gh CLI 操作のみ)

> **(b) (c) 採用時はこの Task は skip**。

- [ ] **Step 1: follow-up issue を起票 (PR 作成後、CI PASS 後に実施)**

```bash
cat > /tmp/pr-617/followup-issue.md <<'EOF'
## 概要

#617 マージ後、`CLAUDE.md` line 31 と `docs/system-architecture.md` の起動経路記述が `.bat` ダブルクリック挙動変更を反映しておらず stale になる。doc 整合性のため両 file を更新する。

## 背景

- #617 (PR #<本 PR 番号>) で `allaganeye.bat` 引数なしダブルクリック時の挙動が「ヘルプ表示」から「`allaganeye-gui.exe` 起動」に変更
- CLAUDE.md line 31 の dispatch 表は `.bat = CLI 起動` のままで factual に不正確
- docs/system-architecture.md の関連箇所も同様

## 作業内容

- [ ] CLAUDE.md line 31 の `> **配布物の起動経路**: ...` を新挙動 (`.bat 引数なし = GUI`, `.bat <args> = CLI`, `.exe 直接 = GUI`) に更新
- [ ] docs/system-architecture.md の dispatch 表 (#527 由来) を同様に更新
- [ ] CI markdownlint + validate-checklist PASS

## 受け入れ条件

- [ ] CLAUDE.md line 31 が新挙動を正確に反映
- [ ] docs/system-architecture.md の関連箇所が新挙動を正確に反映
- [ ] CI 全 jobs PASS

## 関連

- 元: #617 (PR #<本 PR 番号> で `.bat` 挙動変更)
- 設計 spec: [docs/superpowers/specs/2026-05-08-l2b-distribution-design.md](docs/superpowers/specs/2026-05-08-l2b-distribution-design.md) §3
- Iron Law 3 分離: 本 PR scope を spec §3 受け入れ条件のみに限定するため follow-up 化

作成: sleepy-liskov-609b81
EOF

gh issue create \
  --title "[task] L2b: #617 マージ後の CLAUDE.md / system-architecture.md 起動経路記述更新" \
  --body-file /tmp/pr-617/followup-issue.md \
  --label "P3-low,task,l2b-installer,docs"
```

> **note**: label `docs` が repo に存在しない場合は label 引数から外す。`gh label list` で確認。

- [ ] **Step 2: 起票結果を Idios に報告**

```bash
ISSUE_URL=$(gh issue list --search "L2b: #617 マージ後の CLAUDE.md" --state open --json url --jq '.[0].url')
echo "Follow-up issue created: $ISSUE_URL"
```

PR 本文に follow-up issue link を追記:

```bash
gh pr edit --body-file <(cat /tmp/pr-617/body.md; cat <<EOF

## 追加 (scope 分離 follow-up)

- $ISSUE_URL: 本 PR scope に含めない CLAUDE.md / system-architecture.md 更新を follow-up issue として分離 (Iron Law 3 厳守)
EOF
)
```

---

## Self-Review

### Spec coverage

spec §3 の各要素を本 plan の Task でマッピング:

- [x] **§3 受け入れ条件 1: `.bat` ダブルクリック → GUI 起動 (cmd ウィンドウ残らない)** → Task 4 Step 1 (`start "" "%PAYLOAD%allaganeye-gui.exe"` + `endlocal` + `exit /b 0`) + Task 10 Step 3 Idios 実機検証
- [x] **§3 受け入れ条件 2: `--help` / `-h` / `/?` でヘルプ表示** → Task 3 Step 1 (Pester 3 line dispatch assert) + Task 4 Step 1 (3 line `goto :show_help` dispatch) + Task 10 Step 3 Idios 実機検証
- [x] **§3 受け入れ条件 3: CLI 用法が従来通り (動画ドラッグ + `split` 引数指定)** → Task 3 Step 1 (Pester 4 拡張子 `if /i` regression + `python -m allaganeye split %*` regression + CLI passthrough regression) + Task 4 Step 1 (既存 idiom 完全保持) + Task 10 Step 3 Idios 実機検証
- [x] **§3 受け入れ条件 4: CLI-only ZIP で `.bat` ダブルクリック → ヘルプ fallback** → Task 3 Step 1 (Pester `if exist "%PAYLOAD%allaganeye-gui.exe"` + `goto :show_help` fallback assert) + Task 4 Step 1 (runtime defensive `if exist`) + Task 10 Step 3 Idios 実機検証
- [x] **§3 受け入れ条件 5: Pester 全 PASS (新挙動 + #580 idiom regression)** → Task 3 / Task 4 / Task 5 / Task 6 / Task 7 (各 step で Pester 走らせ + green 維持)
- [x] **§3 受け入れ条件 6: CI 全 jobs PASS** → Task 10 Step 1 (`gh pr checks --watch`)

spec §3 §設計 の 5 branch dispatch 表 → Task 4 Step 1 で全 branch を template に明示的に実装。

spec §3 §影響範囲 → Task 4 (`Get-LauncherTemplate`) / Task 5 (`Format-ReadmeContent`) / Task 6 (build script main path reorder) / Task 3 (Pester) で全 file をカバー。

spec §3 §実装方針 6 step → Task 4 Step 1 (1-4 step を一括) + Task 5 Step 1 (5-6 step) + Task 6 Step 1 (build script reorder)。

spec §3 §テスト方針 (Pester + 実機) → Task 3 / Task 4 Step 2 / Task 5 Step 2 / Task 6 Step 3 / Task 7 Step 3 (Pester 各時点 verify) + Task 10 Step 3 (Idios 実機 5 項目)。

spec §3 §開放問題 (writing-plans 持ち越し 2 点) → 本 plan 冒頭で解決 (`%PAYLOAD%` idiom 確認 / `if /i` case-insensitive 確認)、Task 4 Step 1 で 2 idiom を完全保持。

### Placeholder scan

- [x] "TBD" / "TODO" / "implement later" / "fill in details" なし
- [x] "Add appropriate error handling" / "add validation" / "handle edge cases" なし (各 task に actual diff or 完全 code を記載)
- [x] "Write tests for the above" 単独使用なし (Task 3 で完全 Pester body 記載)
- [x] "Similar to Task N" の使い回しなし (各 task に full code)
- [x] "Implementation: <略>" 形式の手抜きなし (Task 4 / 5 / 6 で full code block 記載)

### Type consistency

- `Get-LauncherTemplate` signature: Task 3 (Pester) / Task 4 (impl) / Task 7 (commit msg) で全て `-IncludeGui` (PowerShell `[switch]`) で一貫
- `Format-ReadmeContent` signature: Task 3 / Task 5 / Task 6 で `-IncludeGui` 既存 switch を再利用、新規追加なし
- 環境変数: `%PAYLOAD%` (cmd.exe `set PAYLOAD=...` で定義) を `Get-LauncherTemplate` 内で一貫使用、`%~dp0` は line 258 の初期 capture でのみ使用 (idiom 維持)
- 動画拡張子 enum: `.mp4` / `.mkv` / `.avi` / `.mov` の 4 種を Task 3 (Pester) / Task 4 (impl) で同じ順序 + 同じ `if /i` syntax で記載
- branch 順序 (5 branch): Task 4 Step 1 の comment / Task 9 Step 1 の PR body / spec §3 §設計表で同じ順序 (1: `--help` / 2: no-args + GUI / 3: no-args + fallback / 4: video / 5: other args)

### File path consistency

- `scripts/build-portable-zip.ps1` (`Get-LauncherTemplate` line 246-297, `Format-ReadmeContent` line 158-244, main path Step 5-7 line 391-427) を全 Task で正確に参照
- `scripts/tests/build-portable-zip.Tests.ps1` (`Describe 'Get-LauncherTemplate'` line 210-220, `Describe 'Format-ReadmeContent'` line 133-208) を全 Task で正確に参照
- 一時 file は `/tmp/pr-617/` 配下に集約 (Windows + Git Bash でも `/tmp` は MSYS が `C:\Users\<user>\AppData\Local\Temp\` に変換して動作)

### Iron Law 整合

- [x] **Iron Law 1**: spec §3 受け入れ条件 6 項目を Task 9 Step 1 PR body 内で逐条引用 + 各項目に対応 Task / 検証手段を記載
- [x] **Iron Law 2**: 本 plan は単一 PR / 単一 issue なので bulk operation 該当なし
- [x] **Iron Law 3**: scope 拡張可能性 (CLAUDE.md / system-architecture.md) を Task 1 で AskUserQuestion 確認 (a) 別 issue 分離 / (b) 本 PR 拡張 / (c) CLAUDE.md のみ拡張 の 3 択
- [x] **Iron Law 4**: PR title / body / commit msg で `Closes/Fixes/Resolves` 禁止、`Refs #617` のみ → Task 7 / Task 9 / Task 11 / Task 12 で各 commit msg / body 記載確認、Task 9 Step 3 で grep final check
- [x] **Iron Law 5**: Task 1 (CLAUDE.md scope) / Task 10 Step 3 (実機検証 disposition) で AskUserQuestion 必須化、独断回避
- [x] **Iron Law 6**: Task 2 / Task 8 で PR Pre-flight (`git fetch` + 取り込み未済 + 並行 worktree PR 重複) 2 回実施、Task 10 Step 3 で実機検証 trigger を AskUserQuestion で Idios に依頼

---

## 関連 doc

- 上位 plan: [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](2026-05-07-l2-v020-roadmap.md) Lane IV-a / Group F §3
- 設計 spec: [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](../specs/2026-05-08-l2b-distribution-design.md) §3
- 兄弟 plan (Lane IV-a §1): [`docs/superpowers/plans/2026-05-08-l2b-616-artifact-version.md`](2026-05-08-l2b-616-artifact-version.md) (CLOSED, PR #686)
- `docs/l2-workflow.md` §「PR 作成 Pre-flight」 / §「Self-Test Report 規約」 / §「(A) PR 内修正優先 規約」 / §「PR 作成 path 別自動チェック」 / §「実機検証 trigger 表」
- `.claude/hooks/session-start.sh` Iron Law 1 / 3 / 4 / 5 / 6
- 前提 PR: [#615](https://github.com/Idios/kobutachan-allaganeye/pull/615) (`allaganeye-gui.exe` Portable ZIP 同梱) / [#580](https://github.com/Idios/kobutachan-allaganeye/pull/580) (EXIT_CODE 伝搬 idiom、本 PR で regression test 維持)
- memory feedback: `feedback_gh_command_ja_heredoc.md` / `feedback_powershell_native_redirect.md`
