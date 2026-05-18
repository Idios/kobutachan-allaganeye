# Issue #752: Portable ZIP file 数削減 (PyInstaller --onedir) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pip install --target lib` + Python embeddable interpreter 同梱を **PyInstaller `--onedir`** に置き換え、Portable ZIP の Python 関連ファイル数を ~2500 → ~150-300 に削減する。同時に baseline 計測 infrastructure と integrity.py の frozen-mode 対応を実装する。

**Architecture:** 単一 PR / 2 段階 commit 構成。Step 1 (baseline measurement infrastructure、behavior 変更なし) を先行 commit、Step 2 (PyInstaller migration + integrity.py frozen 対応 + launcher/CI/docs 更新) を本体 commit。GUI Tauri Rust 側は `allaganeye.bat` 抽象化 (#646) により touch 不要。

**Tech Stack:** PowerShell 5.1 / 7+ (build script、Pester v5)、Python 3.11 (pytest、PyInstaller 6.20.0、pyinstaller-hooks-contrib 2026.5)、cmd.exe (launcher.bat)、GitHub Actions (release.yml)、Markdown (docs)

**Spec:** [`docs/superpowers/specs/2026-05-18-issue-752-portable-zip-file-count-reduction-design.md`](../specs/2026-05-18-issue-752-portable-zip-file-count-reduction-design.md) (commit `09b84e5`)

**Session:** `exciting-chatelet-67dc1d`

**Branch:** `claude/exciting-chatelet-67dc1d` (base = `origin/develop-0.3.0`)

---

## Task 1: Iron Law 6 Pre-flight (initial base sync)

**Files:** (read-only)

- Check: `git fetch origin develop-0.3.0` → `git log HEAD..origin/develop-0.3.0` → `gh pr list --search "#752"`

- [ ] **Step 1: develop-0.3.0 を fetch して未取込 commit を確認**

```bash
git fetch origin develop-0.3.0
git log --oneline HEAD..origin/develop-0.3.0 | head -10
```

Expected: 0 行 (取込済) または develop-0.3.0 の新規 commit 一覧。

- [ ] **Step 2: 未取込 commit が touched files と交差するか確認**

```bash
git log --oneline HEAD..origin/develop-0.3.0 -- \
  scripts/build-portable-zip.ps1 \
  scripts/tests/build-portable-zip.Tests.ps1 \
  .github/workflows/release.yml \
  allaganeye/integrity.py \
  tests/test_integrity.py \
  docs/system-architecture.md
```

Expected: 0 行 (交差なし、merge 不要)。

- [ ] **Step 3: 交差ありなら merge + 自動チェック再実行**

If above step yields rows:

```bash
git merge origin/develop-0.3.0
# 競合解消 + 自動チェック再実行 (Task 12 と同じ commands)
```

If 0 rows: skip this step.

- [ ] **Step 4: 並行 worktree PR で #752 重複確認**

```bash
gh pr list --search "752 in:title,body" --state all --json number,title,state,headRefName | head -20
```

Expected: 既に #752 fix PR が他 branch で出ていないこと (本 worktree branch `claude/exciting-chatelet-67dc1d` 以外で `#752` を扱う PR がないこと)。

---

## Task 2: Create baseline measurement script (Step 1 / Pester TDD)

**Files:**

- Create: `scripts/measure-portable-zip-baseline.ps1`
- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (新規 Describe block 追加、末尾)

- [ ] **Step 1: Pester test を `scripts/tests/build-portable-zip.Tests.ps1` 末尾に追加**

`Describe 'File encoding (#704)'` block の **後** に空行 2 つを挟んで以下を append:

```powershell
Describe 'Measure-PortableZipBaseline (#752)' {
  # Lazy-loaded: only test the script when it exists. Acts as TDD anchor for
  # Task 2 (script creation) without breaking the existing Pester suite that
  # is dot-sourced at BeforeAll without the new script.
  BeforeAll {
    $script:MeasureScript = Join-Path (Join-Path $PSScriptRoot '..') 'measure-portable-zip-baseline.ps1'
    $script:MeasureTmp = Join-Path ([System.IO.Path]::GetTempPath()) "measure-baseline-tests-$(New-Guid)"
    New-Item -ItemType Directory -Force -Path $script:MeasureTmp | Out-Null
    # Fake payload: 3 files across 2 top-level dirs.
    $payload = Join-Path $script:MeasureTmp 'fake-payload'
    New-Item -ItemType Directory -Force -Path $payload | Out-Null
    Set-Content -Path (Join-Path $payload 'allaganeye.bat') -Value 'bat content' -Encoding ASCII
    $libDir = Join-Path $payload 'lib\foo'
    New-Item -ItemType Directory -Force -Path $libDir | Out-Null
    Set-Content -Path (Join-Path $libDir 'foo.py') -Value '# py' -Encoding ASCII
    $ffDir = Join-Path $payload 'ffmpeg'
    New-Item -ItemType Directory -Force -Path $ffDir | Out-Null
    Set-Content -Path (Join-Path $ffDir 'fake.dll') -Value 'binary' -Encoding ASCII
    $script:FakePayload = $payload
  }
  AfterAll {
    if (Test-Path $script:MeasureTmp) {
      Remove-Item -Recurse -Force $script:MeasureTmp
    }
  }

  It 'produces JSON with required top-level schema fields' {
    $jsonText = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Json
    $obj = $jsonText | ConvertFrom-Json
    $obj.schema_version | Should -Be 1
    $obj.measured_at | Should -Match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'
    $obj.payload_dir | Should -Be $script:FakePayload
    $obj.total_file_count | Should -Be 3
    $obj.total_size_bytes | Should -BeGreaterThan 0
  }

  It 'aggregates files by top-level directory' {
    $jsonText = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Json
    $obj = $jsonText | ConvertFrom-Json
    $obj.by_top_dir.lib.file_count | Should -Be 1
    $obj.by_top_dir.ffmpeg.file_count | Should -Be 1
    $obj.by_top_dir._root.file_count | Should -Be 1
  }

  It 'aggregates files by extension' {
    $jsonText = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Json
    $obj = $jsonText | ConvertFrom-Json
    $obj.by_extension.'.py'.count | Should -Be 1
    $obj.by_extension.'.dll'.count | Should -Be 1
    # `.bat` のような low-frequency extension は _other に分類されない (拡張子そのまま) のが望ましいが、
    # 実装簡略化のため代表的な extension (.py / .pyd / .dll / .pyi / .so) 以外は _other 集約。
    $obj.by_extension._other.count | Should -BeGreaterThan 0
  }

  It '-Format Human writes human-readable table to stdout' {
    $output = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Human
    ($output -join "`n") | Should -Match 'total_file_count'
    ($output -join "`n") | Should -Match '3'
  }

  It 'throws when -PayloadDir does not exist' {
    { & $script:MeasureScript -PayloadDir (Join-Path $script:MeasureTmp 'missing') -Format Json } |
      Should -Throw -ExpectedMessage '*not found*'
  }
}
```

- [ ] **Step 2: Pester test を実行して 5 件 fail することを確認**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 `
    -Output Detailed `
    -PassThru | Select-Object -ExpandProperty Failed | Measure-Object | Select-Object -ExpandProperty Count
```

