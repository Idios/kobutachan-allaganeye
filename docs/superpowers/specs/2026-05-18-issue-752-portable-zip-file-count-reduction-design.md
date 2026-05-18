# Issue #752: Portable ZIP file 数削減 設計

> **Status**: design (brainstorming 確定、writing-plans 待ち)
> **作成**: 2026-05-18 / session `exciting-chatelet-67dc1d`
> **対象 issue**: #752 (L3 / l2b-installer / P2-medium)
> **関連**: #508 (FFmpeg LGPLv3 同梱) / #557 (CI smoke-test) / #646 (`allaganeye.bat` 抽象化) / #668 (integrity-manifest)
> **target release**: v0.3.0 cycle (deferred from v0.2.x)

---

## §0 概要

### 目的

Portable ZIP (`allaganeye-vX.Y.Z-windows.zip`) 展開後の `<install>/python/` + `<install>/lib/` 配下のファイル数を削減し、Windows での展開時間と初回利用までの UX を改善する。

### 採用方針

**Option C: PyInstaller `--onedir` で CLI を frozen application 化**。

Python コミュニティの標準ツール (PyInstaller、2005-) を使うことで:

- 自前で zipimport / `__path__` patch / file pruning 等の custom logic を実装しない (= 保守性大前提)
- numpy / scipy / opencv-python-headless 用の **公式 hook が存在**、これらの hybrid package の zip 化 / native split は PyInstaller の責務
- 出力: 1 entry point (`allaganeye\allaganeye.exe`) + `_internal/` (Python interpreter + library.zip + native DLLs) で typical ~150-300 file
- maintenance: PyInstaller 自体の version pin (cf. BtbN FFmpeg snapshot pin) のみ。custom logic 保守不要

### 採用までの経緯 (sanity check)

初版 spec (同 path、git 履歴前段) では **Option A (自前 zipimport + intra-package pruning)** を recommend していた。Idios review で「Python コミュニティ標準か、ハック禁止、保守性大前提」と redirect され、再評価:

- Option A の Phase 1 (pure-Python pkg zipimport) は方向性は標準だが、**自前 PowerShell 実装** = 車輪の再発明
- Option A の Phase 2 (intra-pkg pruning of `*.pyi` / `tests/`) は **非標準**、upstream upgrade 毎に regression 検証コストあり、保守性違反
- **最も標準 + 保守性高い** のは PyInstaller などコミュニティ tool に乗ること

→ Option C を本命に格上げ。Option A は不採用 (fallback も不要、`--onedir` で十分削減できなければ別 issue で `--onefile` や Nuitka を検討)。

### scope

**含む** (build / packaging only):

- [scripts/build-portable-zip.ps1](../../scripts/build-portable-zip.ps1)
- [scripts/tests/build-portable-zip.Tests.ps1](../../scripts/tests/build-portable-zip.Tests.ps1)
- [.github/workflows/release.yml](../../.github/workflows/release.yml) (PyInstaller install + smoke-test 調整)
- 新規: `scripts/installer/allaganeye.spec` (PyInstaller spec file、reproducibility & explicit config 用)
- 新規: `scripts/installer/requirements-pyinstaller.txt` (PyInstaller + hooks-contrib の version pin)
- 新規: `scripts/measure-portable-zip-baseline.ps1` (Step 1、before/after 計測)
- [docs/system-architecture.md](../system-architecture.md) (配布構造の追記)

**含む** (runtime code、最小限の frozen-mode 対応):