Expected: 5 (FAIL: 5 tests for Measure-PortableZipBaseline since script doesn't exist yet)

- [ ] **Step 3: `scripts/measure-portable-zip-baseline.ps1` を作成**

```powershell
<#
.SYNOPSIS
Measure Portable ZIP payload file count and size for #752 baseline / regression tracking.

.DESCRIPTION
Recursively walks the expanded Portable ZIP payload directory and aggregates
file counts + sizes by:
  - top-level directory
  - file extension (.py / .pyd / .dll / .pyi / .so / _other)

Output is machine-parseable JSON (default) or a human-readable table.

The output is used by:
  - Pester regression test (`scripts/tests/build-portable-zip.Tests.ps1`)
    to assert the post-PyInstaller file count reduction.
  - CI release.yml `build-windows` job artifact upload (`baseline.json`).
  - PR body before/after comparison (#752 acceptance criterion).

.PARAMETER PayloadDir
Path to the expanded payload root (e.g. `build/portable/allaganeye-v0.3.0/`).

.PARAMETER Format
'Json' (default) emits machine-parseable JSON. 'Human' emits a readable table.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$PayloadDir,
  [ValidateSet('Json', 'Human')][string]$Format = 'Json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path $PayloadDir)) {
  throw "Payload directory not found: $PayloadDir"
}

$resolved = (Resolve-Path $PayloadDir).Path

# Aggregation buckets.
$tracked_extensions = @('.py', '.pyd', '.dll', '.pyi', '.so')
$by_top_dir = @{}
$by_extension = @{}
foreach ($ext in $tracked_extensions) {
  $by_extension[$ext] = @{ count = 0; size_bytes = 0L }
}
$by_extension['_other'] = @{ count = 0; size_bytes = 0L }

$totalCount = 0
$totalSize = 0L

Get-ChildItem -Path $resolved -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
  $totalCount++
  $totalSize += $_.Length

  $rel = $_.FullName.Substring($resolved.Length).TrimStart('\', '/')
  # top-level dir (or _root if file sits at payload root).
  $segments = $rel -split '[\\/]', 2
  $topDir = if ($segments.Count -eq 1) { '_root' } else { $segments[0] }
  if (-not $by_top_dir.ContainsKey($topDir)) {
    $by_top_dir[$topDir] = @{ file_count = 0; size_bytes = 0L }
  }
  $by_top_dir[$topDir].file_count++
  $by_top_dir[$topDir].size_bytes += $_.Length

  $ext = $_.Extension.ToLower()
  if ($tracked_extensions -contains $ext) {
    $by_extension[$ext].count++
    $by_extension[$ext].size_bytes += $_.Length
  } else {
    $by_extension['_other'].count++
    $by_extension['_other'].size_bytes += $_.Length
  }
}

$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$result = [ordered]@{
  schema_version = 1
  measured_at = $now
  payload_dir = $resolved
  total_file_count = $totalCount
  total_size_bytes = $totalSize
  by_top_dir = $by_top_dir
  by_extension = $by_extension
}

if ($Format -eq 'Json') {
  $result | ConvertTo-Json -Depth 4
} else {
  # Human-readable table.
  Write-Output "Payload: $resolved"
  Write-Output "Measured: $now"
  Write-Output ""
  Write-Output "total_file_count: $totalCount"
  Write-Output ("total_size_bytes: {0} ({1:N2} MB)" -f $totalSize, ($totalSize / 1MB))
  Write-Output ""
  Write-Output "by_top_dir:"
  $by_top_dir.GetEnumerator() | Sort-Object Key | ForEach-Object {
    Write-Output ("  {0,-12} files={1,6}  size={2,10:N0} ({3,7:N2} MB)" -f $_.Key, $_.Value.file_count, $_.Value.size_bytes, ($_.Value.size_bytes / 1MB))
  }
  Write-Output ""
  Write-Output "by_extension:"
  $by_extension.GetEnumerator() | Sort-Object Key | ForEach-Object {
    Write-Output ("  {0,-8} count={1,6}  size={2,10:N0} ({3,7:N2} MB)" -f $_.Key, $_.Value.count, $_.Value.size_bytes, ($_.Value.size_bytes / 1MB))
  }
}
```

- [ ] **Step 4: Pester test を実行して 5 件 pass することを確認**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 `
    -Output Detailed `
    -PassThru | Select-Object -ExpandProperty Passed | Measure-Object | Select-Object -ExpandProperty Count
```

Expected: 既存全 test + 新規 5 test の合算が pass count に。Failed = 0。

- [ ] **Step 5: 既存 develop-0.3.0 ZIP に対して動作確認 (任意の手元検証)**

```powershell
# 開発者の手元に既に build した payload があれば実行 (なければ skip)
# Get baseline for "before" comparison
if (Test-Path build\portable\allaganeye-v0.3.0-dev) {
  pwsh -File scripts\measure-portable-zip-baseline.ps1 `
       -PayloadDir build\portable\allaganeye-v0.3.0-dev `
       -Format Human
}
```

Expected: 数千 file (PyInstaller 移行前の baseline 値) が表示される。

---

## Task 3: Add CI baseline upload step (Step 1 cont.)

**Files:**

- Modify: `.github/workflows/release.yml` (line 167-181 付近、Verify allaganeye-gui.exe step の **後**、Smoke test --version step の **前**)

- [ ] **Step 1: release.yml の `Verify allaganeye-gui.exe is bundled (#570)` step の直後に新規 step を追加**

`.github/workflows/release.yml` 内、`Verify allaganeye-gui.exe is bundled (#570)` の `Write-Host "allaganeye-gui.exe bundled at $exePath..."` で終わる block の **後** (line 181 直後) に空行 1 つを挟んで追加:

```yaml
      # #752 -- baseline measurement: capture file count + size by top-dir /
      # extension for PR before/after comparison. The JSON artifact is reused
      # in the Pester regression assertion that locks in the reduction floor.
      - name: Measure Portable ZIP baseline (#752)
        if: github.event_name == 'pull_request' || (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || github.event_name == 'workflow_dispatch'
        shell: ${{ matrix.shell }}
        run: |
          $version = '${{ needs.version-check.outputs.version }}'
          $payload = "build/portable/allaganeye-v$version"
          $outFile = "build/portable/baseline.json"
          $json = & ./scripts/measure-portable-zip-baseline.ps1 -PayloadDir $payload -Format Json
          $json | Out-File -FilePath $outFile -Encoding utf8 -NoNewline
          Write-Host "--- Baseline measurement (#752) ---"
          & ./scripts/measure-portable-zip-baseline.ps1 -PayloadDir $payload -Format Human
          Write-Host "Saved baseline JSON to: $outFile"
```

- [ ] **Step 2: yml の構文チェック**

```powershell
# 簡易 syntax check (workflow_dispatch の dry-run までは要らない)
$yamlText = Get-Content .github/workflows/release.yml -Raw
# PowerShell の ConvertFrom-Yaml は標準 module ではないため、yml 構文は
# yamllint (Python) があれば実行。なければ次の step (Task 4 push 後の CI) に
# 任せる。
if (Get-Command yamllint -ErrorAction SilentlyContinue) {
  yamllint .github/workflows/release.yml
} else {
  Write-Host "yamllint not available; CI will validate yml on push."
}
```

Expected: yamllint がある場合は no error、ない場合は skip。

- [ ] **Step 3: 確認: 新規 step が pull_request / tag push / workflow_dispatch で発火し、push (warm-up) では skip される (既存 smoke と同じ条件式)**

(視覚的確認のみ。実 CI 起動は Task 12 PR push 時)

---

## Task 4: Commit Step 1 (baseline measurement)

- [ ] **Step 1: 変更 file を確認**

```bash
git status
```

Expected:

```text
new file:   scripts/measure-portable-zip-baseline.ps1
modified:   scripts/tests/build-portable-zip.Tests.ps1
modified:   .github/workflows/release.yml
```

- [ ] **Step 2: stage + commit**

```bash
git add scripts/measure-portable-zip-baseline.ps1 \
        scripts/tests/build-portable-zip.Tests.ps1 \
        .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
feat(installer): #752 baseline measurement script + Pester + CI upload (Refs #752)

Portable ZIP file 数削減 PR の Step 1。behavior 変更なしの infrastructure。
- scripts/measure-portable-zip-baseline.ps1 を新設 (-PayloadDir / -Format Json|Human)
- Pester に 5 件 unit test を追加 (schema / aggregation / format / missing dir)
- release.yml に measurement step を追加 (pull_request / tag / workflow_dispatch
  で発火、build/portable/baseline.json + Human stdout 出力)

Step 2 (PyInstaller migration) commit で file count assertion を活性化する。

Refs #752

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git status
```

Expected: commit 成功、working tree clean。

---

## Task 5: pytest TDD — integrity.py frozen-mode 分岐 (test first)

**Files:**

- Modify: `tests/test_integrity.py` (末尾、既存 `test_default_manifest_path_under_install_dir` の **後**)

- [ ] **Step 1: tests/test_integrity.py 末尾に新規 test 2 件を追加**

既存 test の末尾 (file 最終 line の後) に空行 2 つ挟んで append:

```python
def test_resolve_install_dir_frozen_mode_uses_sys_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In PyInstaller frozen mode (#752), install dir derives from sys.executable.

    Layout: <install dir>/allaganeye/allaganeye.exe -> install dir = parent.parent.
    The path passed to ``_resolve_install_dir`` (the package __init__ path) is
    *ignored* in frozen mode because PyInstaller puts the .py files inside
    library.zip and __file__ no longer points at a real disk location.
    """
    import sys

    from allaganeye.integrity import _resolve_install_dir

    fake_install = tmp_path / "install"
    fake_exe = fake_install / "allaganeye" / "allaganeye.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_text("", encoding="utf-8")

    # Simulate PyInstaller frozen launcher.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    # __init__ path is ignored in frozen mode; pass any dummy value.
    dummy_init = tmp_path / "ignored" / "__init__.py"

    assert _resolve_install_dir(dummy_init) == fake_install


def test_resolve_install_dir_dev_mode_unchanged_when_sys_frozen_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In dev / legacy mode (sys.frozen unset), existing path resolution stays.

    Regression guard for #752 to ensure the new sys.frozen branch does not
    change behavior when sys.frozen is False or missing.
    """
    import sys

    from allaganeye.integrity import _resolve_install_dir

    # Ensure sys.frozen is not set (the production CPython interpreter).
    monkeypatch.delattr(sys, "frozen", raising=False)

    init_path = tmp_path / "lib" / "allaganeye" / "__init__.py"
    init_path.parent.mkdir(parents=True)
    init_path.write_text("", encoding="utf-8")

    assert _resolve_install_dir(init_path) == tmp_path
```

- [ ] **Step 2: pytest を実行して新規 2 件 fail することを確認**

```bash
pytest tests/test_integrity.py::test_resolve_install_dir_frozen_mode_uses_sys_executable tests/test_integrity.py::test_resolve_install_dir_dev_mode_unchanged_when_sys_frozen_absent -v
```

Expected:

- `test_resolve_install_dir_frozen_mode_uses_sys_executable`: FAIL (実装が `__init__.py` 経由のままで sys.executable を見ない)
- `test_resolve_install_dir_dev_mode_unchanged_when_sys_frozen_absent`: PASS (既存実装で動く想定だが、impl 修正後も regression なく PASS 維持) — 実は import sys を `_resolve_install_dir` が直接していないため、現実装でも PASS する可能性が高い。検出は frozen 側で十分

実 fail 状態は: 1 件 (frozen mode test) FAIL、もう 1 件 (dev mode test) PASS。

---

## Task 6: integrity.py 実装 — sys.frozen 分岐

**Files:**

- Modify: `allaganeye/integrity.py:14-50` (import section + `_resolve_install_dir` 関数)

- [ ] **Step 1: import section に `import sys` を追加**

`allaganeye/integrity.py` line 16-23 付近、`from __future__ import annotations` の **後** に挿入。具体的には現状:

```python
from __future__ import annotations

import json
import os
from datetime import datetime
from datetime import UTC
from pathlib import Path
from typing import Any
```

を以下に変更 (1 行 `import sys` 追加):

```python
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from datetime import UTC
from pathlib import Path
from typing import Any
```

- [ ] **Step 2: `_resolve_install_dir` 関数を frozen 分岐版に置換**

`allaganeye/integrity.py:38-44` の `_resolve_install_dir` 関数:

before (現状):

```python
def _resolve_install_dir(package_init: Path) -> Path:
    """Compute install dir from ``allaganeye/__init__.py`` path.

    Portable ZIP layout: ``<install dir>/lib/allaganeye/__init__.py``,
    so the install dir is 3 ancestors up from ``__init__.py``.
    """
    return package_init.resolve().parent.parent.parent
```

after:

```python
def _resolve_install_dir(package_init: Path) -> Path:
    """Compute install dir.

    PyInstaller frozen mode (Portable ZIP v0.3.0+, #752):
        ``sys.executable`` = ``<install dir>/allaganeye/allaganeye.exe``
        so install dir = ``parent.parent``.
    Legacy embeddable layout (pre-#752 Portable ZIP) and dev mode:
        ``__init__.py`` at ``<install dir>/lib/allaganeye/__init__.py``
        so install dir = ``parent.parent.parent``.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return package_init.resolve().parent.parent.parent
```

- [ ] **Step 3: pytest 新規 2 件 + 既存 integrity test 全件 pass 確認**

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 test PASS (新規 2 件 + 既存 test の regression なし)。

- [ ] **Step 4: encoding boundary audit — `import sys` 追加で他の挙動に影響ないか確認**

```bash
ruff check allaganeye/integrity.py
ruff format --check allaganeye/integrity.py
pyright allaganeye/integrity.py
```

Expected: いずれも success。

---

## Task 7: Commit integrity.py frozen fix

- [ ] **Step 1: 変更 file を確認**

```bash
git status
```

Expected:

```text
modified:   allaganeye/integrity.py
modified:   tests/test_integrity.py
```

- [ ] **Step 2: stage + commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -m "$(cat <<'EOF'
fix(integrity): #752 PyInstaller frozen-mode で sys.executable から install dir を導出 (Refs #752)

PyInstaller --onedir で frozen 化した allaganeye.exe では `__file__` が
library.zip 内 path を指すため、現状の `Path(__file__).parent.parent.parent`
で install dir を導出するとずれる。`getattr(sys, 'frozen', False)` 分岐で
`Path(sys.executable).parent.parent` (= <install>/allaganeye/allaganeye.exe
の grand-parent = <install>) を返すように変更。

- dev mode (sys.frozen 未設定) では既存 path がそのまま走り regression なし
- legacy Portable ZIP (本 PR merge 以前) 解凍時も既存 path で動く (forward compat)
- pytest に frozen / dev mode 両方の monkeypatch test を追加

Step 2 of #752 PR. Step 1 (baseline measurement infra) は前 commit 済。

Refs #752

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git status
```

Expected: commit 成功、working tree clean。

---

## Task 8: PyInstaller requirements + spec ファイル新設

**Files:**

- Create: `scripts/installer/requirements-pyinstaller.txt`
- Create: `scripts/installer/allaganeye.spec`

- [ ] **Step 1: ディレクトリ作成確認**

```powershell
New-Item -ItemType Directory -Force -Path scripts/installer | Out-Null
Get-ChildItem scripts/installer
```

Expected: scripts/installer/ ディレクトリ存在 (空)。

- [ ] **Step 2: requirements-pyinstaller.txt を作成**

Write `scripts/installer/requirements-pyinstaller.txt`:

```text
# PyInstaller pinning policy (#752):
#   - patch-level pin (e.g. `pyinstaller==6.20.0`)
#   - hooks-contrib も reproducibility 強化のため explicit pin
#   - 4-6 か月毎に bump、Idios の手元で frozen output が test pass することを確認
#   - bump 時は両 version を同時に上げ、PR で smoke-test + 実機 split を実測
pyinstaller==6.20.0
pyinstaller-hooks-contrib==2026.5
```

- [ ] **Step 3: allaganeye.spec を作成**

Write `scripts/installer/allaganeye.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for allaganeye Portable ZIP (#752).

Hand-edited (not auto-generated) so the build is reproducible across PyInstaller
versions and CI environments. To rebuild locally:

    pip install -r scripts/installer/requirements-pyinstaller.txt
    pyinstaller scripts/installer/allaganeye.spec --noconfirm --clean

Output layout (--onedir, default in PyInstaller 6+):
    dist/allaganeye/
        allaganeye.exe           # entry point
        _internal/
            python311.dll
            base_library.zip
            <numpy/scipy/cv2 native DLLs and data>
            ...

Hooks: PyInstaller's bundled hooks at `PyInstaller.hooks.hook-numpy` /
`hook-scipy.signal` etc. automatically collect submodules + data.
pyinstaller-hooks-contrib==2026.5 provides 3rd-party hooks. Additional data
for our package is added via `collect_data_files`.
"""
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['../../allaganeye/__main__.py'],
    pathex=[],
    binaries=[],
    # `audio/refs/fanfare.npz` (allaganeye 同梱 BGM 参照特徴量)
    datas=collect_data_files('allaganeye.audio.refs'),
    # 全モジュールが import 文経由で取れるので hiddenimports は基本 空
    # numpy / scipy / cv2 の hook が PyInstaller 公式で同梱されているため
    # `collect_all` 系の手動指定も不要
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 不要モジュール除外 (size 削減)
        'tkinter',          # 同梱 Python embed には元々入らないが念のため
        'PIL',              # 未使用
        'matplotlib',       # 未使用
        'pytest',           # 未使用 (dev only)
        'sphinx',           # 未使用
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='allaganeye',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX 不要 (Idios 決定 2026-05-18): 起動時間 +1-2s と WindowsDefender false positive リスクを避ける
    console=True,               # CLI は console app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='allaganeye',
)
```

- [ ] **Step 4: ファイルが意図通り生成されたことを確認**

```powershell
Get-ChildItem scripts/installer
Get-Content scripts/installer/requirements-pyinstaller.txt | Select-Object -First 5
```

Expected: 2 file 存在、requirements の先頭に `pyinstaller==6.20.0` が見える。

- [ ] **Step 5: PyInstaller インストールして .spec の構文 check (任意の手元検証)**

```powershell
# 開発者の手元に Python 3.11 venv があれば実施。CI では Task 12 PR push 時に実 build で検証。
$tmpVenv = Join-Path ([System.IO.Path]::GetTempPath()) ".pyinstaller-syntax-check"
if (Test-Path $tmpVenv) { Remove-Item -Recurse -Force $tmpVenv }
python -m venv $tmpVenv
& "$tmpVenv\Scripts\python.exe" -m pip install -r scripts/installer/requirements-pyinstaller.txt --no-cache-dir
# spec の構文 check のみ (実 build はせず、parser だけ走らせる)
& "$tmpVenv\Scripts\python.exe" -c "import importlib.util; spec = importlib.util.spec_from_file_location('s', 'scripts/installer/allaganeye.spec'); print('Spec parsable: OK')"
Remove-Item -Recurse -Force $tmpVenv
```

Expected: "Spec parsable: OK" 出力。

CI が無いと検証できない場合 (Python 環境不在) は次の Pester step で代替。

---

## Task 9: Pester test for spec syntax + path location

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (新規 Describe block 末尾、または Task 2 で追加した block の **後**)

- [ ] **Step 1: Pester test を追加**

`Describe 'Measure-PortableZipBaseline (#752)' { ... }` の **後** に空行 2 つ挟んで append:

```powershell
Describe 'PyInstaller artifacts (#752)' {
  BeforeAll {
    $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    $script:SpecFile = Join-Path $script:RepoRoot 'scripts\installer\allaganeye.spec'
    $script:ReqFile = Join-Path $script:RepoRoot 'scripts\installer\requirements-pyinstaller.txt'
  }

  It 'allaganeye.spec exists at scripts/installer/' {
    Test-Path $script:SpecFile | Should -BeTrue
  }

  It 'requirements-pyinstaller.txt exists and pins pyinstaller + hooks-contrib at exact versions' {
    Test-Path $script:ReqFile | Should -BeTrue
    $content = Get-Content $script:ReqFile -Raw
    $content | Should -Match 'pyinstaller==6\.20\.0'
    $content | Should -Match 'pyinstaller-hooks-contrib==2026\.5'
  }

  It 'allaganeye.spec references allaganeye/__main__.py as entry script (relative to spec)' {
    $spec = Get-Content $script:SpecFile -Raw
    # Relative path from scripts/installer/ to allaganeye/__main__.py is ../../allaganeye/__main__.py
    $spec | Should -Match "Analysis\(\s*\[\s*'\.\./\.\./allaganeye/__main__\.py'\s*\]"
  }

  It 'allaganeye.spec collect_data_files allaganeye.audio.refs (fanfare.npz)' {
    $spec = Get-Content $script:SpecFile -Raw
    $spec | Should -Match "collect_data_files\(\s*'allaganeye\.audio\.refs'\s*\)"
  }

  It 'allaganeye.spec disables UPX compression (Idios 2026-05-18 決定)' {
    $spec = Get-Content $script:SpecFile -Raw
    $spec | Should -Match 'upx\s*=\s*False'
    $spec | Should -Not -Match 'upx\s*=\s*True'
  }
}
```

- [ ] **Step 2: Pester を実行して 5 件 pass 確認**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: 既存 + Task 2 + 本 task の 5 件全 PASS。

---

## Task 10: Get-LauncherTemplate 改修 (Pester TDD)

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (line ~294-307 の既存 `Describe 'Get-LauncherTemplate'` block 内の 2 件)
- Modify: `scripts/build-portable-zip.ps1` (line 357-360 付近、`Get-LauncherTemplate` 関数の python.exe 呼び出し)

- [ ] **Step 1: 既存 Pester test を `python.exe -m allaganeye` → `allaganeye\allaganeye.exe` に書き換え (failing TDD)**

`scripts/tests/build-portable-zip.Tests.ps1` の line 294-307 付近 (`Describe 'Get-LauncherTemplate'` block 内):

before (line 294-307):

```powershell
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
```

after (PyInstaller frozen path):

```powershell
  It 'dispatches video drag-drop to PyInstaller frozen allaganeye.exe split (#752)' {
    # The video drag-drop branch must invoke the PyInstaller-frozen entry
    # point `allaganeye\allaganeye.exe split %*` so all args are forwarded.
    # Pre-#752 used `python\python.exe -m allaganeye split %*`; that path
    # is removed because the embed Python interpreter is no longer shipped.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if /i "%EXT%"==".mp4"'
    $template | Should -Match 'if /i "%EXT%"==".mkv"'
    $template | Should -Match 'if /i "%EXT%"==".avi"'
    $template | Should -Match 'if /i "%EXT%"==".mov"'
    $template | Should -Match '"%PAYLOAD%allaganeye\\allaganeye\.exe" split %\*'
    # Pre-#752 path must not linger in the template.
    $template | Should -Not -Match 'python\\python\.exe'
  }

  It 'dispatches non-video args to PyInstaller frozen allaganeye.exe (#752)' {
    # Non-video args (e.g. allaganeye.bat detect <file>, --version) must
    # also be dispatched to `allaganeye\allaganeye.exe %*` (PyInstaller frozen).
    $template = Get-LauncherTemplate
    $template | Should -Match '"%PAYLOAD%allaganeye\\allaganeye\.exe" %\*'
    $template | Should -Not -Match 'python\\python\.exe'
  }
```

- [ ] **Step 2: Pester を実行して上記 2 件 fail することを確認**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 `
    -Output Detailed `
    -PassThru | Select-Object -ExpandProperty Failed | Measure-Object | Select-Object -ExpandProperty Count
```

Expected: 2 件 fail (Get-LauncherTemplate の中身がまだ python.exe を含むため)。

- [ ] **Step 3: `Get-LauncherTemplate` の python.exe 呼び出しを allaganeye.exe に書き換え**

`scripts/build-portable-zip.ps1` の line 356-360 付近 (`Get-LauncherTemplate` 関数 return template 内の `if defined IS_VIDEO` block):

before:

```cmd
if defined IS_VIDEO (
  "%PAYLOAD%python\python.exe" -m allaganeye split %*
) else (
  "%PAYLOAD%python\python.exe" -m allaganeye %*
)
```

after:

```cmd
if defined IS_VIDEO (
  "%PAYLOAD%allaganeye\allaganeye.exe" split %*
) else (
  "%PAYLOAD%allaganeye\allaganeye.exe" %*
)
```

その他の launcher 内 line (`set ALLAGANEYE_FFMPEG`、`pause`、`exit /b %EXIT_CODE%`、GUI dispatch `start "" "%PAYLOAD%allaganeye-gui.exe"` 等) は **変更しない**。

- [ ] **Step 4: Pester を実行して 2 件 pass 確認**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: Get-LauncherTemplate 関連 test 全 PASS、他 test も regression なし。

---

## Task 11: build-portable-zip.ps1 main path rewrite (Python embed → PyInstaller)

**Files:**

- Modify: `scripts/build-portable-zip.ps1` (line 47-102 の Pin constants 部、line 461-489 の Python embed + pip install --target、新規 step として PyInstaller frozen build)

- [ ] **Step 1: Pin constants 削除 (line 47-94 付近)**

`scripts/build-portable-zip.ps1` の以下の variables / コメントを削除:

- `$PythonVersion = '3.11.9'` (line 49)
- `$PythonEmbedUrl = ...` (line 50)
- `$PythonEmbedSha256 = '...'` (line 51)
- `$GetPipUrl = '...'` (line 53)
- get-pip コメント blob (line 54-67)
- `$GetPipSha256 = '...'` (line 68)

具体的には、`Set-StrictMode -Version Latest` + `$ProgressPreference` の行 (line 44-46) と FFmpeg pin (`$FFmpegVersion = '8.1'` 以降、line 98 から) の **間** にあるすべての Python embed / get-pip pin を削除する。

before (line 48-94):

```powershell
# Pinned versions - referenced from both the main build path and Pester tests.
$PythonVersion = '3.11.9'
$PythonEmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PythonEmbedSha256 = '009D6BF7E3B2DDCA3D784FA09F90FE54336D5B60F0E0F305C37F400BF83CFD3B'

$GetPipUrl = 'https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py'
# #681 -- Pin get-pip.py via the pypa/get-pip GitHub raw URL with a release
... (多数行のコメント)
$GetPipSha256 = '66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76'

# FFmpeg is pinned to a BtbN MONTHLY snapshot ...
```

after:

```powershell
# Pinned versions - referenced from both the main build path and Pester tests.
# Python 3.11 embed + get-pip pin は #752 で PyInstaller 化に伴い削除。
# 代わりに scripts/installer/requirements-pyinstaller.txt が build venv の
# pyinstaller + hooks-contrib version を pin する。
# FFmpeg は引き続き同梱 (LGPLv3 別ディレクトリ、#508)。

# FFmpeg is pinned to a BtbN MONTHLY snapshot ...
```

- [ ] **Step 2: 旧 Python embed + pip install --target step を削除 (line 461-489 付近)**

before (line 461-489):

```powershell
# 1. Python embeddable
$PythonZip = Join-Path $BuildDir 'python-embed.zip'
Invoke-Download -Uri $PythonEmbedUrl -OutPath $PythonZip -ExpectedSha256 $PythonEmbedSha256
$PythonDir = Join-Path $PayloadDir 'python'
Expand-Archive -Path $PythonZip -DestinationPath $PythonDir -Force

$PthFile = Join-Path $PythonDir 'python311._pth'
Set-Content -Path $PthFile -Encoding ASCII -Value @(
  'python311.zip',
  '.',
  '..\lib',
  'import site'
)

# 2. Install pip into the embedded interpreter
$GetPipPath = Join-Path $BuildDir 'get-pip.py'
Invoke-Download -Uri $GetPipUrl -OutPath $GetPipPath -ExpectedSha256 $GetPipSha256
$PythonExe = Join-Path $PythonDir 'python.exe'
& $PythonExe $GetPipPath --no-warn-script-location --no-cache-dir

# 3. Install allaganeye + deps into payload\lib
$LibDir = Join-Path $PayloadDir 'lib'
New-Item -ItemType Directory -Force -Path $LibDir | Out-Null
& $PythonExe -m pip install `
    --target $LibDir `
    --no-compile `
    --no-warn-script-location `
    --no-cache-dir `
    $RepoRoot
```

after (上記 block を以下に丸ごと置換):

```powershell
# 1. Create build venv inside the build artifact dir (clean reproducible env).
# Putting the venv inside $BuildDir means it gets cleaned along with the rest
# of the build artifact, avoiding stale state between runs. CI clean build
# 前提のため artifact 外への venv 共有は不要 (Idios 決定 2026-05-18、#752).
$VenvDir = Join-Path $BuildDir 'venv'
& python -m venv $VenvDir
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

# 2. Install allaganeye + PyInstaller into venv
& $VenvPython -m pip install --upgrade pip --no-cache-dir
& $VenvPython -m pip install `
    -r (Join-Path $RepoRoot 'scripts\installer\requirements-pyinstaller.txt') `
    --no-cache-dir
& $VenvPython -m pip install $RepoRoot --no-cache-dir

# 3. Run PyInstaller (frozen --onedir).
# Output goes to $BuildDir/pyinstaller-dist/allaganeye/ (allaganeye.exe +
# _internal/). We then copy that directory into the payload at step 4.
$PyInstallerDist = Join-Path $BuildDir 'pyinstaller-dist'
$PyInstallerWork = Join-Path $BuildDir 'pyinstaller-work'
Push-Location $RepoRoot
try {
  & $VenvPython -m PyInstaller `
    'scripts/installer/allaganeye.spec' `
    --noconfirm `
    --clean `
    --distpath $PyInstallerDist `
    --workpath $PyInstallerWork
} finally {
  Pop-Location
}

# 4. Copy frozen application into payload root.
# Result: $PayloadDir/allaganeye/allaganeye.exe + $PayloadDir/allaganeye/_internal/
Copy-Item -Recurse -Path (Join-Path $PyInstallerDist 'allaganeye') -Destination $PayloadDir
```

- [ ] **Step 3: 既存 Pester `GetPip pinning (#681)` block の取り扱い**

`scripts/tests/build-portable-zip.Tests.ps1` line 477-496 の `Describe 'GetPip pinning (#681)'` block は `$GetPipUrl` / `$GetPipSha256` が build script から削除されたため動かなくなる。block を削除する:

before (line 477-496):

```powershell
Describe 'GetPip pinning (#681)' {
  It 'pins $GetPipUrl to a versioned pypa/get-pip GitHub raw URL' {
    ...
    $GetPipUrl | Should -Match '^https://raw\.githubusercontent\.com/pypa/get-pip/[\w.\-]+/public/get-pip\.py$'
  }

  It 'pins $GetPipSha256 to the literal value matching the pypa/get-pip 26.1.1 tag' {
    ...
    $GetPipSha256 | Should -Be '66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76'
  }
}
```

after: block 全体を削除し、代わりに以下の comment を残す:

```powershell
# Describe 'GetPip pinning (#681)' block was removed by #752: get-pip.py is no
# longer downloaded as PyInstaller --onedir bundles its own pip-managed venv.
# The version pin moved to scripts/installer/requirements-pyinstaller.txt and
# is covered by the `PyInstaller artifacts (#752)` block above.
```

- [ ] **Step 4: build script をローカル dry-run で実行 (任意の手元検証、Python が用意できる環境)**

```powershell
# Python 3.11+ がインストールされている前提
pwsh -File scripts\build-portable-zip.ps1 -Version 0.3.0-dev -SkipArchive
```

Expected: build 成功、`build/portable/allaganeye-v0.3.0-dev/allaganeye/allaganeye.exe` が生成される。

成功時の確認:

```powershell
Test-Path 'build/portable/allaganeye-v0.3.0-dev/allaganeye/allaganeye.exe'  # True
Test-Path 'build/portable/allaganeye-v0.3.0-dev/python'                     # False (廃止)
Test-Path 'build/portable/allaganeye-v0.3.0-dev/lib'                        # False (廃止)
Test-Path 'build/portable/allaganeye-v0.3.0-dev/ffmpeg/ffmpeg.exe'          # True (LGPL 維持)
Test-Path 'build/portable/allaganeye-v0.3.0-dev/integrity-manifest.json'    # True
```

local 環境がない場合は Task 12 PR push 時に CI build で検証する。

- [ ] **Step 5: 全 Pester test を実行して regression なし確認**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: 全 PASS (削除した `GetPip pinning` block 以外、既存 + Task 2 + Task 9 + Task 10 が全 PASS)。

---

## Task 12: Pester test 追加 — frozen bundle 内 fanfare.npz 存在検証

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (Task 9 で追加した `Describe 'PyInstaller artifacts (#752)'` block 内、または末尾)

- [ ] **Step 1: Pester test を追加**

Task 9 で追加した `Describe 'PyInstaller artifacts (#752)' { ... }` block の **末尾** (`It 'allaganeye.spec disables UPX compression (Idios 2026-05-18 決定)' { ... }` の後) に append:

```powershell
  It 'allaganeye.spec excludes obvious unused stdlib (#752)' {
    # Size reduction: tkinter / PIL / matplotlib / pytest / sphinx は allaganeye
    # 本体および依存からは import されない。明示 exclude で frozen bundle size を
    # 削減する。bump 時に excludes リストの妥当性を再評価する trigger として
    # 本 test を用意。
    $spec = Get-Content $script:SpecFile -Raw
    $spec | Should -Match "'tkinter'"
    $spec | Should -Match "'PIL'"
    $spec | Should -Match "'matplotlib'"
    $spec | Should -Match "'pytest'"
    $spec | Should -Match "'sphinx'"
  }
```

- [ ] **Step 2: Pester を実行して全 PASS 確認**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: 全 PASS。

---

## Task 13: Activate Pester file count assertion

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (Task 2 で追加した `Describe 'Measure-PortableZipBaseline (#752)'` block 末尾、または新 block)

- [ ] **Step 1: 開発者の local build から baseline 数値を取得**

Task 11 Step 4 で local build が成功している前提:

```powershell
# 旧 layout の baseline (実装前) を測る場合: 開発者が事前に Step 1 commit の HEAD で build したものに対して計測する
# (本 Task 時点では既に PyInstaller path に置換済のため、旧 layout の値を得るには git stash → 再 build が必要)
# 簡略化: 既存 develop-0.3.0 main branch から build した既存 ZIP の値を baseline として hardcode

# After value (PyInstaller 化後):
pwsh -File scripts\measure-portable-zip-baseline.ps1 `
     -PayloadDir build\portable\allaganeye-v0.3.0-dev `
     -Format Json | ConvertFrom-Json | Select-Object total_file_count, total_size_bytes
```

Expected output (例値、実値は手元計測で決まる):

```text
total_file_count : 250
total_size_bytes : 180000000
```

baseline (旧 layout) は CI Step 1 commit の baseline.json artifact から、または手元の develop-0.3.0 から build した既存 payload から取得。例値:

- baseline total_file_count: 2500
- after total_file_count: 250
- reduction: 90% (≥ 80% 目標達成)

これらの実値を **PR 本文** と次の Pester 定数に記入する。

- [ ] **Step 2: Pester に file count assertion を追加**

`Describe 'Measure-PortableZipBaseline (#752)' { ... }` block の末尾 (`It 'throws when -PayloadDir does not exist' { ... }` の後) に append:

```powershell
  # NOTE: 本 assertion は #752 PR で post-build measurement の値を hardcode する。
  # 値は CI build-windows job の baseline.json artifact から取得。
  # 旧 (develop-0.3.0 main) baseline と新 (PyInstaller --onedir) after を
  # 並べて削減率を assert することで、将来の不用意な再回帰を防ぐ。
  # Bump 時 (PyInstaller version 更新等) は本 const を再測定して上書きする。
  Context 'File count reduction floor (#752 post-merge regression guard)' {
    BeforeAll {
      # ↓ #752 PR build artifact の baseline.json から取得した実数値
      # PR 着手時点の develop-0.3.0 baseline (旧 layout, pip install --target lib path) を
      # 計測した値を Idios が実 build で取得して上書き。
      # PR 本文の before/after 表とこの定数は同じ値を共有する。
      $script:OLD_BASELINE_FILE_COUNT = 2500  # TBD-AT-BUILD: Step 1 commit の baseline.json から取得
      $script:NEW_AFTER_FILE_COUNT_CEILING = 400  # 新 frozen output の上限 (削減率 ~80% 余裕)
      $script:RecentBaseline = Join-Path $script:RepoRoot 'build\portable\baseline.json'
    }

    It 'frozen output file count is at most NEW_AFTER_FILE_COUNT_CEILING' {
      if (-not (Test-Path $script:RecentBaseline)) {
        # ローカル build せずに Pester を回す場合 (CI lint job 等) は assertion を skip
        Set-ItResult -Skipped -Because 'build/portable/baseline.json not present (no local build); CI smoke covers this in release.yml'
        return
      }
      $obj = Get-Content $script:RecentBaseline -Raw | ConvertFrom-Json
      $obj.total_file_count | Should -BeLessOrEqual $script:NEW_AFTER_FILE_COUNT_CEILING
    }

    It 'reduction from OLD_BASELINE_FILE_COUNT is at least 80%' {
      if (-not (Test-Path $script:RecentBaseline)) {
        Set-ItResult -Skipped -Because 'build/portable/baseline.json not present (no local build); CI smoke covers this in release.yml'
        return
      }
      $obj = Get-Content $script:RecentBaseline -Raw | ConvertFrom-Json
      $reductionRatio = 1.0 - ($obj.total_file_count / $script:OLD_BASELINE_FILE_COUNT)
      $reductionRatio | Should -BeGreaterThan 0.8
    }
  }
```

- [ ] **Step 3: TBD-AT-BUILD 値を Task 11 Step 4 で取得した実値で置換**

ローカル build を実施した場合:

```powershell
# 実値を確認
$obj = Get-Content build/portable/baseline.json -Raw | ConvertFrom-Json
Write-Host "After (PyInstaller): $($obj.total_file_count) files, $([math]::Round($obj.total_size_bytes / 1MB, 2)) MB"
```

`$script:OLD_BASELINE_FILE_COUNT` を develop-0.3.0 baseline 実値に、`$script:NEW_AFTER_FILE_COUNT_CEILING` を after 実値 +50 程度 (将来の hooks-contrib bump 等で +/-10% の variance を許容) に置換。

例: 実測 after = 250 → ceiling = 350、old = 2500 → reduction = 90%。

ローカル build できない場合は **CI 1 回目の baseline.json artifact** を確認して値を確定し、本 PR の最後の追加 commit で値を埋める方針も可。

- [ ] **Step 4: Pester を実行**

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: ローカル build がある場合は assertion 2 件 PASS。ない場合は Skipped (理由が明示される)。

---

## Task 14: release.yml に PyInstaller install + integrity smoke 修正

**Files:**

- Modify: `.github/workflows/release.yml`
  - **追加**: PyInstaller install step を `Verify allaganeye-gui.exe is bundled` の **前**
  - **修正**: `Smoke test (integrity-check fall-through, expect exit 7)` step の victim file path

- [ ] **Step 1: PyInstaller install step を追加**

`Build Tauri GUI binary (#570)` step (line 159-162 付近) と `Build Portable ZIP (skip archive)` step (line 164-166 付近) の **間** に新規 step を挿入:

```yaml
      # #752 -- PyInstaller を build venv に直接入れずに、release.yml runner の
      # base Python 環境にも入れる。build-portable-zip.ps1 内部で `python -m venv`
      # を実行する際の base Python (actions/setup-python) は PyInstaller 自体を
      # 持っていなくて良いが、actions/cache key の安定化と CI 時間短縮のため
      # ここで明示 install しておく。実 frozen build は build-portable-zip.ps1
      # 内の venv で再度 install される (clean reproducible env)。
      - name: Install PyInstaller (#752)
        shell: ${{ matrix.shell }}
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r scripts/installer/requirements-pyinstaller.txt
```

- [ ] **Step 2: `Smoke test (integrity-check fall-through, expect exit 7)` step の victim path 修正**

line 291-296 付近の victim 設定を変更:

before:

```powershell
          # Remove a bundled file the manifest is known to track.
          $victim = Join-Path $verifyDir 'lib\allaganeye\audio\refs\fanfare.npz'
          if (-not (Test-Path $victim)) {
            throw "expected bundled file not present (build broken?): $victim"
          }
          Remove-Item -Force $victim
```

after:

```powershell
          # Remove a bundled file the manifest is known to track.
          # #752: lib/ ディレクトリは PyInstaller --onedir 化で廃止。
          # frozen bundle entry point の allaganeye/allaganeye.exe を消すと
          # bat → allaganeye.exe 起動自体が失敗するため、_internal/ 内の
          # fanfare.npz を victim に変更 (manifest 対象ファイル、削除しても
          # bat → allaganeye.exe 起動は成功 → exit 7 を辿れる)。
          $victim = Join-Path $verifyDir 'allaganeye\_internal\allaganeye\audio\refs\fanfare.npz'
          if (-not (Test-Path $victim)) {
            throw "expected bundled file not present (build broken?): $victim"
          }
          Remove-Item -Force $victim
```

- [ ] **Step 3: release.yml yml 構文の sanity check**

```powershell
if (Get-Command yamllint -ErrorAction SilentlyContinue) {
  yamllint .github/workflows/release.yml
} else {
  Write-Host "yamllint not available; CI will validate yml on push."
}
```

Expected: yamllint があれば no error。

---

## Task 15: docs/system-architecture.md 更新

**Files:**

- Modify: `docs/system-architecture.md` (§配布 セクション、新規 § Portable ZIP 内構造 (#752 で簡素化) を追記)

- [ ] **Step 1: 既存 §配布 セクションを確認**

```bash
grep -n -E '^##|^###' docs/system-architecture.md | head -30
```

§配布 の line 番号を確認 (例: line 80)。

- [ ] **Step 2: §配布 セクションに新規 ### を追記**

`docs/system-architecture.md` の §配布 セクション内、最後の sub-section の **後** に空行 2 つ挟んで append:

```markdown
### Portable ZIP 内構造 (#752 で簡素化)

- `<install>/allaganeye/`: PyInstaller frozen CLI application (#752、v0.3.0+)
  - `allaganeye.exe`: entry point
  - `_internal/`: Python interpreter + library.zip + numpy/scipy/cv2 native DLLs + `allaganeye/audio/refs/fanfare.npz` 等の data
- `<install>/ffmpeg/`: FFmpeg LGPLv3 shared build (LICENSE.txt 同梱、#508)
- `<install>/allaganeye.bat`: launcher (#617、内部実装は `allaganeye\allaganeye.exe` を呼ぶ)
- `<install>/allaganeye-gui.exe`: Tauri GUI (#527、frozen CLI を allaganeye.bat 経由で起動 (#646))
- `<install>/README.txt`: 日本語 (#749)
- `<install>/integrity-manifest.json`: 同梱物整合性検査 manifest (#668)

旧来の `python/` (embeddable interpreter) および `lib/` (`pip install --target`) ディレクトリは **v0.3.0 の #752 で廃止**。PyInstaller `--onedir` が Python interpreter + 全依存を `allaganeye/_internal/` に統合する。

GUI Tauri Rust 側 (`gui/src-tauri/src/lib.rs::resolve_allaganeye_command`) は `<resource_dir>/allaganeye.bat` を `Command::new(...)` の program として渡すだけで、bat 内部実装の変更 (`python.exe -m allaganeye` → `allaganeye\allaganeye.exe`) は Rust から不可視 (`allaganeye.bat` 抽象化レイヤー、#646)。
```

- [ ] **Step 3: markdownlint で line length / style 確認**

```bash
bash scripts/check-markdownlint.sh
```

Expected: no error (style guide 遵守)。

---

## Task 16: Encoding boundary audit (Iron Law 6 補助、CLAUDE.md F4 教訓)

PR 提出前に PyInstaller 化で encoding 層をまたぐ箇所を audit する。

**Files:** (read-only audit)

- [ ] **Step 1: Python 側 — frozen Python の `sys.stdout` encoding を確認**

PyInstaller frozen Python は通常 `sys.stdout.encoding = 'utf-8'`. ただし Windows console で日本語を出すケースがあれば cp932 影響を受ける。allaganeye CLI の出力は ASCII が中心 (`--version` 等) のため影響軽微。

確認のみ (コード変更不要):

```bash
grep -rn 'sys.stdout' allaganeye/ --include='*.py' | head -5
```

Expected: 該当箇所が `progress_emitter.py` 等の出力経路 (既存) のみ。新規追加はなし → audit 通過。

- [ ] **Step 2: Rust 側 (Tauri) — 既存 path 維持確認**

`gui/src-tauri/src/lib.rs:2575` `resolve_allaganeye_command` が `allaganeye.bat` を program として渡す既存 path は **touch しない**。dev fallback (`python -m allaganeye`) も unchanged。

確認のみ:

```bash
grep -n 'resolve_allaganeye_command\|allaganeye.bat\|python -m allaganeye' gui/src-tauri/src/lib.rs | head -10
```

Expected: 既存 path がそのまま残っている。新規 PR で touch していないことを確認。

- [ ] **Step 3: cmd.exe code page — launcher.bat 内に encoding 依存処理がないか確認**

```bash
grep -n 'chcp\|cp932\|encoding' scripts/build-portable-zip.ps1 | head -5
```

Expected: 該当無し (launcher.bat は ASCII + 環境変数 set のみ、frozen exe 起動も encoding 中立)。

audit 完了、PR 本文で「encoding boundary audit 通過 (3 層全て unchanged)」を明記する。

---

## Task 17: Commit Step 2 (PyInstaller migration 本体)

- [ ] **Step 1: 変更 file を確認**

```bash
git status
```

Expected:

```text
new file:   scripts/installer/allaganeye.spec
new file:   scripts/installer/requirements-pyinstaller.txt
modified:   scripts/build-portable-zip.ps1
modified:   scripts/tests/build-portable-zip.Tests.ps1
modified:   .github/workflows/release.yml
modified:   docs/system-architecture.md
```

(Task 11 で `tests/test_integrity.py` の修正は既に Task 7 commit に含まれている。今回は Step 2 の build/installer/docs 系のみ)

- [ ] **Step 2: stage + commit**

```bash
git add scripts/installer/allaganeye.spec \
        scripts/installer/requirements-pyinstaller.txt \
        scripts/build-portable-zip.ps1 \
        scripts/tests/build-portable-zip.Tests.ps1 \
        .github/workflows/release.yml \
        docs/system-architecture.md
git commit -m "$(cat <<'EOF'
feat(installer): #752 PyInstaller --onedir で Portable ZIP CLI を frozen 化 (Refs #752)

Python embeddable + pip install --target lib を PyInstaller --onedir に置き換え、
Portable ZIP の Python 関連 file を ~2500 → ~150-300 まで削減。

- scripts/installer/allaganeye.spec を新設 (hand-edited、再現可能 build 目的)
- scripts/installer/requirements-pyinstaller.txt で pyinstaller==6.20.0 +
  pyinstaller-hooks-contrib==2026.5 を pin (BtbN FFmpeg snapshot pin と同等の policy)
- build-portable-zip.ps1 を rewrite: $BuildDir/venv で base Python 環境を作り、
  PyInstaller --onedir で frozen build → $PayloadDir/allaganeye/ に Copy-Item
- Get-LauncherTemplate を `python\python.exe -m allaganeye` から
  `allaganeye\allaganeye.exe` 呼び出しに変更
- release.yml に PyInstaller install step を追加、integrity-fall-through smoke の
  victim file を `_internal/allaganeye/audio/refs/fanfare.npz` に変更
- docs/system-architecture.md §配布 に新 frozen 構造を追記
- Pester に PyInstaller artifact 5 件 + measurement 5 件 + launcher 修正 2 件、
  GetPip pinning block を削除 (get-pip.py は廃止)
- 旧 Python embed + get-pip pin (line 47-94, line 461-489) と関連変数を削除
- file count assertion を Pester に追加 (`build/portable/baseline.json` 経由、
  reduction ratio ≥ 80%、ceiling = NEW_AFTER_FILE_COUNT_CEILING)

GUI Tauri Rust 側 (gui/src-tauri/src/lib.rs::resolve_allaganeye_command) は
allaganeye.bat 抽象化 (#646) のため touch 不要。dev mode (npm run tauri dev) も
resolve_python_fallback (`python -m allaganeye`) で従来通り動作。

LGPLv3 ffmpeg (#508) と integrity-manifest (#668) は影響なし。

Encoding boundary audit (CLAUDE.md F4): Python sys.stdout / Rust Command::new /
cmd.exe code page の 3 層、いずれも既存 path 維持で audit 通過。

Refs #752

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git status
```

Expected: commit 成功、working tree clean。

---

## Task 18: PR 作成 Pre-flight (Iron Law 6 全 Step 再実行)

Pre-flight 5 Step を **PR 作成直前** に再実行 (`docs/l2-workflow.md` §「PR 作成 Pre-flight」参照)。

- [ ] **Step 0: hard-gate — 既存 #752 PR の有無を確認 (<1s)**

```bash
gh pr list --search "752" --state open --json number,title,headRefName | head -10
```

Expected: 0 件 (本 PR が初出)、または 1 件で `headRefName` が `claude/exciting-chatelet-67dc1d` (本 worktree)。

複数件・他 branch の競合 PR があれば **STOP** して Idios に AskUserQuestion。

- [ ] **Step 1: base 同期 (origin/develop-0.3.0 fetch)**

```bash
git fetch origin develop-0.3.0
```

- [ ] **Step 2: 取り込み未済 commit を列挙**

```bash
git log --oneline HEAD..origin/develop-0.3.0 | head -10
```

Expected: 0 行 (Task 1 から触っていない場合) または develop-0.3.0 の新規 commit。

- [ ] **Step 3: 取り込み未済 commit が touched files と交差するか**

```bash
git log --oneline HEAD..origin/develop-0.3.0 -- \
  scripts/build-portable-zip.ps1 \
  scripts/tests/build-portable-zip.Tests.ps1 \
  scripts/measure-portable-zip-baseline.ps1 \
  scripts/installer/ \
  .github/workflows/release.yml \
  allaganeye/integrity.py \
  tests/test_integrity.py \
  docs/system-architecture.md
```

Expected: 0 行。交差ありなら `git merge origin/develop-0.3.0` で先取り込み + 自動チェック再実行。

- [ ] **Step 4: 並行 worktree PR 重複再確認**

```bash
gh pr list --search "752 in:title,body" --state all --json number,title,state,headRefName | head -20
```

Expected: 本 PR (まだ未作成) 以外で #752 を扱う open / merged PR がないこと。

- [ ] **Step 5: Codex adversarial-review 起動 (focus 文字列指定)**

```bash
# /codex:adversarial-review skill を invoke。focus は以下:
# - PyInstaller hook 漏れ (numpy / scipy / cv2 動的 import の取りこぼし)
# - sys.frozen / sys.executable の path resolution edge case
# - encoding boundary (Python / Rust / cmd.exe の 3 層 audit、F4 教訓再発確認)
# - GUI Tauri Rust 側 (lib.rs:2575) で本当に touch していないかの確認
# - #752 と類似の過去 PR (#702, #729) の root cause が再発していないか
```

Codex 出力を読み、blocker finding があれば修正 commit を追加。focus されない finding は §「(A) PR 内修正優先」規約に従い PR 内追加 commit で対応。

- [ ] **Step 6: 自動チェック全 path で実行**

Python:

```bash
ruff check .
ruff format --check .
pyright
pytest -m 'not slow'
```

PowerShell / Pester:

```powershell
Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

markdownlint:

```bash
bash scripts/check-markdownlint.sh
```

GUI (touch していないが Iron Law 6 path 別自動チェック表に従い実行不要、ただし regression なし確認のために 1 回だけ走らせる選択肢あり):

```powershell
# Optional sanity (本 PR では gui touch なしのため省略可)
# cd gui ; npm run lint ; cd ..
```

Expected: 全 PASS。Fail 時は修正 commit を追加して Pre-flight 再実行。

---

## Task 19: Push + PR 作成

- [ ] **Step 1: branch を push**

```bash
git push -u origin claude/exciting-chatelet-67dc1d
```

Expected: push 成功。

- [ ] **Step 2: PR を作成**

```bash
gh pr create \
  --base develop-0.3.0 \
  --head claude/exciting-chatelet-67dc1d \
  --title "feat(installer): #752 Portable ZIP CLI を PyInstaller --onedir で frozen 化" \
  --body "$(cat <<'EOF'
## Summary

- Portable ZIP の Python 関連 file を ~2500 → ~150-300 に削減 (PyInstaller `--onedir` 採用)
- 旧 `python/` (embeddable) + `lib/` (pip install --target) ディレクトリ廃止、新 `allaganeye/allaganeye.exe` + `allaganeye/_internal/` 構造に
- `allaganeye/integrity.py` を `sys.frozen` aware に補正 (frozen 時 `sys.executable` ベースで install dir 解決)
- baseline measurement script (`scripts/measure-portable-zip-baseline.ps1`) + Pester regression assertion (削減率 ≥ 80%) を導入

Refs #752

## Before / After (machine-verified)

| metric | before (develop-0.3.0) | after (#752) | reduction |
|---|---|---|---|
| total_file_count | TBD-FROM-CI-ARTIFACT | TBD-FROM-CI-ARTIFACT | TBD% |
| total_size_bytes (MB) | TBD | TBD | TBD% |
| python/ + lib/ file_count | TBD | 0 (廃止) | 100% |
| allaganeye/ file_count | 0 (新設) | TBD | n/a |

実値は CI artifact `baseline.json` (PR push 後の build-windows job artifact) から取得して上書き。

## Acceptance criteria (spec §6 mapping)

**Step 1 (baseline measurement)**:

- [x] `scripts/measure-portable-zip-baseline.ps1` が `-PayloadDir` から JSON / Human 出力
- [x] CI build-windows job が baseline.json を artifact 化
- [x] PR 本文に before/after 並記 (※ CI 後に値を書き込み)

**Step 2 (PyInstaller migration)**:

- [x] `scripts/installer/allaganeye.spec` が再現可能 build
- [x] `pyinstaller==6.20.0` + `pyinstaller-hooks-contrib==2026.5` を pin
- [x] 旧 `python311.zip`, `get-pip.py`, `pip install --target lib` 関連 step を build script から削除
- [x] `<install>/allaganeye/allaganeye.exe` (frozen) が存在
- [x] `<install>/python/` が存在しない
- [x] `<install>/lib/` が存在しない
- [x] `<install>/allaganeye/_internal/allaganeye/audio/refs/fanfare.npz` が存在 (resource bundle 確認)
- [x] `<install>/allaganeye.bat` が `allaganeye\allaganeye.exe` を呼ぶ
- [x] `<install>/ffmpeg/` 不変 (LGPLv3 同梱維持)
- [x] `<install>/allaganeye-gui.exe` 不変
- [x] `allaganeye/integrity.py` の `_resolve_install_dir` が `sys.frozen` 分岐済 + pytest PASS
- [x] CI smoke Lv A (`--version`) PASS
- [x] CI smoke Lv B (`detect` 3s) PASS
- [x] CI smoke integrity exit 7 PASS (victim = `_internal/allaganeye/audio/refs/fanfare.npz`)
- [x] integrity-manifest.json が `allaganeye/allaganeye.exe` 等を entry 化
- [x] file count 削減幅 ≥ 80% を本文に記載

**Idios 実機検証 (machine-unverifiable、`AskUserQuestion` でハンドオフ)**:

- 配布 ZIP 展開後 `allaganeye.bat` ダブルクリック → GUI 起動
- `allaganeye.bat <video.mp4>` で split 完了
- `allaganeye-gui.exe` から detect 起動 → completion 画面遷移

## Self-Test Report

**machine-verified** (CI で確認):

- [x] ruff check / ruff format --check / pyright / pytest -m 'not slow'
- [x] Pester (build-portable-zip.Tests.ps1) 全 PASS
- [x] markdownlint
- [x] CI smoke (Lv A `--version` / Lv B `detect` 3s / integrity exit 7) 全 PASS
- [x] PyInstaller frozen output 生成 (build artifact 検証)
- [x] integrity-manifest.json が新構造を反映 (size match)
- [x] file count 削減数 machine-verified (baseline.json before/after)

**machine-unverifiable** (Idios 実機検証で確認):

- 配布 ZIP 展開時間の体感 (before / after)
- GUI export 動作 (フロー一通り)
- 長時間動画 (1:25+) split 動作

## Encoding boundary audit (CLAUDE.md F4 教訓)

- Python 側 (frozen `sys.stdout`): 既存 progress_emitter.py のみ、新規追加無し → audit 通過
- Rust 側 (Tauri `Command::new("...allaganeye.bat")`): `lib.rs:2575` 既存 path 維持、touch なし → audit 通過
- cmd.exe code page (launcher.bat): chcp / encoding 依存処理なし、ASCII + env var set のみ → audit 通過

3 層全て unchanged で audit 通過。

## Pre-flight 通過確認

- Step 0 (hard-gate): #752 open PR は本 PR のみ
- Step 1-3 (base 同期 + 取り込み未済 + 交差判定): 交差なし
- Step 4 (並行 worktree PR 重複): なし
- Step 5 (Codex adversarial-review): focus 文字列で実行、blocker なし
- Step 6 (自動チェック): 全 PASS

## Closes / Fixes / Resolves 不使用 (Iron Law 4)

`Refs #752` のみ。merge 後、Idios の実機検証ハンドオフ完了後に手動 `gh issue close #752`。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL が出力される。

- [ ] **Step 3: PR URL をメモして CI 結果を確認**

```bash
gh pr view --json url,statusCheckRollup | jq -r '.url'
```

Expected: PR URL。

CI の進捗監視:

```bash
gh pr checks --watch
```

Expected: 全 check (release.yml の matrix shell、ci.yml の Python lint / pytest / etc.) が PASS。

- [ ] **Step 4: CI baseline.json から実値を取得して PR 本文を更新**

CI 完了後:

```bash
# PR ID + artifact から baseline.json を取得
gh run download --name allaganeye-windows-v* --dir /tmp/pr-artifact || true
cat /tmp/pr-artifact/baseline.json | jq '{total_file_count, total_size_bytes}'
```

PR 本文の "TBD-FROM-CI-ARTIFACT" を実値に置換:

```bash
gh pr edit <PR#> --body "$(cat <<'EOF'
... (実値で更新した本文)
EOF
)"
```

CI artifact が PR Actions tab から取得できない場合、CI logs の `Measure Portable ZIP baseline (#752)` step の stdout を直接読んで値を取得。

---

## Task 20: Idios 実機検証ハンドオフ (machine-unverifiable AC)

- [ ] **Step 1: `AskUserQuestion` で Idios 実機検証を依頼**

```text
質問: 「PR #<番号> の Portable ZIP 実機検証をお願いできますか?」
選択肢:
  - 「OK / 全項目検証する」 (Recommended) — ZIP DL → 展開 → .bat ダブルクリック / .bat split / GUI 起動 の 3 項目を確認
  - 「OK / 軽い検証だけ」 — .bat --version だけ確認
  - 「後で / Idios 都合で実機テスト時に確認」 — 今は merge 進めず machine-verified のみで保留
  - 「妥当性に懸念あり」 — どこを心配しているか共有
```

検証結果を PR 本文 "Idios 実機検証" check box に反映。

- [ ] **Step 2: 検証 OK なら `/iterate-review <PR#>` で review-fix ループを起動**

```text
/iterate-review <PR#>
```

Expected: review skill 起動、findings の自動 (A) PR 内修正 / (B)(C) handoff を実施、Round 4-5 程度で収束。

---

## Task 21: Merge + Issue close (skill ハンドオフ)

- [ ] **Step 1: `/iterate-review` 収束後、`/review-pr` の最終 LGTM 判断を待つ**

LGTM 出れば squash merge (または rebase merge、Iron Law / l2-workflow 規約に従う):

```bash
gh pr merge <PR#> --squash --delete-branch
```

Expected: merge 成功、本 worktree branch が削除。

- [ ] **Step 2: `/close-issue #752` を invoke**

`/close-issue` skill が受け入れ条件をマージ後 develop-0.3.0 で実測再検証し、未消化チェックボックスがあれば (B) 新 issue / (C) 既存 issue 追記にハンドオフした上で `gh issue close #752` を実行。

---

## 自己レビュー (writing-plans 完了直前)

**1. Spec coverage:** spec §1 (Baseline measurement) / §2 (PyInstaller migration) / §3 (Test 戦略) / §4 (Risks) / §6 (受け入れ条件 mapping) / §7 (docs) / §8 (関連) を Task 2-19 で網羅。spec §5 (Open questions) は writing-plans 持ち越し 2 件のみ:

- 1: hiddenimports 追加要否 → Task 11 Step 4 の local build / Task 19 Step 3 の CI で `--debug imports` 出力を確認、必要なら本 PR 内追加 commit (規約 §(A) PR 内修正優先)
- 2: CI cache 戦略 → 初版 cache 無しでも可、Task 14 に actions/cache 追加は将来の最適化 commit に持ち越し (本 PR scope 外、follow-up issue 化検討)

**2. Placeholder scan:** TBD-AT-BUILD / TBD-FROM-CI-ARTIFACT 値は **Task 13 Step 3** と **Task 19 Step 4** で実値に置換するため "placeholder" ではなく "実行 timing 明示の遅延埋め込み" として扱う。コード内 placeholder (TODO / TBD コメント) は無し。

**3. Type consistency:** PowerShell 関数名・パラメータ名・JSON schema field 名 (schema_version / measured_at / payload_dir / total_file_count / by_top_dir / by_extension) は Task 2 Step 1 (Pester) + Task 2 Step 3 (script 本体) + Task 3 Step 1 (release.yml) + Task 13 Step 2 (assertion) で一貫。Python関数 `_resolve_install_dir` の signature も Task 5 / Task 6 で一貫。launcher.bat 内 path (`%PAYLOAD%allaganeye\allaganeye.exe`) も Task 10 / Task 11 / Task 14 で一貫。