- [allaganeye/integrity.py:35](../../allaganeye/integrity.py#L35) `_PACKAGE_INIT` / `_resolve_install_dir` を `sys.frozen` aware に補正 (~5-10 行)。理由: 現実装は `Path(__file__).resolve().parent.parent.parent` で install dir を導出するが、PyInstaller frozen mode では `__file__` が library.zip 内 path を指し `parent.parent.parent` が不正解に。`getattr(sys, 'frozen', False)` 分岐で `sys.executable` ベースに切替。**import 構造変更ではなく path resolution の frozen 対応のみ** (Iron Law 3 抵触しないと判断)

**含まない** (out-of-scope, Iron Law 3):

- **GUI Tauri Rust 側コード** ([gui/src-tauri/src/lib.rs:2575](../../gui/src-tauri/src/lib.rs#L2575) `resolve_allaganeye_command`): 既に `allaganeye.bat` を抽象化レイヤーとして使用 (#646)、`bat` の内部実装変更は Rust から不可視。**変更不要**
- runtime コードの import 構造 (`allaganeye/cli.py` の Typer 構造、`video/*.py` / `audio/*.py` 等): touch なし。pip install から PyInstaller frozen 化への build path 切替のみ
- `ffmpeg/` 構造 (LGPLv3 #508 制約、subprocess invoke のまま影響なし)
- `integrity-manifest.json` schema (#668 v1 維持。PyInstaller output も既存 walker で manifest 化可能)

### Iron Law 整合

- **Iron Law 1** (受け入れ条件): 元 issue (#752) の確認項目を §6 で逐条 mapping、PR review で `enforce-acceptance-criteria` skill 実行
- **Iron Law 3** (scope): **1 spec / 1 PR** (Idios 決定 2026-05-18)。Step 1 baseline measurement と Step 2 PyInstaller migration は同一 PR で実装する。理由: Step 1 単体は behavior 変更なしの infrastructure で、Step 2 と分離するメリット (revert 容易性) より、cohesive 1 PR で before/after 比較を完結させる便益 (PR 本文で実数値を示せる) が勝る
- **Iron Law 4** (close keyword): `Refs #752` のみ、PR merge 後に手動 `gh issue close`
- **Iron Law 6** (Pre-flight): base 同期 + 並行 worktree PR 重複確認 + `/codex:adversarial-review` (Step 5) を必ず実行
- **encoding boundary audit** (CLAUDE.md F4 教訓): PyInstaller bootstrap で Python ↔ subprocess ↔ launcher.bat の 3 層が変わる。PR 内で 3 層全てを audit (Python 側 sys.stdout.encoding / Rust 側 既存パス維持 / cmd.exe code page)

---

## §1 Step 1: Baseline measurement (PR 内先行 commit)

### 目的

変更前の現状を **machine-verifiable** に記録し、Step 2 (PyInstaller migration) の改善幅を客観評価可能にする。Pester regression test の閾値固定にも使う。Step 2 と同一 PR 内で commit 順序を分け、PR diff 上で「baseline → migration → assertion 活性化」の流れが追えるようにする。

### 影響範囲

- 新規: `scripts/measure-portable-zip-baseline.ps1`
- 既存: `scripts/tests/build-portable-zip.Tests.ps1` (本 step では log のみ。Step 2 commit 内で assertion 活性化)

### 設計

#### `scripts/measure-portable-zip-baseline.ps1`

入力: `-PayloadDir <path>` (展開済の Portable ZIP payload root、例 `build/portable/allaganeye-v0.3.0/`)

出力 (stdout JSON、`-Format Human` で readable table):

```json
{
  "schema_version": 1,
  "measured_at": "2026-05-18T12:34:56Z",
  "payload_dir": "build/portable/allaganeye-v0.3.0",
  "total_file_count": 0,
  "total_size_bytes": 0,
  "by_top_dir": {
    "python":  { "file_count": 0, "size_bytes": 0 },
    "lib":     { "file_count": 0, "size_bytes": 0 },
    "ffmpeg":  { "file_count": 0, "size_bytes": 0 },
    "_root":   { "file_count": 0, "size_bytes": 0 }
  },
  "by_extension": {
    ".py":  { "count": 0, "size_bytes": 0 },
    ".pyd": { "count": 0, "size_bytes": 0 },
    ".dll": { "count": 0, "size_bytes": 0 },
    ".pyi": { "count": 0, "size_bytes": 0 },
    "_other": { "count": 0, "size_bytes": 0 }
  }
}
```

実値は Step 1 commit で計測した結果を PR 本文に貼付 (before スナップショット)。

#### Pester regression assertion (本 phase では log のみ)

`scripts/tests/build-portable-zip.Tests.ps1` に context 追加:

```powershell
Context 'File count baseline measurement' {
  BeforeAll {
    $script:baseline = & (Join-Path $PSScriptRoot '..' 'measure-portable-zip-baseline.ps1') `
      -PayloadDir $script:payloadDir | ConvertFrom-Json
  }

  It 'logs baseline file count for future regression detection' {
    Write-Host "Baseline total file count: $($script:baseline.total_file_count)"
    Write-Host "Baseline total size (MB): $([math]::Round($script:baseline.total_size_bytes / 1MB, 2))"
    # Step 1 commit: assertion はまだ無効。Step 2 commit で baseline 値を定数固定し assert を活性化
    $script:baseline.total_file_count | Should -BeGreaterThan 0
  }
}
```

CI release.yml の build-windows job に measurement step + `baseline.json` を artifact upload に追加 (PR diff で before/after 比較取得用)。

---

## §2 Step 2: PyInstaller `--onedir` migration (本体)

### 目的

`pip install --target lib` + Python embeddable interpreter 同梱を、**PyInstaller frozen application** に置き換え、Portable ZIP の Python 関連 file を ~2500 → ~150-300 まで削減する。

### 影響範囲

- `scripts/build-portable-zip.ps1` (step 1-3 を rewrite、step 6 launcher 内容変更)
- `scripts/tests/build-portable-zip.Tests.ps1` (新規関数 / 削除関数 + assertion 活性化)
- `.github/workflows/release.yml` (PyInstaller install step + smoke-test 内容調整)
- 新規: `scripts/installer/allaganeye.spec` (PyInstaller `.spec` ファイル)
- 新規: `scripts/installer/requirements-pyinstaller.txt` (PyInstaller + hooks-contrib version pin)
- **runtime code (最小限の frozen 対応、scope 含む)**: [allaganeye/integrity.py](../../allaganeye/integrity.py) `_resolve_install_dir` を `sys.frozen` 分岐に
- `tests/test_integrity.py` (既存 file に frozen 分岐 unit test 追加)
- [docs/system-architecture.md](../system-architecture.md) §配布
- [docs/cli-spec.md](../cli-spec.md) (exit code 7 = 同梱物欠損 は変わらず)

### 設計

#### PyInstaller version pin

`scripts/installer/requirements-pyinstaller.txt`:

```text
# PyInstaller pinning policy:
#   - patch-level pin (e.g. `pyinstaller==6.20.0`)
#   - hooks-contrib も reproducibility 強化のため explicit pin
#   - 4-6 か月毎に bump、Idios の手元で frozen output が test pass することを確認
#   - bump 時は両 version を同時に上げ、PR で smoke-test + 実機 split を実測
pyinstaller==6.20.0
pyinstaller-hooks-contrib==2026.5
```

CI build-windows job で:

```yaml
- name: Install PyInstaller (#752)
  shell: ${{ matrix.shell }}
  run: |
    python -m pip install --upgrade pip
    python -m pip install -r scripts/installer/requirements-pyinstaller.txt
```

#### `scripts/installer/allaganeye.spec` (PyInstaller spec file)

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

#### `build-portable-zip.ps1` の変更

**削除する step** (旧 Python embed + pip install --target lib path):

- 旧 step 1: Python embed download / extract / `python311._pth` 書き出し
- 旧 step 2: get-pip.py download / install
- 旧 step 3: `pip install --target $LibDir --no-compile $RepoRoot`
- 旧 `$PthFile`, `$LibDir`, `$GetPipUrl`, `$GetPipSha256` 等の関連変数 (これらは PyInstaller では不要)

**新規 step** (artifact 内 venv 方針、Idios 決定):

```powershell
# 1. Create build venv inside the build artifact dir (clean reproducible env).
# Putting the venv inside $BuildDir means it gets cleaned along with the rest
# of the build artifact, avoiding stale state between runs. CI clean build
# 前提のため artifact 外への venv 共有は不要 (Idios 決定 2026-05-18).
$VenvDir = Join-Path $BuildDir 'venv'
& python -m venv $VenvDir
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

# 2. Install allaganeye + PyInstaller into venv
& $VenvPython -m pip install --upgrade pip --no-cache-dir
& $VenvPython -m pip install `
    -r (Join-Path $RepoRoot 'scripts\installer\requirements-pyinstaller.txt') `
    --no-cache-dir
& $VenvPython -m pip install $RepoRoot --no-cache-dir

# 3. Run PyInstaller (frozen --onedir)
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

# 4. Copy frozen application into payload root
Copy-Item -Recurse -Path (Join-Path $PyInstallerDist 'allaganeye') -Destination $PayloadDir
```

実行後:

- `<install>/allaganeye/allaganeye.exe` (entry point)
- `<install>/allaganeye/_internal/` (interpreter + library.zip + native DLLs)
- `<install>/ffmpeg/` (未変更、LGPLv3 同梱)
- `<install>/allaganeye-gui.exe` (Tauri、未変更)

#### `Get-LauncherTemplate` 関数の変更

`build-portable-zip.ps1` の `Get-LauncherTemplate` (lines 279-380) 内の `python.exe -m allaganeye` 呼び出しを `allaganeye.exe` に置換:

before (line 357-360):

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

その他の launcher 仕様 (GUI dispatch、`--help`、`set ALLAGANEYE_FFMPEG`、`pause`、`exit /b %EXIT_CODE%` (#580)、(#617) `start "" "%PAYLOAD%allaganeye-gui.exe"`) は未変更。

#### runtime code: `integrity.py` の frozen 対応

[allaganeye/integrity.py:32-50](../../allaganeye/integrity.py#L32) を以下のように変更:

before:

```python
_PACKAGE_INIT: Path = Path(__file__).resolve().parent / "__init__.py"


def _resolve_install_dir(package_init: Path) -> Path:
    """Compute install dir from ``allaganeye/__init__.py`` path.

    Portable ZIP layout: ``<install dir>/lib/allaganeye/__init__.py``,
    so the install dir is 3 ancestors up from ``__init__.py``.
    """
    return package_init.resolve().parent.parent.parent


def _default_manifest_path() -> Path:
    install_dir = _resolve_install_dir(_PACKAGE_INIT)
    return install_dir / _MANIFEST_NAME
```

after:

```python
import sys


_PACKAGE_INIT: Path = Path(__file__).resolve().parent / "__init__.py"


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


def _default_manifest_path() -> Path:
    install_dir = _resolve_install_dir(_PACKAGE_INIT)
    return install_dir / _MANIFEST_NAME
```

理由 / scope justification:

- 変更箇所は **path resolution の 1 箇所** のみ。import 構造 / API / runtime 挙動は不変
- `getattr(sys, 'frozen', False)` は PyInstaller / cx_Freeze の公式判定 idiom (PEP 不要、PyInstaller docs にも記載)
- dev mode (`pip install -e .`) では `sys.frozen` 未設定なので既存 path が走る (regression なし)
- legacy Portable ZIP (本 PR merge 以前) を解凍した manifest からも install dir を導出可能 (forward compat)
- Iron Law 3 (scope creep) との関係: 本変更は「PyInstaller frozen mode を runtime が認識する」ための必要最小限。spec §0 scope で明示

#### runtime code: `audio/refs/__init__.py` (本 spec の検証対象外)

[`allaganeye/audio/refs/__init__.py`](../../allaganeye/audio/refs/__init__.py) は `importlib.resources.files()` + `as_file()` を使用。PyInstaller `.spec` の `collect_data_files('allaganeye.audio.refs')` で `.npz` は `_internal/allaganeye/audio/refs/fanfare.npz` に bundle される (=resource は frozen bundle 内に確実に存在)。**コード変更不要**。

audio 系 path の empirical な動作確認は本 spec の検証対象外 (Idios 2026-05-18 判断: 現在 audio 機能を使っていないため本 PR では深掘りしない)。将来 audio 機能を再度 active に使う際に問題が出れば別 issue で `audio/refs/__init__.py` の `with as_file(...) as path: return Path(path)` pattern を再評価する。

#### Tauri Rust 側 (変更不要、再確認)

[gui/src-tauri/src/lib.rs:2575](../../gui/src-tauri/src/lib.rs#L2575) `resolve_allaganeye_command` の production path は [line 2605-2616](../../gui/src-tauri/src/lib.rs#L2605) で:

```rust
fn resolve_from_resource_dir(resource_dir: &Path) -> Option<AllaganeyeCommand> {
    let bat = resource_dir.join("allaganeye.bat");
    if bat.exists() {
        Some(AllaganeyeCommand {
            program: bat.to_string_lossy().to_string(),
            ...
```

`.bat` を program に設定するだけで、bat の内部実装 (`python.exe` か `allaganeye.exe` か) は **Rust から不可視**。Step 2 で bat 内部だけ書き換える形で abstraction が成立。

dev mode (`npm run tauri dev` / `cargo check`) は `resolve_python_fallback` (line 2622) を経由するため、PyInstaller frozen output が無くても worktree の `pip install -e .` で動く。**dev 環境への影響もゼロ**。

#### integrity-manifest との互換性

[scripts/build-portable-zip.ps1:382-440](../../scripts/build-portable-zip.ps1#L382) の `New-IntegrityManifest` は payload を `Get-ChildItem -Recurse -File` で walk し、`*.pyc` と dotfile を除外して全 file を size とともに記録する汎用 implementation。

PyInstaller output (`allaganeye/_internal/*.dll`, `_internal/library.zip` 等) も同じ walker で自動的に entry 化される。**追加実装不要**。

`*.pyc` 除外ルールは PyInstaller bundle 内の `_internal/library.zip` 内部には届かない (zip 内部は manifest 対象外、size 一致のみで検査) ため、`*.pyc` の non-determinism 問題 (cf. PR #702 実機検証) も影響なし。

#### CI smoke-test 調整

`.github/workflows/release.yml` の既存 smoke-test:

- **Lv A (`--version`)**: 不変。bat → allaganeye.exe 経由で `allaganeye --version` を実行、stdout に `allaganeye` 文字列を assert
- **Lv B (`detect` 3s fixture)**: 不変。bat → allaganeye.exe で detect 実行
- **integrity fall-through (exit 7)**: **削除対象 file を変更**。zip 内部は manifest 対象外なので、現行の lib/ 配下 file 削除では効かない。新規に **`allaganeye/allaganeye.exe` または `_internal/python311.dll`** を削除して exit 7 を trigger

#### Pester test 更新

`scripts/tests/build-portable-zip.Tests.ps1`:

- **削除**: `python311._pth` 内容検査 (関連 step が build から削除)
- **削除**: `Get-PurePythonPackages` / `Move-PurePythonPackages` 等の旧 spec の関数 test (実装しないため)
- **追加**: `Get-LauncherTemplate` の `allaganeye.exe` path 検査 (path が `python\python.exe` ではなく `allaganeye\allaganeye.exe` を含む)
- **追加**: PyInstaller `.spec` ファイル存在 + parse 可能性 (`python -c "exec(open('scripts/installer/allaganeye.spec').read())"` を mock せず `exec()` で構文 check のみ)
- **追加**: `_internal/allaganeye/audio/refs/fanfare.npz` が build artifact に存在することを assert (audio path 動作確認は scope 外だが、resource bundle 自体は assert)
- **追加**: Step 1 baseline と Step 2 after の file count assertion 活性化 (`Should -BeLessThan` で削減幅 ≥ 80%)

### 受け入れ条件 (PR 全体、Step 1 + Step 2 統合)

**Step 1 (baseline measurement) 部分**:

- [ ] `scripts/measure-portable-zip-baseline.ps1` が `-PayloadDir` から JSON / Human 出力可能
- [ ] CI `build-windows` job が build 完了後に measurement step を実行し artifact に `baseline.json` を含む
- [ ] PR 本文に develop-0.3.0 ベースラインと PyInstaller 後の数値を before/after 並記 (machine-verified)

**Step 2 (PyInstaller migration) 部分**:

- [ ] `scripts/installer/allaganeye.spec` が存在し、PyInstaller で `--noconfirm --clean` で再現可能 build
- [ ] `scripts/installer/requirements-pyinstaller.txt` に `pyinstaller==6.20.0` + `pyinstaller-hooks-contrib==2026.5` を pin
- [ ] build script から `python311.zip`, `get-pip.py`, `pip install --target lib` 関連 step が削除されている
- [ ] payload root に `<install>/allaganeye/allaganeye.exe` (PyInstaller frozen) が存在
- [ ] payload root に `<install>/python/` ディレクトリが **存在しない** (廃止)
- [ ] payload root に `<install>/lib/` ディレクトリが **存在しない** (廃止)
- [ ] `<install>/allaganeye/_internal/allaganeye/audio/refs/fanfare.npz` が存在 (resource bundle 確認、動作確認は scope 外)
- [ ] `<install>/allaganeye.bat` が `allaganeye\allaganeye.exe` を呼ぶよう書き換わっている
- [ ] `<install>/ffmpeg/` は変化なし (LGPLv3 同梱維持)
- [ ] `<install>/allaganeye-gui.exe` (Tauri) は変化なし
- [ ] `allaganeye/integrity.py` の `_resolve_install_dir` が `sys.frozen` 分岐済 + pytest PASS (frozen / non-frozen 両方)
- [ ] `tests/test_integrity.py` の既存 test が引き続き PASS (regression 無し)
- [ ] CI smoke-test Lv A (`--version`) が PASS
- [ ] CI smoke-test Lv B (`detect` 3s fixture) が PASS
- [ ] CI smoke-test integrity fall-through (frozen DLL 削除 → exit 7) が PASS
- [ ] `integrity-manifest.json` が payload root に存在、`allaganeye/allaganeye.exe` などを 1 entry として記録
- [ ] Step 1 baseline からの file count 削減幅 ≥ 80% を PR 本文に記載 (machine-verified)
- [ ] `.bat` ダブルクリック起動の手動確認 (machine-unverifiable、`AskUserQuestion`、Idios 実機):
  - [ ] 配布 ZIP 展開後 `allaganeye.bat` ダブルクリック → GUI 起動
  - [ ] `allaganeye.bat <video.mp4>` で split 完了 (audio 機能は scope 外、video 検出 only でも PASS とする)
  - [ ] `allaganeye-gui.exe` から detect 起動 → completion 画面遷移

### Self-Test Report (1 PR 全体)

- machine-verified: PyInstaller frozen output 生成 / CI smoke 全 PASS / file count 削減数 / integrity-manifest 整合 / pytest 全 PASS (`[x]`)
- machine-unverifiable: 展開時間体感、GUI export 動作、長時間動画 (1:25+) split (`-`、Idios 実機 AskUserQuestion)

---

## §3 Test 戦略

1 PR / 2 commit (Step 1 → Step 2)。各 layer の更新点:

| layer | Step 1 (baseline) | Step 2 (PyInstaller) |
| --- | --- | --- |
| Pester unit | new measurement script | `Get-LauncherTemplate` path 検査 + `.spec` 構文 check |
| Pester integration | baseline log のみ | file count assertion 活性化 (削減幅 ≥ 80%) |
| pytest unit (`tests/test_integrity.py`) | unchanged | **`sys.frozen` 分岐の monkeypatch test 追加** (frozen / non-frozen 両 path) |
| CI smoke A (`--version`) | unchanged | unchanged (bat → allaganeye.exe 経由) |
| CI smoke B (`detect` 3s) | unchanged | unchanged (bat → allaganeye.exe 経由) |
| CI smoke integrity exit 7 | unchanged | **削除対象 file を `allaganeye/allaganeye.exe` に変更** |
| `python -m allaganeye` dev mode | unchanged | unchanged (Rust の `resolve_python_fallback` で worktree から動く) |
| Idios 実機検証 | n/a | `.bat` ダブルクリック起動 / `.bat` split / GUI 起動 (audio は scope 外) |

### 開発者の local build 手順

```powershell
# build script は内部で artifact 内 venv を作成・pip install するため、
# 開発者は build-portable-zip.ps1 を直接呼び出すだけで良い (one-shot)

# 1. Build Portable ZIP (dry-run、--SkipArchive で zip 化省略)
pwsh -File scripts\build-portable-zip.ps1 -Version 0.3.0-dev -SkipArchive

# 2. Measure baseline / after
pwsh -File scripts\measure-portable-zip-baseline.ps1 `
    -PayloadDir build\portable\allaganeye-v0.3.0-dev
```

---

## §4 Risks / mitigation

| Risk | severity | mitigation |
| --- | --- | --- |
| PyInstaller の numpy/scipy/cv2 hook が将来 version で broken | 低-中 | `requirements-pyinstaller.txt` で patch pin、release 前に Idios 手元で smoke 確認 |
| PyInstaller output が byte-deterministic でない | 低 | integrity-manifest は **size only** で hash 不使用、size は同 source + 同 env で deterministic |
| ALLAGANEYE_FFMPEG 環境変数の path resolution が frozen 化で変わる | 低 | `allaganeye.bat` で env var を設定する layer が変更なし、frozen Python は通常通り `os.environ` 参照 |
| `audio/refs` の fanfare.npz が frozen bundle に欠落 | 低 | `.spec` の `collect_data_files('allaganeye.audio.refs')` で明示 bundle、build artifact の `_internal/allaganeye/audio/refs/` に file 存在を Pester で assert (現在 audio 機能未使用、Idios 2026-05-18 / 動作 path の empirical 確認は scope 外) |
| `integrity.py` の `sys.frozen` 分岐 unit test が dev / frozen 両方で実行必要 | 低 | `monkeypatch.setattr(sys, "frozen", True)` + `monkeypatch.setattr(sys, "executable", str(tmp_path/"fake"/"allaganeye.exe"))` で frozen 経路を mock、既存 test pattern を踏襲 |
| `--no-gpu` 等 path で subprocess (`ffmpeg`) 呼び出しが broken | 低 | ffmpeg は別 exe で subprocess.run 経由、frozen 化と無関係 |
| CI 時間増加 (~3-5min) | 低 | actions/cache で venv + pyinstaller cache を `~/.cache/pyinstaller` キャッシュ |
| LGPLv3 ffmpeg (#508) 影響 | 無 | `ffmpeg/` touch なし |
| integrity-check (#668) との衝突 | 無 | payload walker は generic、PyInstaller output も自動 entry 化 |
| dev mode (`npm run tauri dev`) への影響 | 無 | `resolve_python_fallback` が `python -m allaganeye` を維持、`pip install -e .` で動作 |
| reproducibility (build 毎の hash drift) | 低 | size 不変であれば manifest OK。PyInstaller 6+ は size 安定 |
| 本 PR と並行進行 L3 work (#576 等) の conflict | 低 | scope = build script + workflow yml + 新規 `scripts/installer/` 配下、runtime code 中心の L3 とは衝突 risk 低 |
| Codex review 推奨 | 中 | Iron Law 6 Pre-flight Step 5 `/codex:adversarial-review` で「PyInstaller hook 漏れ / numpy import 漏れ / `os.environ` 経由 path 解決」を focus 指定 |

---

## §5 Open questions (writing-plans 持ち越し)

writing-plans 持ち越しの未確定事項は以下のみ (主要設計判断は Idios 2026-05-18 で確定済):

1. **`hiddenimports` の追加要否**: numpy/scipy/cv2 の公式 hook で覆えない動的 import がある場合 `hiddenimports` に追加が必要。Idios 実機検証時に `--debug imports` 出力を確認し fallback として追加するか、CI 上で `python -c "import allaganeye"` 等の dry import 検証を増やすか writing-plans で判断
2. **CI cache 戦略**: PyInstaller / pip cache を actions/cache でどう保持するか (key 設計)。`~/.cache/pyinstaller` + `~/AppData/Local/pip/cache` を cache 化する想定だが clean build 優先で初版は cache 無しでも可

確定済 (本 spec で固定、再議論不要):

- `scripts/installer/` ディレクトリ配置 (Idios 決定)
- venv は build artifact 内 (`build/portable/venv/`、Idios 決定)
- UPX 不使用 (Idios 決定)
- `pyinstaller-hooks-contrib==2026.5` を explicit pin (Idios 決定)
- 1 PR 構成 (Step 1 + Step 2、Idios 決定)
- audio path の empirical 検証は scope 外 (Idios 決定、現 audio 未使用)

---

## §6 元 issue 受け入れ条件 mapping

issue #752 "確認項目 / 作業項目" → 本 spec mapping:

| 元 item | 対応 phase | machine-verified? |
| --- | --- | --- |
| `python/` と `lib/` 現状のファイル数・サイズを計測 | Step 1 | yes (baseline.json) |
| Option A を試作 (zip pack ステップ追加) | **Option C に変更** (本 spec §0 経緯) | yes (CI build artifact) |
| L1 CLI 全コマンドで import エラー無し | Step 2 (CI smoke Lv A/B) | yes |
| L2 GUI から Python subprocess 起動の振る舞い | Step 2 (Idios 実機検証) | partial |
| `integrity-manifest.json` との整合性 | Step 2 (CI smoke 整合) | yes |
| 各パッケージの LICENSE 配置方針 | Step 2 (PyInstaller `--collect-data` で LICENSE も収集) | yes (PR で manifest 確認) |

---

## §7 docs 更新 (本 PR 同梱)

[docs/system-architecture.md](../system-architecture.md) §配布 に追記:

```markdown
### Portable ZIP 内構造 (#752 で簡素化)

- `<install>/allaganeye/`: PyInstaller frozen CLI application (#752、v0.3.0+)
  - `allaganeye.exe`: entry point
  - `_internal/`: Python interpreter + library.zip + numpy/scipy/cv2 native DLLs
- `<install>/ffmpeg/`: FFmpeg LGPLv3 shared build (LICENSE.txt 同梱、#508)
- `<install>/allaganeye.bat`: launcher (#617、内部実装は `allaganeye\allaganeye.exe` を呼ぶ)
- `<install>/allaganeye-gui.exe`: Tauri GUI (#527、frozen CLI を allaganeye.bat 経由で起動)
- `<install>/README.txt`: 日本語 (#749)
- `<install>/integrity-manifest.json`: 同梱物整合性検査 manifest (#668)

旧来の `python/` (embeddable interpreter) および `lib/` (pip install --target) ディレクトリは **v0.3.0 で廃止**。PyInstaller `--onedir` が Python interpreter + 全依存を `allaganeye/_internal/` に統合。
```

[docs/cli-spec.md](../cli-spec.md) §exit code: exit 7 (同梱物欠損) は未変更。検査対象 file は `allaganeye/allaganeye.exe` および `_internal/` 配下を含む。

---

## §8 関連 issue / PR

- 本 issue: #752 (この spec の対象)
- 関連 issue:
  - #508 (FFmpeg LGPLv3 同梱) — 影響無 (ffmpeg/ touch なし)
  - #557 (Portable ZIP CI smoke-test) — Step 2 で smoke 内容を frozen 経由に微調整
  - #646 (`allaganeye.bat` を Rust から resource_dir で見つける abstraction) — **本 spec の前提**、Step 2 で実利益化
  - #668 (integrity-manifest) — schema 不変、payload walker 自動対応
- 関連 PR (履歴):
  - #702 (integrity 実装、`*.pyc` / dotfile exclude 教訓) — manifest walker の既知制約として継承
  - #729 (BOM-less UTF-8) — manifest write path 不変
  - #570 / #615 (Portable ZIP 形式確定) — 構造は維持、内部実装のみ変更
  - #617 (.bat double-click GUI) — launcher 大枠未変更
- follow-up 候補 (本 spec 対象外):
  - PyInstaller `--onefile` 化 (size 更削減、ただし TEMP 展開で portable 哲学と衝突)
  - Nuitka 化 (compile による更削減、ただし build 複雑度大)
  - `ffmpeg/` の strip / 不要 codec 削減 (要 LGPLv3 制約確認)
  - `requirements-pyinstaller.txt` への hooks-contrib explicit pin (reproducibility 強化、§5 #6)
