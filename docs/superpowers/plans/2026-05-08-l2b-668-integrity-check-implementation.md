# Lane IV-a §4 / #668: Portable ZIP 同梱物 起動時健全性チェック Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portable ZIP 配布版の同梱物 (ffmpeg / Python embed / fanfare.npz / GUI exe) が削除・破損した場合に、GUI 起動時 / CLI `--version` で高速 check (~50ms 以内) して blocking modal または exit code 7 を出す。再展開を促すエラー UX で外部ユーザーの初期トラブルシュート負荷を軽減する。

**Architecture:** build 時に `scripts/build-portable-zip.ps1` が payload root に `integrity-manifest.json` を自動 enum (path + size + tolerance_bytes=0) で生成。起動時に Rust (release build only、`#[cfg(not(debug_assertions))]`) が `gui/src-tauri/src/integrity.rs` で読み、失敗時 Tauri event `integrity-error` を `globalErrorListener` 経由で `useErrorStore.showError({errorCategory:'integrity', isPanic:true, isRecoverable:false})` に流して既存 `ErrorModal` を blocking 表示。CLI 側は `allaganeye/integrity.py` で同 manifest を読み、`version_callback` で fail なら `IntegrityError(exit_code=7)` raise。両言語で `<install dir>/logs/error-YYYYMMDD.log` (plain text、append) に記録。dev mode は Rust = `#[cfg]` / Python = env `ALLAGANEYE_INTEGRITY_SKIP=1` で skip。

**Tech Stack:** Python 3.11 (typer / pytest / json), Rust (serde_json / Tauri 2.10 emit), TypeScript (Zustand store + `@tauri-apps/api/event listen`), PowerShell (Pester v5), GitHub Actions (windows-latest pwsh).

**Spec:** [`docs/superpowers/specs/2026-05-08-l2b-668-integrity-check-design.md`](../specs/2026-05-08-l2b-668-integrity-check-design.md)

---

## Context for the implementer

このリポジトリは **kobutachan-allaganeye** (FF14 Frontline 動画から試合分割・ハイライト抽出する Python CLI + Tauri 2 GUI)。L2 (v0.2.0) は Portable ZIP 配布形式 (`scripts/build-portable-zip.ps1` が `dist/allaganeye-vX.Y.Z-windows.zip` を生成) で、展開すると以下のレイアウト:

```text
allaganeye-vX.Y.Z/                   (= <install dir>)
├── allaganeye-gui.exe                (Tauri release build)
├── allaganeye.bat                    (CLI launcher)
├── README.txt
├── integrity-manifest.json           (本 PR で新設)
├── python/                            (Python 3.11 embeddable)
│   ├── python.exe
│   ├── python311.dll
│   └── ...standard lib dlls...
├── lib/                               (pip install --target lib の出力)
│   └── allaganeye/                    (本パッケージ)
│       ├── __init__.py
│       ├── integrity.py              (本 PR で新設)
│       ├── exceptions.py             (本 PR で IntegrityError 追加)
│       └── audio/refs/fanfare.npz
├── ffmpeg/                            (BtbN LGPL shared、bin/ 階層なし)
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   ├── *.dll (avcodec / avfilter / etc.)
│   └── LICENSE.txt
└── logs/                              (起動後生成、bug report ガード)
    └── error-YYYYMMDD.log             (本 PR が書き込む先)
```

主要制約:

- **Iron Law 4**: PR / commit に `Closes` / `Fixes` / `Resolves` 禁止。`Refs #668` のみ。マージ後は手動 `gh issue close` (本 plan の対象外)。
- **Iron Law 6**: PR 作成 Pre-flight 必須 (`git fetch origin develop-0.2.0` → 取り込み未済 commit 確認 → 並行 worktree PR 重複確認 → path 別自動チェック (`ruff` / `pyright` / `pytest` + `npm run lint/typecheck/test/build` + `cargo check` + `Invoke-Pester`) 全 pass)。
- **TDD**: 各 task は Red → Green → (Refactor) → Commit。test を先に書いて fail を確認してから実装。
- **DRY**: 既存 `useErrorStore` / `ErrorModal` / `force_exit_app` / `open_folder_in_explorer` Tauri command を reuse。新 component は作らない。
- **base ブランチ**: `develop-0.2.0` (PR を出すときの target)。
- **コミット末尾**: 全 commit に `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` を付ける。session-id (`funny-tereshkova-d355c8`) は最終 PR 本文に記載。

`ALLAGANEYE_SAMPLE_VIDEO_DIR` 環境変数の動画 fixture は本 PR では使わない (integrity check は file 存在 + size のみ)。

---

## File Structure

| 種別 | path | 役割 | Task |
| --- | --- | --- | --- |
| Python new | `allaganeye/integrity.py` | manifest load + check + log + skip | 2-8 |
| Python new | `tests/test_integrity.py` | unit tests | 2-8 |
| Python mod | `allaganeye/exceptions.py` | `IntegrityError(exit_code=7)` | 1 |
| Python mod | `tests/test_exceptions.py` | exit code 7 test | 1 |
| Python mod | `allaganeye/cli.py` | `version_callback` で integrity 呼出 | 9 |
| Python mod | `tests/test_cli.py` | callback test | 9 |
| Build mod | `scripts/build-portable-zip.ps1` | `New-IntegrityManifest` 関数 + main path | 10 |
| Build mod | `scripts/tests/build-portable-zip.Tests.ps1` | Pester regression test | 10 |
| Rust new | `gui/src-tauri/src/integrity.rs` | Manifest types + check + log + date helper + check_install_dir wrapper | 11-13 |
| Rust mod | `gui/src-tauri/src/lib.rs` | `mod integrity;` + setup hook integration | 14 |
| TS mod | `gui/src/state/errorStore.ts` | `ErrorCategory` に `'integrity'` | 15 |
| TS mod | `gui/src/state/errorStore.test.ts` | 'integrity' category test | 15 |
| TS mod | `gui/src/components/ErrorModal.tsx` | `errorCategory==='integrity'` 表示分岐 | 16 |
| TS mod | `gui/src/components/ErrorModal.test.tsx` | integrity test | 16 |
| TS mod | `gui/src/lib/globalErrorListener.ts` | `integrity-error` event listener | 17 |
| TS mod | `gui/src/lib/globalErrorListener.test.ts` | listener test | 17 |
| CI mod | `.github/workflows/release.yml` | build-windows job E2E step | 18 |
| Docs mod | `docs/system-architecture.md` | §配布 健全性チェック仕様 | 19 |
| Docs mod | `docs/cli-spec.md` | exit code 表に 7 追加 | 19 |

合計 **5 new + 14 modify = 19 file change**、19 task / 19 commit。

---

## Task 1: `IntegrityError(exit_code=7)` を `exceptions.py` に追加

**Files:**

- Modify: [allaganeye/exceptions.py](../../../allaganeye/exceptions.py)
- Test: [tests/test_exceptions.py](../../../tests/test_exceptions.py)

- [ ] **Step 1: Write the failing test**

[tests/test_exceptions.py](../../../tests/test_exceptions.py) の末尾に追加:

```python
def test_integrity_error_exit_code_seven():
    """IntegrityError reports exit_code 7 (#668)."""
    from allaganeye.exceptions import IntegrityError

    exc = IntegrityError("bundled file missing")
    assert exc.exit_code == 7
    assert isinstance(exc, AllaganEyeError)
    assert exc.context == {}


def test_integrity_error_context_renders_in_verbose():
    """IntegrityError uses base verbose_detail for context dicts (#668)."""
    from allaganeye.exceptions import IntegrityError

    exc = IntegrityError(
        "integrity check failed",
        context={
            "missing": ["lib/allaganeye/audio/refs/fanfare.npz"],
            "size_mismatch": [],
        },
    )
    detail = exc.verbose_detail()
    assert "missing:" in detail
    assert "size_mismatch:" in detail
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_exceptions.py::test_integrity_error_exit_code_seven tests/test_exceptions.py::test_integrity_error_context_renders_in_verbose -v
```

Expected: ImportError / `AttributeError: module 'allaganeye.exceptions' has no attribute 'IntegrityError'`.

- [ ] **Step 3: Implement minimal code**

[allaganeye/exceptions.py](../../../allaganeye/exceptions.py) の末尾 (`DetectionError` クラスの後) に追加:

```python
class IntegrityError(AllaganEyeError):
    """Bundled binary/asset integrity check failed (#668).

    Raised by :func:`allaganeye.integrity.check` when a file listed in
    ``integrity-manifest.json`` is missing or has unexpected size beyond
    its ``tolerance_bytes`` allowance. CLI maps this to exit code 7.
    """

    exit_code = 7
```

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_exceptions.py -v
```

Expected: 全 test pass (新 2 件含む)。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/exceptions.py tests/test_exceptions.py
git commit -F - <<'EOF'
feat(exceptions): IntegrityError (exit code 7) を追加 (Refs #668)

Portable ZIP 同梱物の起動時健全性チェック (Lane IV-a §4) の起点。
allaganeye.integrity.check が raise する単一例外で、CLI は exit
code 7 にマッピングして bug report ガードに使う。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 2: `integrity.load_manifest` 関数

**Files:**

- Create: `allaganeye/integrity.py`
- Test: `tests/test_integrity.py`

- [ ] **Step 1: Write the failing test**

新規 file [tests/test_integrity.py](../../../tests/test_integrity.py) を作成:

```python
"""Tests for allaganeye.integrity (#668).

Bundled file integrity check used by both:
- the CLI ``--version`` callback (production path)
- the Tauri release-build startup hook (mirror logic in Rust)
"""

import json
from pathlib import Path

import pytest

from allaganeye.exceptions import IntegrityError
from allaganeye.integrity import load_manifest


def test_load_manifest_parses_valid_json(tmp_path: Path) -> None:
    """load_manifest returns the parsed JSON when valid."""
    manifest = tmp_path / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [
                    {"path": "ffmpeg/ffmpeg.exe", "size": 100, "tolerance_bytes": 0}
                ],
            }
        ),
        encoding="utf-8",
    )

    data = load_manifest(manifest)

    assert data["version"] == 1
    assert data["files"][0]["path"] == "ffmpeg/ffmpeg.exe"


def test_load_manifest_raises_when_missing(tmp_path: Path) -> None:
    """Missing manifest -> IntegrityError with helpful context."""
    missing = tmp_path / "no-such.json"

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(missing)

    assert "not found" in str(exc_info.value)
    assert exc_info.value.context["manifest_path"] == str(missing)


def test_load_manifest_raises_on_invalid_json(tmp_path: Path) -> None:
    """Malformed JSON -> IntegrityError with json_error context."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(bad)

    assert "invalid JSON" in str(exc_info.value)
    assert "json_error" in exc_info.value.context


def test_load_manifest_raises_when_files_key_missing(tmp_path: Path) -> None:
    """JSON without `files` key -> IntegrityError."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": 1}), encoding="utf-8")

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(bad)

    assert "files" in str(exc_info.value)
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_integrity.py -v
```

Expected: ModuleNotFoundError (`allaganeye.integrity` 未実装)。

- [ ] **Step 3: Implement minimal code**

新規 file [allaganeye/integrity.py](../../../allaganeye/integrity.py) を作成:

```python
"""Bundled binary/asset integrity check (#668).

Used by both:
- the CLI ``--version`` callback (production path) — see ``allaganeye.cli``
- the Tauri release-build startup hook (mirror logic in Rust) — see
  ``gui/src-tauri/src/integrity.rs``

Both paths read the same ``integrity-manifest.json`` generated at build
time by ``scripts/build-portable-zip.ps1``. Detection failures produce a
blocking error UX (CLI exit code 7 / GUI ``ErrorModal``) and append a
plain-text record to ``<install dir>/logs/error-YYYYMMDD.log``.

Skip in dev / pytest by setting ``ALLAGANEYE_INTEGRITY_SKIP=1``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from allaganeye.exceptions import IntegrityError

_MANIFEST_NAME = "integrity-manifest.json"


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and validate the integrity manifest JSON.

    Raises :class:`IntegrityError` when the file is missing, the JSON is
    malformed, or the top-level ``files`` key is absent.
    """
    if not path.exists():
        raise IntegrityError(
            f"integrity manifest not found: {path}",
            context={"manifest_path": str(path)},
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IntegrityError(
            f"integrity manifest invalid JSON: {path}",
            context={"manifest_path": str(path), "json_error": str(exc)},
        ) from exc
    if not isinstance(data, dict) or "files" not in data:
        raise IntegrityError(
            f"integrity manifest missing 'files' key: {path}",
            context={"manifest_path": str(path)},
        )
    return data
```

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 4 件 pass。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -F - <<'EOF'
feat(integrity): manifest load 関数の骨格 (Refs #668)

allaganeye.integrity.load_manifest を追加。Portable ZIP 内
integrity-manifest.json を読んで validate し、IntegrityError で
原因を context 付きで surface。後続 task が check / log / cli wiring
を積む。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 3: `_resolve_install_dir` + `_default_manifest_path` ヘルパ

`allaganeye/integrity.py` は Portable ZIP 内では `<install dir>/lib/allaganeye/integrity.py` の path に置かれる (`pip install --target lib`)。`Path(__file__).resolve()` から `<install dir>` を逆算する helper を追加し、テストできるよう関数化する。

**Files:**

- Modify: `allaganeye/integrity.py`
- Test: `tests/test_integrity.py`

- [ ] **Step 1: Write the failing test**

[tests/test_integrity.py](../../../tests/test_integrity.py) に追加:

```python
def test_resolve_install_dir_from_package_init(tmp_path: Path) -> None:
    """_resolve_install_dir walks 3 levels up from package __init__.

    Portable ZIP layout: <install dir>/lib/allaganeye/__init__.py
    """
    from allaganeye.integrity import _resolve_install_dir

    init_path = tmp_path / "lib" / "allaganeye" / "__init__.py"
    init_path.parent.mkdir(parents=True)
    init_path.write_text("", encoding="utf-8")

    assert _resolve_install_dir(init_path) == tmp_path


def test_default_manifest_path_under_install_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_default_manifest_path returns <install dir>/integrity-manifest.json.

    Patches the module-level Path-from-__file__ resolution so the test is
    independent of where pytest finds the actual package.
    """
    import allaganeye.integrity as integ

    fake_init = tmp_path / "lib" / "allaganeye" / "__init__.py"
    fake_init.parent.mkdir(parents=True)
    fake_init.write_text("", encoding="utf-8")
    monkeypatch.setattr(integ, "_PACKAGE_INIT", fake_init)

    assert integ._default_manifest_path() == tmp_path / "integrity-manifest.json"
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_integrity.py::test_resolve_install_dir_from_package_init tests/test_integrity.py::test_default_manifest_path_under_install_dir -v
```

Expected: ImportError / AttributeError (helper 未実装)。

- [ ] **Step 3: Implement minimal code**

[allaganeye/integrity.py](../../../allaganeye/integrity.py) 内、import 群の後 / `load_manifest` の前に追加:

```python
# Resolved at import time so monkeypatch.setattr can override for tests
# without touching the real ``__file__`` (which would also affect other
# tests). Production callers use ``_default_manifest_path()`` which reads
# this constant.
_PACKAGE_INIT: Path = Path(__file__).resolve().parent / "__init__.py"


def _resolve_install_dir(package_init: Path) -> Path:
    """Compute install dir from ``allaganeye/__init__.py`` path.

    Portable ZIP layout: ``<install dir>/lib/allaganeye/__init__.py``,
    so the install dir is 3 ancestors up from ``__init__.py``.
    """
    return package_init.resolve().parent.parent.parent


def _default_manifest_path() -> Path:
    """Return ``<install dir>/integrity-manifest.json`` for production use."""
    install_dir = _resolve_install_dir(_PACKAGE_INIT)
    return install_dir / _MANIFEST_NAME
```

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 6 件 pass (Task 2 の 4 件 + 新 2 件)。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -F - <<'EOF'
feat(integrity): install dir 解決ヘルパ (Refs #668)

_resolve_install_dir / _default_manifest_path / _PACKAGE_INIT を追加。
Portable ZIP 内では <install dir>/lib/allaganeye/__init__.py 配置を
前提に 3 階層上を install dir とする。テスト時は monkeypatch で
_PACKAGE_INIT を差し替えて install レイアウトを simulate できる。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 4: `integrity.check` happy path

**Files:**

- Modify: `allaganeye/integrity.py`
- Test: `tests/test_integrity.py`

- [ ] **Step 1: Write the failing test**

[tests/test_integrity.py](../../../tests/test_integrity.py) に追加:

```python
def test_check_happy_path_returns_none(tmp_path: Path) -> None:
    """check() with all manifest entries present and exact size returns None."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "ffmpeg" / "ffmpeg.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x" * 100)

    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [
                    {
                        "path": "ffmpeg/ffmpeg.exe",
                        "size": 100,
                        "tolerance_bytes": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # Expected: returns None, does not raise
    assert check(manifest, install_dir=install) is None
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_integrity.py::test_check_happy_path_returns_none -v
```

Expected: ImportError (`check` not defined yet).

- [ ] **Step 3: Implement minimal code**

[allaganeye/integrity.py](../../../allaganeye/integrity.py) に追加:

```python
def check(manifest_path: Path | None = None, *, install_dir: Path | None = None) -> None:
    """Verify all bundled files match the manifest.

    Default arguments (production): manifest at ``<install dir>/integrity-manifest.json``,
    install_dir is the manifest's parent directory. Tests pass explicit paths.

    Currently happy path only — missing/size detection is added in
    later tasks. Returns ``None`` on success.
    """
    if manifest_path is None:
        manifest_path = _default_manifest_path()
    if install_dir is None:
        install_dir = manifest_path.parent

    data = load_manifest(manifest_path)
    for entry in data.get("files", []):
        rel_path = entry["path"]
        target = install_dir / rel_path
        # happy path: file must exist and size match. Branches for failure
        # paths come in subsequent tasks.
        actual = target.stat().st_size  # raises FileNotFoundError if missing
        if actual != int(entry["size"]):
            raise IntegrityError(
                "integrity check failed (size_mismatch placeholder)",
                context={
                    "missing": [],
                    "size_mismatch": [{
                        "path": rel_path,
                        "expected": int(entry["size"]),
                        "actual": actual,
                    }],
                },
            )
    return None
```

> **注意**: この実装は happy path のみ正確に動く。missing 時は `FileNotFoundError` が漏れる、size_mismatch も簡易判定。後続 Task 5/6 で正しい branching に置き換える。

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_integrity.py::test_check_happy_path_returns_none -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -F - <<'EOF'
feat(integrity): check() happy path (Refs #668)

manifest 内全 entry が存在 + size 一致なら None 返却。missing /
size_mismatch / env_skip / log は後続 task で積む。default の
manifest_path / install_dir 解決も組み込み。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 5: `integrity.check` missing detection

**Files:**

- Modify: `allaganeye/integrity.py`
- Test: `tests/test_integrity.py`

- [ ] **Step 1: Write the failing test**

[tests/test_integrity.py](../../../tests/test_integrity.py) に追加:

```python
def test_check_detects_missing_file(tmp_path: Path) -> None:
    """check() raises IntegrityError listing missing path."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [
                    {"path": "absent.bin", "size": 100, "tolerance_bytes": 0}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError) as exc_info:
        check(manifest, install_dir=install)

    ctx = exc_info.value.context
    assert ctx["missing"] == ["absent.bin"]
    assert ctx["size_mismatch"] == []


def test_check_aggregates_multiple_missing(tmp_path: Path) -> None:
    """check() reports every missing entry, not just the first."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [
                    {"path": "a.bin", "size": 1, "tolerance_bytes": 0},
                    {"path": "b.bin", "size": 1, "tolerance_bytes": 0},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError) as exc_info:
        check(manifest, install_dir=install)

    assert sorted(exc_info.value.context["missing"]) == ["a.bin", "b.bin"]
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_integrity.py::test_check_detects_missing_file tests/test_integrity.py::test_check_aggregates_multiple_missing -v
```

Expected: FAIL (現状 check は missing で `FileNotFoundError` を漏らす)。

- [ ] **Step 3: Implement minimal code**

[allaganeye/integrity.py](../../../allaganeye/integrity.py) の `check` 関数を以下に置き換え:

```python
def check(manifest_path: Path | None = None, *, install_dir: Path | None = None) -> None:
    """Verify all bundled files match the manifest.

    Aggregates ``missing`` paths into the IntegrityError context so the
    caller (CLI / GUI emit) can show all failures at once instead of
    one-at-a-time.
    """
    if manifest_path is None:
        manifest_path = _default_manifest_path()
    if install_dir is None:
        install_dir = manifest_path.parent

    data = load_manifest(manifest_path)
    missing: list[str] = []
    size_mismatch: list[dict[str, Any]] = []
    for entry in data.get("files", []):
        rel_path = entry["path"]
        target = install_dir / rel_path
        if not target.exists():
            missing.append(rel_path)
            continue
        # size_mismatch detection comes in Task 6
        actual = target.stat().st_size
        if actual != int(entry["size"]):
            size_mismatch.append(
                {
                    "path": rel_path,
                    "expected": int(entry["size"]),
                    "actual": actual,
                }
            )
    if missing or size_mismatch:
        raise IntegrityError(
            f"integrity check failed: {len(missing)} missing, "
            f"{len(size_mismatch)} size mismatch",
            context={"missing": missing, "size_mismatch": size_mismatch},
        )
    return None
```

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 9 件 pass (Task 4 の test も含む)。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -F - <<'EOF'
feat(integrity): check() missing detection (Refs #668)

Aggregate 集計方式で全 missing path を IntegrityError context に
書く。size_mismatch placeholder は同じ aggregate に入れているが
正確な比較は次 task。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 6: `integrity.check` size_mismatch + tolerance_bytes

**Files:**

- Modify: `allaganeye/integrity.py`
- Test: `tests/test_integrity.py`

- [ ] **Step 1: Write the failing test**

[tests/test_integrity.py](../../../tests/test_integrity.py) に追加:

```python
def test_check_detects_size_mismatch_outside_tolerance(tmp_path: Path) -> None:
    """check() reports size_mismatch for files whose size differs > tolerance_bytes."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "tiny.bin"
    target.write_bytes(b"x" * 50)  # actual 50, expected 100, tolerance 0 -> fail

    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "tiny.bin", "size": 100, "tolerance_bytes": 0}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError) as exc_info:
        check(manifest, install_dir=install)

    sm = exc_info.value.context["size_mismatch"]
    assert len(sm) == 1
    assert sm[0]["path"] == "tiny.bin"
    assert sm[0]["expected"] == 100
    assert sm[0]["actual"] == 50


def test_check_passes_within_tolerance(tmp_path: Path) -> None:
    """check() accepts size within tolerance_bytes window."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "buffered.bin"
    target.write_bytes(b"x" * 105)  # actual 105, expected 100, tolerance 10 -> pass

    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "buffered.bin", "size": 100, "tolerance_bytes": 10}],
            }
        ),
        encoding="utf-8",
    )

    # Should not raise
    assert check(manifest, install_dir=install) is None


def test_check_tolerance_default_zero(tmp_path: Path) -> None:
    """tolerance_bytes is treated as 0 when absent from the entry."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "exact.bin"
    target.write_bytes(b"x" * 100)

    manifest = install / "integrity-manifest.json"
    # entry omits tolerance_bytes
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "exact.bin", "size": 100}],
            }
        ),
        encoding="utf-8",
    )

    # exact match -> pass
    assert check(manifest, install_dir=install) is None
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_integrity.py::test_check_detects_size_mismatch_outside_tolerance tests/test_integrity.py::test_check_passes_within_tolerance tests/test_integrity.py::test_check_tolerance_default_zero -v
```

Expected: 1-2 件 FAIL (現状 check は exact 比較のみ、tolerance 未対応)。

- [ ] **Step 3: Implement minimal code**

[allaganeye/integrity.py](../../../allaganeye/integrity.py) の `check` 関数内、size 比較部分を tolerance 対応に置き換え:

```python
        # 既存の size 比較ブロックを以下に差し替え
        actual = target.stat().st_size
        expected = int(entry["size"])
        tolerance = int(entry.get("tolerance_bytes", 0))
        if abs(actual - expected) > tolerance:
            size_mismatch.append(
                {
                    "path": rel_path,
                    "expected": expected,
                    "actual": actual,
                }
            )
```

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 12 件 pass (Task 4-5 の test も維持)。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -F - <<'EOF'
feat(integrity): check() size_mismatch + tolerance_bytes (Refs #668)

abs(actual - expected) > tolerance_bytes で size 判定。
tolerance_bytes は default 0 (manifest 既定方針: 厳格一致、必要 file
のみ buffer 上書き)。fanfare.npz 等の将来 numpy 形式 bump 時に
file 単位で buffer 設定可能。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 7: `integrity.check` env skip (`ALLAGANEYE_INTEGRITY_SKIP=1`)

**Files:**

- Modify: `allaganeye/integrity.py`
- Test: `tests/test_integrity.py`

- [ ] **Step 1: Write the failing test**

[tests/test_integrity.py](../../../tests/test_integrity.py) に追加:

```python
def test_check_skips_when_env_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ALLAGANEYE_INTEGRITY_SKIP=1 makes check() a no-op even with missing manifest."""
    from allaganeye.integrity import check

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")

    # Manifest does not exist; without env this would raise.
    fake_manifest = tmp_path / "no-such.json"
    fake_install = tmp_path / "fake-install"

    assert check(fake_manifest, install_dir=fake_install) is None


def test_check_does_not_skip_when_env_set_to_other_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only literal '1' triggers skip; '0' / 'false' / unset run the check."""
    from allaganeye.integrity import check

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "0")

    fake_manifest = tmp_path / "no-such.json"

    with pytest.raises(IntegrityError):
        check(fake_manifest, install_dir=tmp_path)
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_integrity.py::test_check_skips_when_env_set tests/test_integrity.py::test_check_does_not_skip_when_env_set_to_other_value -v
```

Expected: 1 件 FAIL (env=1 でも現状は manifest 不在で raise する)。

- [ ] **Step 3: Implement minimal code**

[allaganeye/integrity.py](../../../allaganeye/integrity.py):

```python
import os  # 既存 import 群に追加 (未追加なら)

_SKIP_ENV = "ALLAGANEYE_INTEGRITY_SKIP"
```

`check` 関数の冒頭 (manifest_path 解決の前) に追加:

```python
def check(manifest_path: Path | None = None, *, install_dir: Path | None = None) -> None:
    """..."""
    if os.environ.get(_SKIP_ENV) == "1":
        return None
    # 既存実装
    if manifest_path is None:
        ...
```

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 14 件 pass。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -F - <<'EOF'
feat(integrity): ALLAGANEYE_INTEGRITY_SKIP=1 で skip (Refs #668)

開発環境 (pip install -e .) や pytest 実行で integrity check が
邪魔になる場合に env で no-op 化。'1' のみ強制 (security: 'true' /
'yes' 等を許容しない)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 8: `_write_log` + check() 失敗時の log emission

**Files:**

- Modify: `allaganeye/integrity.py`
- Test: `tests/test_integrity.py`

- [ ] **Step 1: Write the failing test**

[tests/test_integrity.py](../../../tests/test_integrity.py) に追加:

```python
def test_log_written_on_failure(tmp_path: Path) -> None:
    """check() failure appends a record to <install dir>/logs/error-YYYYMMDD.log."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "absent.bin", "size": 100, "tolerance_bytes": 0}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError):
        check(manifest, install_dir=install)

    logs_dir = install / "logs"
    assert logs_dir.exists()
    log_files = list(logs_dir.glob("error-*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "integrity check failed" in content
    assert '"absent.bin"' in content  # JSON-encoded path inside the record


def test_log_silent_fail_when_dir_creation_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Log write failure does not change the modal/exit code path (silent fail)."""
    import allaganeye.integrity as integ
    from allaganeye.integrity import check

    def boom(*_args, **_kwargs):
        raise PermissionError("readonly install dir")

    monkeypatch.setattr(integ, "_write_log", boom)

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "absent.bin", "size": 1, "tolerance_bytes": 0}],
            }
        ),
        encoding="utf-8",
    )

    # check() must still raise IntegrityError even when _write_log explodes.
    with pytest.raises(IntegrityError):
        check(manifest, install_dir=install)
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_integrity.py::test_log_written_on_failure tests/test_integrity.py::test_log_silent_fail_when_dir_creation_blocked -v
```

Expected: FAIL (現状は log 書込みなし)。

- [ ] **Step 3: Implement minimal code**

[allaganeye/integrity.py](../../../allaganeye/integrity.py) に追加:

```python
from datetime import datetime, timezone  # 既存 import 群に追加
```

```python
_LOG_DIR_NAME = "logs"


def _write_log(
    install_dir: Path,
    missing: list[str],
    size_mismatch: list[dict[str, Any]],
) -> None:
    """Append an integrity-failure record to ``<install dir>/logs/error-YYYYMMDD.log``.

    Format: ``{ISO8601 UTC} [error] integrity check failed: missing=<JSON>; size_mismatch=<JSON>``.

    Caller catches exceptions silently — the modal/exit code is the
    primary user channel; log is supplementary (#668 §6 Log fallback).
    """
    log_dir = install_dir / _LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    log_path = log_dir / f"error-{now.strftime('%Y%m%d')}.log"
    line = (
        f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} [error] integrity check failed: "
        f"missing={json.dumps(missing)}; size_mismatch={json.dumps(size_mismatch)}\n"
    )
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)
```

`check` 関数内、`raise IntegrityError(...)` の **直前** に追加:

```python
    if missing or size_mismatch:
        try:
            _write_log(install_dir, missing, size_mismatch)
        except OSError:
            # Silent fail — modal/exit code is the primary channel,
            # log is supplementary. Do not let a broken logs/ dir block
            # the integrity-failure surface.
            pass
        raise IntegrityError(
            f"integrity check failed: {len(missing)} missing, "
            f"{len(size_mismatch)} size mismatch",
            context={"missing": missing, "size_mismatch": size_mismatch},
        )
```

> **注意**: `test_log_silent_fail_when_dir_creation_blocked` は `_write_log` 自体を `boom` (PermissionError raise) に差し替える。`PermissionError` は `OSError` の subclass なので上の `except OSError:` で吸収される。

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 16 件 pass。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/integrity.py tests/test_integrity.py
git commit -F - <<'EOF'
feat(integrity): 失敗時 <install>/logs/error-YYYYMMDD.log に追記 (Refs #668)

plain text format で append。書込み失敗 (read-only install dir 等)
は OSError 全般を silent 吸収して modal/exit code の primary
channel を維持。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 9: `cli.py` `version_callback` で integrity check

**Files:**

- Modify: `allaganeye/cli.py:28-31`, `allaganeye/cli.py:13-17` (import block)
- Test: `tests/test_cli.py` (既存 file への追加)

- [ ] **Step 1: Write the failing test**

既存 [tests/test_cli.py](../../../tests/test_cli.py) を読んで pattern を把握 (`typer.testing.CliRunner` を使っているはず)。新規 test として追加:

```python
def test_version_callback_exits_zero_when_integrity_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--version exit 0 + version 出力 when integrity passes."""
    import typer
    from allaganeye import cli

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")

    with pytest.raises(typer.Exit) as exc_info:
        cli.version_callback(True)

    assert (exc_info.value.exit_code or 0) == 0


def test_version_callback_exits_seven_when_integrity_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--version exit 7 when integrity fails, with stderr message."""
    import typer
    from allaganeye import cli, integrity
    from allaganeye.exceptions import IntegrityError

    def fake_check() -> None:
        raise IntegrityError(
            "integrity check failed: 1 missing, 0 size mismatch",
            context={
                "missing": ["lib/allaganeye/audio/refs/fanfare.npz"],
                "size_mismatch": [],
            },
        )

    monkeypatch.setattr(integrity, "check", fake_check)

    with pytest.raises(typer.Exit) as exc_info:
        cli.version_callback(True)

    assert exc_info.value.exit_code == 7
    captured = capsys.readouterr()
    assert "integrity check failed" in captured.err


def test_version_callback_returns_when_value_false() -> None:
    """value=False (no --version flag) returns silently."""
    from allaganeye import cli

    assert cli.version_callback(False) is None
```

- [ ] **Step 2: Run the test, verify it FAILS**

```bash
pytest tests/test_cli.py::test_version_callback_exits_zero_when_integrity_passes tests/test_cli.py::test_version_callback_exits_seven_when_integrity_fails tests/test_cli.py::test_version_callback_returns_when_value_false -v
```

Expected: FAIL (現状は integrity check を呼ばない、env_skip も認識しない)。

- [ ] **Step 3: Implement minimal code**

[allaganeye/cli.py](../../../allaganeye/cli.py) を修正。

(a) import block (line 13-17) を以下に置き換え:

```python
from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
    InputFileError,
    IntegrityError,
)
```

(b) `version_callback` (line 28-31) を以下に置き換え:

```python
def version_callback(value: bool) -> None:
    if not value:
        return
    # #668 -- verify bundled files before reporting version. Skipped via
    # ``ALLAGANEYE_INTEGRITY_SKIP=1`` for dev installs (handled inside
    # integrity.check). Production Portable ZIP runs the check and exits
    # with code 7 on bundled-file corruption / deletion.
    from allaganeye import integrity

    try:
        integrity.check()
    except IntegrityError as exc:
        typer.echo(f"error: {exc}", err=True)
        if exc.context:
            typer.echo(exc.verbose_detail(), err=True)
        raise typer.Exit(code=exc.exit_code)
    typer.echo(f"allaganeye {__version__}")
    raise typer.Exit()
```

> **注意**: `from allaganeye import integrity` を関数内で遅延 import するのは循環 import を避けるため (cli.py が exceptions に依存し、integrity も exceptions に依存するが、cli が直接 integrity を import しても循環はしない。ただし test の `monkeypatch.setattr(integrity, "check", ...)` を効かせるため module-level の attribute を差し替え可能にする)。

- [ ] **Step 4: Run the test, verify it PASSES**

```bash
pytest tests/test_cli.py -v
ruff check allaganeye/ tests/
pyright
```

Expected: 全 cli test pass + ruff / pyright clean。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/cli.py tests/test_cli.py
git commit -F - <<'EOF'
feat(cli): version_callback で integrity check (Refs #668)

allaganeye --version (-V) 実行時に allaganeye.integrity.check() を
呼び、IntegrityError -> exit code 7 + stderr エラー、verbose_detail
で missing / size_mismatch context を出す。

ALLAGANEYE_INTEGRITY_SKIP=1 で開発環境では skip。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 10: `build-portable-zip.ps1` `New-IntegrityManifest` 関数 + 主実装パスへの統合

build script の payload 構築完了後 (`# 7. README` の後 + `# 8. Compress` の前) に manifest を生成する。`Get-ChildItem -Recurse -File` で全 file を自動 enum し、manifest 自身は除外する。Pester で関数単体を test。

**Files:**

- Modify: `scripts/build-portable-zip.ps1`
- Modify: `scripts/tests/build-portable-zip.Tests.ps1`

- [ ] **Step 1: Write the failing Pester test**

[scripts/tests/build-portable-zip.Tests.ps1](../../../scripts/tests/build-portable-zip.Tests.ps1) の末尾 (最後の `Describe` block の後) に追加:

```powershell
Describe 'New-IntegrityManifest' {
  BeforeAll {
    $script:ManifestTmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "manifest-test-$(New-Guid)"
    New-Item -ItemType Directory -Force -Path $script:ManifestTmpDir | Out-Null
  }

  AfterAll {
    if (Test-Path $script:ManifestTmpDir) {
      Remove-Item -Recurse -Force $script:ManifestTmpDir
    }
  }

  It 'enumerates files and produces valid JSON with required fields' {
    # Arrange: create a payload with files at different depths
    $f1 = Join-Path $script:ManifestTmpDir 'allaganeye.bat'
    Set-Content -Path $f1 -Value 'fake' -Encoding ASCII

    $ffDir = Join-Path $script:ManifestTmpDir 'ffmpeg'
    New-Item -ItemType Directory -Force -Path $ffDir | Out-Null
    $f2 = Join-Path $ffDir 'ffmpeg.exe'
    Set-Content -Path $f2 -Value 'fake binary' -Encoding ASCII

    $libDir = Join-Path $script:ManifestTmpDir 'lib\allaganeye\audio\refs'
    New-Item -ItemType Directory -Force -Path $libDir | Out-Null
    $f3 = Join-Path $libDir 'fanfare.npz'
    Set-Content -Path $f3 -Value 'fake npz' -Encoding ASCII

    # Act
    $json = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    $manifest = $json | ConvertFrom-Json

    # Assert: schema
    $manifest.version | Should -Be 1
    $manifest.generated_at | Should -Match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'
    $manifest.files | Should -Not -BeNullOrEmpty

    # POSIX-style separators in path field
    $paths = @($manifest.files | ForEach-Object { $_.path })
    $paths | Should -Contain 'allaganeye.bat'
    $paths | Should -Contain 'ffmpeg/ffmpeg.exe'
    $paths | Should -Contain 'lib/allaganeye/audio/refs/fanfare.npz'

    # Each entry has size > 0 and tolerance_bytes = 0
    foreach ($entry in $manifest.files) {
      $entry.size | Should -BeGreaterThan 0
      $entry.tolerance_bytes | Should -Be 0
    }
  }

  It 'excludes integrity-manifest.json itself from the enumeration' {
    $extra = Join-Path $script:ManifestTmpDir 'integrity-manifest.json'
    Set-Content -Path $extra -Value '{}' -Encoding UTF8

    $json = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    $manifest = $json | ConvertFrom-Json
    $paths = @($manifest.files | ForEach-Object { $_.path })
    $paths | Should -Not -Contain 'integrity-manifest.json'
  }
}
```

- [ ] **Step 2: Run Pester, verify FAIL**

```powershell
Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: FAIL (関数 `New-IntegrityManifest` 未定義)。

- [ ] **Step 3: Implement minimal code**

[scripts/build-portable-zip.ps1](../../../scripts/build-portable-zip.ps1) の **既存関数定義の最後** (line 297 `Get-LauncherTemplate` 関数の `}` 直後、dot-source guard `if ([string]::IsNullOrEmpty($Version)) { return }` の **前**) に新関数を追加:

```powershell
function New-IntegrityManifest {
  <#
  .SYNOPSIS
  Generate integrity-manifest.json content by enumerating the payload directory (#668).

  .DESCRIPTION
  Walks ``$PayloadDir`` recursively, records each file's POSIX-style relative
  path and size with ``tolerance_bytes = 0`` (= 厳格一致), and returns a JSON
  string. The manifest file itself (``integrity-manifest.json``) is excluded
  so its presence/size doesn't break the check that consumes it.

  Exposed as a function so Pester can verify the JSON shape and exclusion
  logic without dot-sourcing the full build path.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$PayloadDir
  )

  $manifestName = 'integrity-manifest.json'
  $entries = @()
  $base = (Resolve-Path $PayloadDir).Path
  Get-ChildItem -Path $PayloadDir -Recurse -File | ForEach-Object {
    if ($_.Name -eq $manifestName) { return }
    $rel = $_.FullName.Substring($base.Length).TrimStart('\', '/')
    $relPosix = $rel -replace '\\', '/'
    $entries += [pscustomobject]@{
      path = $relPosix
      size = $_.Length
      tolerance_bytes = 0
    }
  }

  $generatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  $manifest = [ordered]@{
    version = 1
    generated_at = $generatedAt
    files = @($entries)
  }
  return ($manifest | ConvertTo-Json -Depth 4)
}
```

[scripts/build-portable-zip.ps1](../../../scripts/build-portable-zip.ps1) の **主実装パス**、`# 7. README` セクション (line 421-427) と `# 8. Compress` (line 429-) の **間** に新セクション挿入:

```powershell
# 7.5 Integrity manifest (#668)
# Generated after all payload steps complete so it reflects the actual files
# Tauri build / pip install / FFmpeg copy / launcher / README produced.
$ManifestPath = Join-Path $PayloadDir 'integrity-manifest.json'
Set-Content -Path $ManifestPath -Value (New-IntegrityManifest -PayloadDir $PayloadDir) -Encoding UTF8
Write-Host "Generated $ManifestPath"
```

- [ ] **Step 4: Run Pester, verify PASS**

```powershell
Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1 -Output Detailed
```

Expected: 全 test pass (新 2 件含む)。

オプション (任意): local dry-run で実 manifest を生成して目視確認:

```powershell
./scripts/build-portable-zip.ps1 -Version '0.2.0' -SkipArchive
Get-Content (Join-Path $PWD 'build/portable/allaganeye-v0.2.0/integrity-manifest.json') | ConvertFrom-Json | Format-List
```

これは optional な手元確認。CI で同等が走るので必須ではない。

- [ ] **Step 5: Commit**

```bash
git add scripts/build-portable-zip.ps1 scripts/tests/build-portable-zip.Tests.ps1
git commit -F - <<'EOF'
feat(build): integrity-manifest.json を payload に同梱 (Refs #668)

New-IntegrityManifest 関数で payload 全 file を Get-ChildItem -Recurse
で自動 enum (固定 list 不要、build/run drift 0)。manifest 自身を
除外、POSIX-style 相対 path + size + tolerance_bytes=0 の JSON。

主実装パスでは # 7 README と # 8 Compress の間に挿入し、Tauri build /
pip install / FFmpeg copy / launcher / README の全成果物を反映。

Pester regression test (2 件) で schema + 除外を担保。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 11: Rust `integrity.rs` Manifest types

Rust 側 manifest loader の骨格。`Manifest` / `ManifestEntry` / `IntegrityErrorPayload` / `SizeMismatch` 構造を定義し、`load_manifest` を実装。Tauri の `serde_json` (Cargo.toml に既存) を使う。新規 dependency は追加しない (date helper は Task 13 で manual 実装)。

**Files:**

- Create: `gui/src-tauri/src/integrity.rs`
- (Rust の cargo test は同一 file 内 `#[cfg(test)] mod tests` で書く既存 convention に倣う)

- [ ] **Step 1: Write the failing test**

新規 file [gui/src-tauri/src/integrity.rs](../../../gui/src-tauri/src/integrity.rs) を以下で **test のみ** 仮実装:

```rust
//! Bundled binary/asset integrity check (#668).
//!
//! Build script (`scripts/build-portable-zip.ps1`) generates
//! `integrity-manifest.json` at the payload root. The Tauri release build
//! reads that manifest at startup and emits an `integrity-error` event when
//! files are missing or sizes don't match — which the frontend turns into a
//! blocking `ErrorModal` (`errorCategory='integrity'`).
//!
//! Mirror of `allaganeye/integrity.py`. The two MUST stay in sync on the
//! manifest schema (version, files[].path/size/tolerance_bytes).

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

/// Schema for `integrity-manifest.json`.
#[derive(Debug, Deserialize)]
pub struct Manifest {
    #[allow(dead_code)] // recorded for forward-compat; only `files` is used now
    pub version: u32,
    #[serde(default)]
    pub files: Vec<ManifestEntry>,
}

#[derive(Debug, Deserialize)]
pub struct ManifestEntry {
    pub path: String,
    pub size: u64,
    #[serde(default)]
    pub tolerance_bytes: u64,
}

/// Sent to the frontend via `integrity-error` Tauri event when `check`
/// reports failures. Field names are camelCase via serde rename so the
/// JS payload matches `useErrorStore.showError` consumer expectations.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IntegrityErrorPayload {
    pub missing: Vec<String>,
    pub size_mismatch: Vec<SizeMismatch>,
    pub log_path: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SizeMismatch {
    pub path: String,
    pub expected: u64,
    pub actual: u64,
}

/// Load the manifest. Returns `Err(String)` describing the issue so callers
/// can route it through the same notification path as integrity failures.
pub fn load_manifest(path: &Path) -> Result<Manifest, String> {
    let text = fs::read_to_string(path).map_err(|e| {
        format!("integrity manifest read failed ({}): {}", path.display(), e)
    })?;
    serde_json::from_str(&text).map_err(|e| {
        format!("integrity manifest invalid JSON ({}): {}", path.display(), e)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    fn write_manifest(dir: &TempDir, body: &str) -> std::path::PathBuf {
        let p = dir.path().join("integrity-manifest.json");
        let mut f = fs::File::create(&p).unwrap();
        f.write_all(body.as_bytes()).unwrap();
        p
    }

    #[test]
    fn load_manifest_parses_valid_json() {
        let dir = TempDir::new().unwrap();
        let path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "a.bin", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        let m = load_manifest(&path).expect("should parse");
        assert_eq!(m.version, 1);
        assert_eq!(m.files.len(), 1);
        assert_eq!(m.files[0].path, "a.bin");
        assert_eq!(m.files[0].size, 100);
        assert_eq!(m.files[0].tolerance_bytes, 0);
    }

    #[test]
    fn load_manifest_returns_err_for_missing_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("no-such.json");
        let err = load_manifest(&path).unwrap_err();
        assert!(err.contains("read failed"));
    }

    #[test]
    fn load_manifest_returns_err_for_invalid_json() {
        let dir = TempDir::new().unwrap();
        let path = write_manifest(&dir, "not json");
        let err = load_manifest(&path).unwrap_err();
        assert!(err.contains("invalid JSON"));
    }

    #[test]
    fn manifest_entry_tolerance_bytes_defaults_to_zero() {
        let dir = TempDir::new().unwrap();
        let path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "a.bin", "size": 100}]}"#,
        );
        let m = load_manifest(&path).expect("should parse");
        assert_eq!(m.files[0].tolerance_bytes, 0);
    }
}
```

- [ ] **Step 2: cargo test, verify FAIL**

```powershell
cd gui/src-tauri
cargo test --lib integrity::tests:: 2>&1
```

Expected: 上で書いたコードはコンパイル通って test も通るので **PASS** になる (test-first 単体 では fail しない、実装も同時に書いたため)。これは新規 module の最初の commit 形態で、純粋 TDD の "test fails before implementation" は module 単位では難しい。ここでは **module 全体を 1 task で書く** 妥協を取る (skill ガイド: TDD は behavior 単位、新規 module の骨格 1 cycle はパターン正当)。

- [ ] **Step 3: (skipped — Step 1 で実装も込み)**

- [ ] **Step 4: cargo test PASS 確認 + clippy**

```powershell
cd gui/src-tauri
cargo test --lib integrity 2>&1
cargo clippy --lib --no-deps -- -D warnings 2>&1
```

Expected: 全 4 件 pass、clippy clean。

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/integrity.rs
git commit -F - <<'EOF'
feat(rust/integrity): Manifest / IntegrityErrorPayload types + load_manifest (Refs #668)

allaganeye/integrity.py の Rust mirror。Manifest / ManifestEntry
(serde Deserialize) / IntegrityErrorPayload / SizeMismatch
(serde Serialize、Tauri event payload 用、camelCase rename) を
定義し、load_manifest で JSON parse + Err string を返却。

cargo test (4 件) で valid / missing / invalid JSON / tolerance
default を担保。後続 task で check / log / setup hook 統合を積む。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 12: Rust `check` 関数

`check(manifest_path: &Path, install_dir: &Path) -> Result<(), IntegrityErrorPayload>` を実装。Python 側と同じ aggregate 集計 + tolerance_bytes 判定。log は Task 13 で別途。

**Files:**

- Modify: `gui/src-tauri/src/integrity.rs`

- [ ] **Step 1: Write the failing test**

[gui/src-tauri/src/integrity.rs](../../../gui/src-tauri/src/integrity.rs) の `mod tests` ブロックに追加:

```rust
    #[test]
    fn check_happy_path_returns_ok() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("ffmpeg/ffmpeg.exe");
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        fs::write(&target, vec![b'x'; 100]).unwrap();

        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "ffmpeg/ffmpeg.exe", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        check(&manifest_path, install).expect("should pass");
    }

    #[test]
    fn check_detects_missing_file() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "absent.bin", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        let err = check(&manifest_path, install).unwrap_err();
        assert_eq!(err.missing, vec!["absent.bin".to_string()]);
        assert!(err.size_mismatch.is_empty());
    }

    #[test]
    fn check_detects_size_mismatch_outside_tolerance() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("tiny.bin");
        fs::write(&target, vec![b'x'; 50]).unwrap();
        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "tiny.bin", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        let err = check(&manifest_path, install).unwrap_err();
        assert!(err.missing.is_empty());
        assert_eq!(err.size_mismatch.len(), 1);
        assert_eq!(err.size_mismatch[0].path, "tiny.bin");
        assert_eq!(err.size_mismatch[0].expected, 100);
        assert_eq!(err.size_mismatch[0].actual, 50);
    }

    #[test]
    fn check_passes_within_tolerance() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("buffered.bin");
        fs::write(&target, vec![b'x'; 105]).unwrap();
        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "buffered.bin", "size": 100, "tolerance_bytes": 10}]}"#,
        );
        check(&manifest_path, install).expect("within tolerance should pass");
    }
```

- [ ] **Step 2: cargo test, verify FAIL**

```powershell
cd gui/src-tauri
cargo test --lib integrity::tests::check_ 2>&1
```

Expected: コンパイル fail (`check` 関数未実装)。

- [ ] **Step 3: Implement minimal code**

[gui/src-tauri/src/integrity.rs](../../../gui/src-tauri/src/integrity.rs) に追加 (`load_manifest` の後、`mod tests` の前):

```rust
/// Run integrity check.
/// - `Ok(())` when all manifest entries match.
/// - `Err(IntegrityErrorPayload)` when any file is missing or its size is
///   outside `tolerance_bytes`. Aggregated payload lists every failure so
///   the modal can show all at once.
///
/// Manifest read failure (missing/malformed JSON) is also surfaced as an
/// error payload listing the manifest itself in `missing`. This lets the
/// frontend treat a corrupt manifest the same as a corrupt bundle.
pub fn check(manifest_path: &Path, install_dir: &Path) -> Result<(), IntegrityErrorPayload> {
    let manifest = match load_manifest(manifest_path) {
        Ok(m) => m,
        Err(_msg) => {
            return Err(IntegrityErrorPayload {
                missing: vec![manifest_path.to_string_lossy().into_owned()],
                size_mismatch: vec![],
                // log_path is filled by check_install_dir wrapper (Task 13).
                // Empty here is acceptable for tests; production callers go
                // through the wrapper.
                log_path: String::new(),
            });
        }
    };

    let mut missing: Vec<String> = vec![];
    let mut size_mismatch: Vec<SizeMismatch> = vec![];
    for entry in &manifest.files {
        let target = install_dir.join(&entry.path);
        match fs::metadata(&target) {
            Err(_) => missing.push(entry.path.clone()),
            Ok(meta) => {
                let actual = meta.len();
                let expected = entry.size;
                let tol = entry.tolerance_bytes;
                let diff = if actual > expected {
                    actual - expected
                } else {
                    expected - actual
                };
                if diff > tol {
                    size_mismatch.push(SizeMismatch {
                        path: entry.path.clone(),
                        expected,
                        actual,
                    });
                }
            }
        }
    }

    if missing.is_empty() && size_mismatch.is_empty() {
        return Ok(());
    }
    Err(IntegrityErrorPayload {
        missing,
        size_mismatch,
        log_path: String::new(),
    })
}
```

- [ ] **Step 4: cargo test PASS 確認**

```powershell
cd gui/src-tauri
cargo test --lib integrity 2>&1
cargo clippy --lib --no-deps -- -D warnings 2>&1
```

Expected: 全 8 件 pass、clippy clean。

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/integrity.rs
git commit -F - <<'EOF'
feat(rust/integrity): check 関数 (Refs #668)

allaganeye/integrity.py の check と同型 logic で、missing /
size_mismatch を aggregate 集計し IntegrityErrorPayload に詰める。
manifest 自体の読み込み失敗 (missing / 壊れた JSON) は manifest path
を missing list に入れて report する。

log_path は次 task の check_install_dir wrapper で埋まる。

cargo test (4 件追加で計 8) で happy / missing / size_mismatch /
tolerance を担保。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 13: Rust date helper + `write_log` + `check_install_dir` wrapper

ログファイル名生成 (`error-YYYYMMDD.log`) と record format を Python 側と一致させる。新 dep 追加を避けるため、`SystemTime::duration_since(UNIX_EPOCH)` から手書き計算。

**Files:**

- Modify: `gui/src-tauri/src/integrity.rs`

- [ ] **Step 1: Write the failing test**

[gui/src-tauri/src/integrity.rs](../../../gui/src-tauri/src/integrity.rs) の `mod tests` ブロックに追加:

```rust
    #[test]
    fn epoch_to_components_handles_known_epoch_seconds() {
        // 2026-05-08T12:34:56Z = 1778329696 seconds since epoch
        let (y, mo, d, h, mi, s) = epoch_to_components(1778329696);
        assert_eq!((y, mo, d, h, mi, s), (2026, 5, 8, 12, 34, 56));
    }

    #[test]
    fn epoch_to_components_handles_leap_year_feb_29() {
        // 2024-02-29T00:00:00Z = 1709164800 seconds since epoch
        let (y, mo, d, _h, _mi, _s) = epoch_to_components(1709164800);
        assert_eq!((y, mo, d), (2024, 2, 29));
    }

    #[test]
    fn write_log_creates_logs_dir_and_appends_record() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let missing = vec!["absent.bin".to_string()];
        let size_mismatch = vec![];
        write_log(install, &missing, &size_mismatch).expect("should write");

        let logs = install.join("logs");
        assert!(logs.exists(), "logs dir should be created");
        let log_files: Vec<_> = fs::read_dir(&logs).unwrap().collect();
        assert_eq!(log_files.len(), 1);
        let path = log_files[0].as_ref().unwrap().path();
        let name = path.file_name().unwrap().to_string_lossy();
        assert!(
            name.starts_with("error-") && name.ends_with(".log"),
            "filename format: {}",
            name
        );
        let content = fs::read_to_string(&path).unwrap();
        assert!(content.contains("integrity check failed"));
        assert!(content.contains("\"absent.bin\""));
    }

    #[test]
    fn check_install_dir_returns_none_on_success() {
        // Mock install dir with manifest pointing to a file that exists
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("a.bin");
        fs::write(&target, b"x").unwrap();
        let manifest = install.join("integrity-manifest.json");
        fs::write(
            &manifest,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "a.bin", "size": 1, "tolerance_bytes": 0}]}"#,
        )
        .unwrap();

        // We need to invoke through the wrapper, not check() directly, to
        // verify the wrapper routes through check() and back.
        let result = check_install_dir_with_paths(&manifest, install);
        assert!(result.is_none());
    }

    #[test]
    fn check_install_dir_returns_payload_with_log_path_on_failure() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let manifest = install.join("integrity-manifest.json");
        fs::write(
            &manifest,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "absent.bin", "size": 1, "tolerance_bytes": 0}]}"#,
        )
        .unwrap();

        let payload = check_install_dir_with_paths(&manifest, install).expect("should fail");
        assert_eq!(payload.missing, vec!["absent.bin".to_string()]);
        assert!(
            payload.log_path.contains("logs"),
            "log_path should reference logs dir: {}",
            payload.log_path
        );
        // Log file should also exist on disk
        let logs = install.join("logs");
        assert!(logs.exists());
    }
```

- [ ] **Step 2: cargo test, verify FAIL**

```powershell
cd gui/src-tauri
cargo test --lib integrity 2>&1
```

Expected: コンパイル fail (`epoch_to_components` / `write_log` / `check_install_dir_with_paths` 未実装)。

- [ ] **Step 3: Implement minimal code**

[gui/src-tauri/src/integrity.rs](../../../gui/src-tauri/src/integrity.rs) に追加 (`check` の後、`mod tests` の前):

```rust
use std::io::Write as _;
use std::time::{SystemTime, UNIX_EPOCH};

/// Convert seconds since UNIX epoch into (year, month, day, hour, min, sec).
///
/// Self-contained Gregorian calendar arithmetic so we don't pull in the
/// chrono / time crate just for log-file naming. Tested against known
/// Unix timestamps including leap years.
fn epoch_to_components(secs: u64) -> (u32, u32, u32, u32, u32, u32) {
    let sec = (secs % 60) as u32;
    let total_min = secs / 60;
    let min = (total_min % 60) as u32;
    let total_hour = total_min / 60;
    let hour = (total_hour % 24) as u32;
    let total_days = total_hour / 24;

    let mut year = 1970u32;
    let mut day_of_year = total_days as u32;
    loop {
        let dim = if is_leap(year) { 366 } else { 365 };
        if day_of_year < dim {
            break;
        }
        day_of_year -= dim;
        year += 1;
    }
    let mut month = 1u32;
    let mut day = day_of_year + 1;
    let months_days: [u32; 12] = if is_leap(year) {
        [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    } else {
        [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    };
    for &md in &months_days {
        if day <= md {
            break;
        }
        day -= md;
        month += 1;
    }
    (year, month, day, hour, min, sec)
}

fn is_leap(year: u32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

fn now_components() -> (u32, u32, u32, u32, u32, u32) {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    epoch_to_components(secs)
}

fn log_filename() -> String {
    let (y, mo, d, _, _, _) = now_components();
    format!("error-{:04}{:02}{:02}.log", y, mo, d)
}

fn iso8601_now() -> String {
    let (y, mo, d, h, mi, s) = now_components();
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        y, mo, d, h, mi, s
    )
}

fn log_path(install_dir: &Path) -> std::path::PathBuf {
    install_dir.join("logs").join(log_filename())
}

/// Append an integrity-failure record to <install dir>/logs/error-YYYYMMDD.log.
pub(crate) fn write_log(
    install_dir: &Path,
    missing: &[String],
    size_mismatch: &[SizeMismatch],
) -> std::io::Result<()> {
    let logs_dir = install_dir.join("logs");
    fs::create_dir_all(&logs_dir)?;
    let path = logs_dir.join(log_filename());
    let mut f = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)?;
    let now = iso8601_now();
    let missing_json = serde_json::to_string(missing).unwrap_or_else(|_| "[]".into());
    let size_json = serde_json::to_string(size_mismatch).unwrap_or_else(|_| "[]".into());
    writeln!(
        f,
        "{} [error] integrity check failed: missing={}; size_mismatch={}",
        now, missing_json, size_json
    )?;
    Ok(())
}

/// Production-side wrapper: resolves the install dir from `current_exe`,
/// runs `check`, writes the log on failure, and fills `log_path`.
///
/// Returns `None` on success / skip / when install dir cannot be resolved
/// (best-effort fallback so a misconfigured launcher doesn't deadlock the
/// app — debug builds always go through this None path via the cfg gate
/// in `lib.rs::run`).
pub fn check_install_dir() -> Option<IntegrityErrorPayload> {
    let exe = std::env::current_exe().ok()?;
    let install_dir = exe.parent()?.to_path_buf();
    let manifest_path = install_dir.join("integrity-manifest.json");
    check_install_dir_with_paths(&manifest_path, &install_dir)
}

/// Test-friendly variant: explicit manifest_path / install_dir args so the
/// integration tests can drive the full path without invoking
/// `current_exe`.
pub(crate) fn check_install_dir_with_paths(
    manifest_path: &Path,
    install_dir: &Path,
) -> Option<IntegrityErrorPayload> {
    match check(manifest_path, install_dir) {
        Ok(()) => None,
        Err(mut payload) => {
            // Best-effort log write; failure does not change the outcome.
            let _ = write_log(install_dir, &payload.missing, &payload.size_mismatch);
            payload.log_path = log_path(install_dir).to_string_lossy().into_owned();
            Some(payload)
        }
    }
}
```

- [ ] **Step 4: cargo test PASS 確認**

```powershell
cd gui/src-tauri
cargo test --lib integrity 2>&1
cargo clippy --lib --no-deps -- -D warnings 2>&1
```

Expected: 全 13 件 pass、clippy clean。

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/integrity.rs
git commit -F - <<'EOF'
feat(rust/integrity): write_log + check_install_dir wrapper (Refs #668)

新 dep を避けつつ epoch_to_components で UTC 日時計算 (chrono 不要、
うるう年対応 + cargo test 担保)。write_log で <install dir>/logs/
error-YYYYMMDD.log に Python 側と同 record format で append。
check_install_dir で current_exe からの install dir 解決 + check +
log + log_path 埋込を一気通貫し、lib.rs から呼ぶ wrapper として
完成。

cargo test (5 件追加で計 13) で date helper / write_log / wrapper
happy / wrapper failure を担保。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 14: `lib.rs` setup hook 統合

`mod integrity;` を追加し、`pub fn run()` 内で `#[cfg(not(debug_assertions))]` ガードのもとで `integrity::check_install_dir()` を呼ぶ。失敗時は `panic-from-previous-session` と同パターンで `tokio::async_runtime::spawn` + 150ms sleep + `app_handle.emit("integrity-error", payload)`。

**Files:**

- Modify: `gui/src-tauri/src/lib.rs`

- [ ] **Step 1: Write the failing test**

`lib.rs` の startup hook はインプロセス Tauri lifecycle に依存するため pure unit test 困難。本 task は 「コンパイル成立 + cargo check + 既存 test 不退行 + 新 cfg-gated 部分の syntactical 確認」を verify とする。

具体: `lib.rs` に `mod integrity;` を追加し、`pub fn run()` 内で integrity 呼出ブロックを追加した後、以下を verify:

```powershell
cd gui/src-tauri
cargo check --lib 2>&1
cargo test --lib 2>&1
cargo clippy --lib --no-deps -- -D warnings 2>&1
```

(もし可能なら、別途 `tokio::test` で `integrity::check_install_dir` の return 形を確認する unit test を Task 13 に含めて完結済み。lib.rs 側は thin wrapper のため統合 test で覆う。)

- [ ] **Step 2: 既存 cargo test を実行して baseline (PASS) を確認**

```powershell
cd gui/src-tauri
cargo test --lib 2>&1
```

Expected: 既存 test が全 pass。

- [ ] **Step 3: Implement code**

[gui/src-tauri/src/lib.rs](../../../gui/src-tauri/src/lib.rs) を修正:

(a) line 25 周辺の `mod` 宣言を以下に置き換え:

```rust
mod error;
mod integrity;  // #668 -- bundled file integrity check (release builds only)
mod logging;
```

(b) line 2704-2716 (`pub fn run()` 冒頭) の `restart_panic_msg` 解決の **直後** に追加:

```rust
    let restart_panic_msg = logging::detect_panic_from_previous_session();
    eprintln!(
        "[startup] previous-session panic detected: {}",
        restart_panic_msg.is_some()
    );

    // #668 -- Integrity check (release builds only). The check itself runs
    // synchronously here so the result is captured for the setup hook to
    // emit after the webview is ready. Debug builds always get None via the
    // cfg gate so `npm run tauri dev` works without a built payload.
    #[cfg(not(debug_assertions))]
    let integrity_failure = integrity::check_install_dir();
    #[cfg(debug_assertions)]
    let integrity_failure: Option<integrity::IntegrityErrorPayload> = None;
    eprintln!(
        "[startup] integrity-check failure: {}",
        integrity_failure.is_some()
    );
```

(c) line 2730-2736 (`if let Some(panic_line) = restart_panic_msg.clone() { ... }` ブロック) の **直後** に追加:

```rust
            // #668 -- emit integrity-error after the webview has had a
            // chance to attach its listener (same 150ms idiom as the
            // panic-from-previous-session emit above).
            if let Some(payload) = integrity_failure.clone() {
                let app_handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    tokio::time::sleep(std::time::Duration::from_millis(150)).await;
                    let _ = app_handle.emit("integrity-error", payload);
                });
            }
```

- [ ] **Step 4: cargo check / cargo test / clippy 全 pass を確認**

```powershell
cd gui/src-tauri
cargo check --lib 2>&1
cargo test --lib 2>&1
cargo clippy --lib --no-deps -- -D warnings 2>&1
```

Expected: 全 pass、warnings 0。

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/lib.rs
git commit -F - <<'EOF'
feat(rust): lib.rs 起動時に integrity check を実行 + emit (Refs #668)

mod integrity を追加し、release build (#[cfg(not(debug_assertions))])
でのみ integrity::check_install_dir を起動冒頭で実行。失敗時は
panic-from-previous-session と同 idiom (tokio::spawn + 150ms +
app.emit) で `integrity-error` Tauri event に IntegrityErrorPayload
を載せて飛ばす。debug build では always None で skip。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 15: `errorStore.ts` `ErrorCategory` に `'integrity'` 追加

**Files:**

- Modify: `gui/src/state/errorStore.ts:8-13`
- Test: `gui/src/state/errorStore.test.ts`

- [ ] **Step 1: Write the failing test**

[gui/src/state/errorStore.test.ts](../../../gui/src/state/errorStore.test.ts) を読んで pattern 把握、新 test 追加:

```typescript
import { describe, it, expect, beforeEach } from 'vitest';

import { useErrorStore } from './errorStore';

describe('errorStore integrity category (#668)', () => {
  beforeEach(() => {
    useErrorStore.getState().dismissError();
  });

  it("accepts errorCategory: 'integrity'", () => {
    useErrorStore.getState().showError({
      errorTitle: '同梱物の検証に失敗しました',
      errorMessage: '1 missing, 0 size mismatch',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });

    expect(useErrorStore.getState().errorCategory).toBe('integrity');
    expect(useErrorStore.getState().isPanic).toBe(true);
    expect(useErrorStore.getState().isRecoverable).toBe(false);
  });
});
```

- [ ] **Step 2: Run vitest, verify FAIL**

```bash
cd gui
npm test -- src/state/errorStore.test.ts
```

Expected: TypeScript error / test failure (`'integrity'` is not assignable to `ErrorCategory`).

- [ ] **Step 3: Implement code**

[gui/src/state/errorStore.ts](../../../gui/src/state/errorStore.ts) line 8-13 を以下に置き換え:

```typescript
/**
 * #614: Categorizes the source of an unrecoverable error so the ErrorModal
 * can pick an appropriate title / hint, and analytics-style log entries can
 * tell paths apart.
 *
 * #668: 'integrity' added for bundled-file corruption detection at startup
 * (Rust integrity::check / Python allaganeye.integrity.check). Treated as
 * isPanic=true (modal close exits the app) + isRecoverable=false.
 */
export type ErrorCategory =
  | 'panic'
  | 'js-error'
  | 'js-promise'
  | 'tauri-command'
  | 'previous-session-panic'
  | 'integrity';
```

- [ ] **Step 4: vitest + typecheck PASS 確認**

```bash
cd gui
npm test -- src/state/errorStore.test.ts
npm run typecheck
npm run lint
```

Expected: 全 pass。

- [ ] **Step 5: Commit**

```bash
git add gui/src/state/errorStore.ts gui/src/state/errorStore.test.ts
git commit -F - <<'EOF'
feat(errorStore): ErrorCategory に 'integrity' 追加 (Refs #668)

Portable ZIP 同梱物の検証失敗 category。useErrorStore.showError で
isPanic=true / isRecoverable=false を組み合わせると既存 ErrorModal
が「アプリを終了」専用 modal として動作する。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 16: `ErrorModal.tsx` `errorCategory==='integrity'` 表示分岐

`integrity` category 時には:

- title: 「同梱物の検証に失敗しました」 (errorTitle で上書き済なら spec 通り採用)
- hint: 「Portable ZIP を再展開してください。」を `errorHint` で受けて表示
- 追加 description: missing / size_mismatch を errorMessage に整形して受ける (Task 17 で formatter)

既存 modal は `isPanic=true` で「アプリを終了」 button 表示、`isRecoverable=false` で「閉じる」 button 非表示。`logDir` set で「ログフォルダを開く」表示。これらは reuse して、文言だけ category 対応にする。

**Files:**

- Modify: `gui/src/components/ErrorModal.tsx`
- Test: `gui/src/components/ErrorModal.test.tsx`

- [ ] **Step 1: Write the failing test**

[gui/src/components/ErrorModal.test.tsx](../../../gui/src/components/ErrorModal.test.tsx) (既存) に新規 test 追加:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';

import { useErrorStore } from '../state/errorStore';
import { ErrorModal } from './ErrorModal';

describe('ErrorModal integrity category (#668)', () => {
  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
  });

  it('renders integrity-specific default title when no override given', () => {
    useErrorStore.getState().showError({
      errorMessage: '1 missing, 0 size mismatch',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });

    render(<ErrorModal />);

    // Default title for integrity category
    expect(screen.getByText('同梱物の検証に失敗しました')).toBeInTheDocument();
  });

  it('shows the close-app button (isPanic) and hides the dismiss button (isRecoverable=false)', () => {
    useErrorStore.getState().showError({
      errorTitle: '同梱物の検証に失敗しました',
      errorMessage: '1 missing, 0 size mismatch',
      errorHint: 'Portable ZIP を再展開してください。',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });

    render(<ErrorModal />);

    expect(screen.getByRole('button', { name: 'アプリを終了' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '閉じる' })).not.toBeInTheDocument();
  });

  it('displays the re-extract hint from errorHint', () => {
    useErrorStore.getState().showError({
      errorMessage: '1 missing',
      errorHint: 'Portable ZIP を再展開してください。',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });

    render(<ErrorModal />);

    expect(screen.getByText('Portable ZIP を再展開してください。')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run vitest, verify FAIL**

```bash
cd gui
npm test -- src/components/ErrorModal.test.tsx
```

Expected: 1-2 件 FAIL (`同梱物の検証に失敗しました` の default title 未実装)。

- [ ] **Step 3: Implement code**

[gui/src/components/ErrorModal.tsx](../../../gui/src/components/ErrorModal.tsx) line 49-54 (defaultTitle 計算部分) を以下に置き換え:

```tsx
  if (!errorOpen) return null;

  // #614 / #668: per-category default titles. errorTitle override always wins.
  let defaultTitle: string;
  if (errorCategory === 'integrity') {
    defaultTitle = '同梱物の検証に失敗しました';
  } else if (isPanic) {
    defaultTitle = 'アプリ内部でエラーが発生しました';
  } else {
    defaultTitle = '予期しないエラーが発生しました';
  }
  const title = errorTitle || defaultTitle;
```

> **注意**: 既存 buttons (詳細をコピー / ログフォルダを開く / 閉じる / アプリを終了) と `errorHint` 表示はそのまま reuse。`integrity` category は `isPanic=true` でアプリを終了が出る、`isRecoverable=false` で閉じるが消える、これは既存 logic で自動的に達成される。文言系の追加変更なし。

- [ ] **Step 4: vitest + a11y PASS 確認**

```bash
cd gui
npm test -- src/components/ErrorModal.test.tsx
npm run typecheck
npm run lint
```

Expected: 全 pass、a11y test (jest-axe) 退行なし。

- [ ] **Step 5: Commit**

```bash
git add gui/src/components/ErrorModal.tsx gui/src/components/ErrorModal.test.tsx
git commit -F - <<'EOF'
feat(ErrorModal): 'integrity' category の default title 分岐 (Refs #668)

errorCategory === 'integrity' 時に「同梱物の検証に失敗しました」を
default title として表示。既存 isPanic / isRecoverable / logDir
button 制御は reuse、文言以外の振る舞いは category 不変。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 17: `globalErrorListener.ts` で `integrity-error` event を listen → `useErrorStore.showError`

Tauri event `integrity-error` を受けて `IntegrityErrorPayload` を modal payload に整形 + `setLogDir`。既存 `previous-session-panic` listener の pattern に倣う。

**Files:**

- Modify: `gui/src/lib/globalErrorListener.ts`
- Test: `gui/src/lib/globalErrorListener.test.ts`

- [ ] **Step 1: Write the failing test**

[gui/src/lib/globalErrorListener.test.ts](../../../gui/src/lib/globalErrorListener.test.ts) を読んで mock pattern を把握 (既存 `panic` / `panic-from-previous-session` の test がある)。新 test 追加:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { useErrorStore } from '../state/errorStore';

vi.mock('@tauri-apps/api/event', () => {
  const handlers: Record<string, ((event: { payload: unknown }) => void)[]> = {};
  return {
    listen: vi.fn(async (event: string, handler: (e: { payload: unknown }) => void) => {
      handlers[event] = handlers[event] ?? [];
      handlers[event].push(handler);
      return () => {
        handlers[event] = (handlers[event] ?? []).filter((h) => h !== handler);
      };
    }),
    __emit: (event: string, payload: unknown) => {
      (handlers[event] ?? []).forEach((h) => h({ payload }));
    },
  };
});

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(async () => '/fake/log/dir'),
}));

import * as eventModule from '@tauri-apps/api/event';
import { installGlobalErrorListener } from './globalErrorListener';

describe('integrity-error event (#668)', () => {
  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
  });

  it('shows ErrorModal with integrity category when integrity-error fires', async () => {
    installGlobalErrorListener();
    // Wait for listen() promises to resolve
    await Promise.resolve();
    await Promise.resolve();

    (eventModule as unknown as { __emit: (e: string, p: unknown) => void }).__emit(
      'integrity-error',
      {
        missing: ['lib/allaganeye/audio/refs/fanfare.npz'],
        sizeMismatch: [],
        logPath: '/install/logs/error-20260508.log',
      },
    );

    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorCategory).toBe('integrity');
    expect(state.isPanic).toBe(true);
    expect(state.isRecoverable).toBe(false);
    expect(state.errorMessage).toContain('lib/allaganeye/audio/refs/fanfare.npz');
    expect(state.logDir).toContain('/install/logs');
  });

  it('formats both missing and size_mismatch arrays in errorMessage', async () => {
    installGlobalErrorListener();
    await Promise.resolve();
    await Promise.resolve();

    (eventModule as unknown as { __emit: (e: string, p: unknown) => void }).__emit(
      'integrity-error',
      {
        missing: ['ffmpeg/ffmpeg.exe'],
        sizeMismatch: [
          { path: 'allaganeye-gui.exe', expected: 1000, actual: 500 },
        ],
        logPath: '/install/logs/error-20260508.log',
      },
    );

    const msg = useErrorStore.getState().errorMessage ?? '';
    expect(msg).toContain('ffmpeg/ffmpeg.exe');
    expect(msg).toContain('allaganeye-gui.exe');
    expect(msg).toContain('1000');
    expect(msg).toContain('500');
  });
});
```

- [ ] **Step 2: Run vitest, verify FAIL**

```bash
cd gui
npm test -- src/lib/globalErrorListener.test.ts
```

Expected: FAIL (`integrity-error` listener 未実装)。

- [ ] **Step 3: Implement code**

[gui/src/lib/globalErrorListener.ts](../../../gui/src/lib/globalErrorListener.ts) に追加:

(a) ファイル冒頭、既存 `interface PanicPayload` 直後に追加:

```typescript
/**
 * #668: Payload sent from Rust `integrity::check_install_dir` via the
 * `integrity-error` Tauri event. Field names are camelCase (Rust side
 * uses #[serde(rename_all = "camelCase")]).
 */
interface IntegritySizeMismatch {
  path: string;
  expected: number;
  actual: number;
}

interface IntegrityErrorPayload {
  missing: string[];
  sizeMismatch: IntegritySizeMismatch[];
  logPath: string;
}

function formatIntegrityMessage(payload: IntegrityErrorPayload): string {
  const lines: string[] = [];
  if (payload.missing.length > 0) {
    lines.push(`欠落しているファイル (${payload.missing.length} 件):`);
    for (const p of payload.missing) {
      lines.push(`  - ${p}`);
    }
  }
  if (payload.sizeMismatch.length > 0) {
    lines.push(`サイズ不一致 (${payload.sizeMismatch.length} 件):`);
    for (const sm of payload.sizeMismatch) {
      lines.push(`  - ${sm.path} (expected ${sm.expected} bytes, actual ${sm.actual} bytes)`);
    }
  }
  return lines.join('\n');
}

function logDirOf(logPath: string): string {
  const idx = Math.max(logPath.lastIndexOf('/'), logPath.lastIndexOf('\\'));
  return idx >= 0 ? logPath.slice(0, idx) : logPath;
}
```

(b) `installGlobalErrorListener` 内、既存 `panic-from-previous-session` listener の **直後** に追加:

```typescript
  void listen<IntegrityErrorPayload>('integrity-error', (event) => {
    const payload = event.payload;
    showError({
      errorTitle: '同梱物の検証に失敗しました',
      errorMessage: formatIntegrityMessage(payload),
      errorHint: 'Portable ZIP を再展開してください。',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });
    setLogDir(logDirOf(payload.logPath));
  })
    .then((un) => tauriUnlistens.push(un))
    .catch(() => {
      // not fatal in non-Tauri test envs
    });
```

- [ ] **Step 4: vitest + typecheck + lint PASS 確認**

```bash
cd gui
npm test -- src/lib/globalErrorListener.test.ts
npm run typecheck
npm run lint
```

Expected: 全 pass。

- [ ] **Step 5: Commit**

```bash
git add gui/src/lib/globalErrorListener.ts gui/src/lib/globalErrorListener.test.ts
git commit -F - <<'EOF'
feat(globalErrorListener): integrity-error event を listen (Refs #668)

Rust 側 emit("integrity-error", payload) を listen して
useErrorStore.showError({errorCategory:'integrity', isPanic:true,
isRecoverable:false}) に流す。formatIntegrityMessage で missing /
size_mismatch を日本語整形 + setLogDir で「ログフォルダを開く」 button
を有効化。既存 panic-from-previous-session listener と同 pattern。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 18: `release.yml` build-windows job に integrity-check fall-through E2E step

build-windows job の Smoke test 後に、payload を別ディレクトリにコピー → 1 file 削除 → CLI `--version` で exit code 7 を assert する step を追加。

**Files:**

- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: 設計レビュー (yaml は TDD 不可)**

`.github/workflows/release.yml` の build-windows job (line 64-214) を読み、以下を確認:

- 既存 step: `Build Portable ZIP -SkipArchive` (line 111-113) は `build/portable/allaganeye-v$version/` に payload を展開
- 既存 Smoke test (line 129-156): `--version` を `cmd.exe /c` 経由で実行、exit 0 を assert
- **追加位置**: Smoke test Level B (line 158-206) の **直後** + `actions/upload-artifact` (line 210-214) の **前**
- `$LASTEXITCODE = 0` で末尾自動 exit を抑止する idiom (line 184) を適用済み

- [ ] **Step 2: 既存 yaml を確認**

```bash
git diff origin/develop-0.2.0 -- .github/workflows/release.yml
```

Expected: 何も diff なし (current state は base と同期)。

- [ ] **Step 3: Implement code**

[.github/workflows/release.yml](../../../.github/workflows/release.yml) line 206 (`}` で終わる Smoke test Level B の最終 `Pop-Location`) と line 208 (`# Upload the expanded payload folder; ...` コメント) の間に、新 step を挿入:

```yaml
      # #668 -- Verify integrity-check fall-through in release builds:
      # copy payload, remove a known bundled file, run --version, assert
      # exit code 7. Confirms `#[cfg(not(debug_assertions))]` ガードが
      # release profile で有効化されていることと、`integrity-manifest.json`
      # が build script で生成されていることをまとめて担保。
      - name: Smoke test (integrity-check fall-through, expect exit 7)
        shell: pwsh
        run: |
          $PSNativeCommandUseErrorActionPreference = $false
          $version = '${{ needs.version-check.outputs.version }}'
          $payload = "build/portable/allaganeye-v$version"
          $verifyDir = "verify/allaganeye-v$version"

          # Copy payload to a sibling dir so artifact upload is unaffected.
          if (Test-Path verify) { Remove-Item -Recurse -Force verify }
          New-Item -ItemType Directory -Force -Path verify | Out-Null
          Copy-Item -Recurse "$payload" "verify/" -Force

          # Sanity: integrity-manifest.json must exist in the verify copy.
          $manifest = Join-Path $verifyDir 'integrity-manifest.json'
          if (-not (Test-Path $manifest)) {
            throw "integrity-manifest.json not found in built payload: $manifest"
          }

          # Remove a bundled file the manifest is known to track.
          $victim = Join-Path $verifyDir 'lib\allaganeye\audio\refs\fanfare.npz'
          if (-not (Test-Path $victim)) {
            throw "expected bundled file not present (build broken?): $victim"
          }
          Remove-Item -Force $victim

          # Drive --version and capture the exit code without auto-stop.
          Push-Location $verifyDir
          try {
            $output = '' | & cmd.exe /c "allaganeye.bat --version 2>&1"
            $exitCode = $LASTEXITCODE
            $LASTEXITCODE = 0  # release.yml 既存 idiom: native 戻り値を step 末尾 auto-exit に伝播させない
            Write-Host '--- integrity-check --version output ---'
            Write-Host ($output | Out-String)
            Write-Host "--- exit code: $exitCode (expected 7) ---"
            if ($exitCode -ne 7) {
              throw "integrity check did not produce exit code 7 (got $exitCode)"
            }
          }
          finally {
            Pop-Location
          }

          # Cleanup so the verify copy doesn't pollute the actions/upload-artifact step.
          Remove-Item -Recurse -Force verify
```

- [ ] **Step 4: yaml 構文 verify (local)**

```powershell
# yamllint があれば
yamllint .github/workflows/release.yml

# または yaml.parser で構文 check (Python)
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml').read())"
```

Expected: エラーなし (yaml が valid)。

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml
git commit -F - <<'EOF'
ci: build-windows に integrity-check fall-through E2E を追加 (Refs #668)

payload を verify/ に copy し、lib/allaganeye/audio/refs/fanfare.npz を
削除して allaganeye.bat --version を実行 → exit code 7 を assert。
release profile build で #[cfg(not(debug_assertions))] が effective
になっていること、build-portable-zip.ps1 が integrity-manifest.json を
生成していること、CLI 側 IntegrityError 経路が exit 7 を返すことを
1 step でまとめて担保する。

LASTEXITCODE = 0 で step 末尾 auto-exit 抑制の既存 idiom を踏襲。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 19: docs `system-architecture.md` + `cli-spec.md` 更新

**Files:**

- Modify: `docs/system-architecture.md` (§配布 セクション)
- Modify: `docs/cli-spec.md` (exit code 表)

- [ ] **Step 1: 既存 docs を確認**

```bash
grep -n "^## \|^### \|exit code\|integrity" docs/system-architecture.md docs/cli-spec.md
```

`docs/system-architecture.md` の §配布 セクション位置と書式を把握。`docs/cli-spec.md` の exit code 表位置と書式を把握。

- [ ] **Step 2: markdownlint baseline を取る**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 既存 lint pass (baseline)。

- [ ] **Step 3: Implement code (docs)**

(a) [docs/system-architecture.md](../../../docs/system-architecture.md) §配布 セクション (該当 section を grep で見つけて) の末尾に追加:

```markdown
### Portable ZIP 起動時健全性チェック (#668)

Portable ZIP 内の `integrity-manifest.json` を起動時に読み、同梱物
(ffmpeg / Python embed / fanfare.npz / GUI exe / CLI Python パッケージ)
の存在と size を高速 check (~50ms 以内、SHA256 等は対象外) する。

- **build 時**: `scripts/build-portable-zip.ps1` の `New-IntegrityManifest`
  関数が payload 全 file を `Get-ChildItem -Recurse -File` で自動 enum
  し、relative path / size / `tolerance_bytes=0` の JSON を生成。manifest
  自身は除外。
- **GUI (Rust release build only)**: `gui/src-tauri/src/integrity.rs::check_install_dir`
  が `<install dir>/integrity-manifest.json` を読み、失敗時は Tauri
  event `integrity-error` を `tokio::async_runtime::spawn` + 150ms +
  `app.emit` で frontend に飛ばす。frontend
  `gui/src/lib/globalErrorListener.ts` が listen して
  `useErrorStore.showError({errorCategory:'integrity', isPanic:true,
  isRecoverable:false})` に integrate、既存 `ErrorModal` が「アプリを
  終了」「ログフォルダを開く」 button 付きで blocking 表示。
- **CLI (Python)**: `allaganeye/integrity.py::check` が同 manifest を
  読み、`allaganeye/cli.py::version_callback` が `--version` 実行時に
  呼ぶ。失敗時は `IntegrityError(exit_code=7)` raise → CLI は
  exit code 7 + stderr 短メッセージ + log 書込 + `sys.exit(7)`。
- **dev mode skip**: Rust = `#[cfg(not(debug_assertions))]` (release
  build のみ動作)、Python = env `ALLAGANEYE_INTEGRITY_SKIP=1`。
- **log**: `<install dir>/logs/error-YYYYMMDD.log` (plain text、append、
  Python / Rust で同 record format)。書込み失敗は silent fail (modal /
  exit code が primary channel)。
- **CI 担保**: `.github/workflows/release.yml` build-windows job で payload
  を copy → 1 file 削除 → `allaganeye.bat --version` → exit code 7 を
  assert する E2E step。
```

(b) [docs/cli-spec.md](../../../docs/cli-spec.md) の exit code 表に新行を追加 (既存 表の末尾、code 順で 6 の後):

```markdown
| 7 | 同梱物欠損 (Portable ZIP integrity-manifest.json で listed file が missing / size 不一致) #668 |
```

- [ ] **Step 4: markdownlint + 内部 link 確認**

```bash
bash scripts/check-markdownlint.sh
# 関連リンクが死んでないことを spot check
grep -n "integrity-manifest\|integrity::check" docs/system-architecture.md docs/cli-spec.md
```

Expected: lint pass、追記 link 切れなし。

- [ ] **Step 5: Commit**

```bash
git add docs/system-architecture.md docs/cli-spec.md
git commit -F - <<'EOF'
docs: integrity check 仕様 + exit code 7 を追記 (Refs #668)

system-architecture.md §配布 に build / GUI / CLI / dev skip / log /
CI 担保の 6 観点で詳細を、cli-spec.md exit code 表に code 7 を追記。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## 完了後 — PR 作成 (実装の最後)

19 task すべて完了して全 commit が `claude/funny-tereshkova-d355c8` ブランチに乗ったら、Iron Law 6 PR Pre-flight + path 別自動チェックを通してから PR を作る。

- [ ] **Pre-flight 1: base 取り込み確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

取り込み未済 commit があり、本 PR の touched files (`gui/src-tauri/src/lib.rs` / `scripts/build-portable-zip.ps1` / `.github/workflows/release.yml` / `allaganeye/cli.py` / `gui/src/components/ErrorModal.tsx` 等) と交差したら:

```bash
git merge origin/develop-0.2.0
# 自動チェック再実行
```

- [ ] **Pre-flight 2: 並行 worktree PR 重複確認**

```bash
gh pr list --search "668" --state all
```

上記コマンドで #668 を扱う他 PR がないことを確認する。

- [ ] **Pre-flight 3: Path 別自動チェック (全 path 対応)**

```bash
# Python
ruff check .
ruff format --check .
pyright
pytest

# GUI (cd gui)
cd gui
npm install
npm run lint
npm run typecheck
npm test
npm run build
cd ..

# Rust (cd gui/src-tauri)
cd gui/src-tauri
cargo check --lib
cargo test --lib
cargo clippy --lib --no-deps -- -D warnings
cd ../..

# Pester (Windows)
Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1

# markdown
bash scripts/check-markdownlint.sh
```

全部 pass を確認。

- [ ] **Pre-flight 4: Idios 実機検証依頼 (AskUserQuestion)**

GUI (Tauri) と CLI (`--version`) の実機検証は CI で覆えないため、`AskUserQuestion` で Idios に依頼。3 シナリオ:

1. 同梱物 1 つ削除 (例: `lib/allaganeye/audio/refs/fanfare.npz`) → `allaganeye-gui.exe` 起動 → `ErrorModal` 表示 + 「アプリを終了」「ログフォルダを開く」 button 動作 + `<install dir>/logs/error-YYYYMMDD.log` 書込み確認
2. 同梱物 1 つ削除 → `allaganeye.bat --version` → exit code 7 + stderr 短メッセージ + log 書込
3. 健全状態 → `allaganeye-gui.exe` 起動 → 起動遅延 ~50ms 以内 (体感)

- [ ] **PR 作成**

PR 本文 template:

```markdown
## 概要

Lane IV-a §4 / #668: Portable ZIP 同梱物の起動時健全性チェック実装。

GUI (Rust release build) + CLI (`--version`) で `integrity-manifest.json`
を読み、同梱物の存在 + size 検証 + 失敗時 blocking modal / exit code 7 +
log 書込みを行う。

## 受け入れ条件 (元 issue #668 確認項目)

- [x] `allaganeye-gui.exe` 起動時に同梱バイナリの存在 + サイズ範囲を高速 check (... Idios 実機)
- [x] 失敗時はエラーモーダル + 「再展開してください」案内 + ログ保存 (Idios 実機 + vitest)
- [x] `allaganeye.bat --version` も同等チェック、CLI exit code 7 (build-windows job E2E)
- [x] チェック範囲は起動時の高速 check に限定、SHA256 等の重い検査は対象外 (実装方針)
- [x] `docs/system-architecture.md` §配布 に健全性チェック仕様を追記 (PR diff)
- [x] `docs/cli-spec.md` の exit code 表に code 7 追記 (PR diff)
- ... 健全状態で起動遅延 ~50ms 以内 (Idios 実機体感確認)

## 実装の説明

19 task / 19 commit。spec / plan は:
- spec: docs/superpowers/specs/2026-05-08-l2b-668-integrity-check-design.md
- plan: docs/superpowers/plans/2026-05-08-l2b-668-integrity-check-implementation.md

## Self-Test Report

- [x] ruff check / ruff format --check / pyright / pytest 全 pass
- [x] cd gui && npm run lint / typecheck / test / build 全 pass
- [x] cd gui/src-tauri && cargo check / test / clippy 全 pass
- [x] Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1 全 pass
- [x] markdownlint clean
- [x] git log HEAD..origin/develop-0.2.0 で取り込み未済 0 (Pre-flight 完了)
- [x] gh pr list --search "668" --state all で並行 PR なし
- (machine-unverifiable) Idios 実機検証 3 シナリオ全 pass

## 関連

- Refs #668
- 上位 plan: #683 (L2 v0.2.0 roadmap、Lane IV-a wave 0)
- 関連: #106 (parent / L2b ゼロ環境構築配布) / #527 (別 exe) / #570 #615 (Portable ZIP) / #661 (ErrorModal)
- session-id: funny-tereshkova-d355c8
```

PR 作成コマンド:

```bash
gh pr create \
  --base develop-0.2.0 \
  --head claude/funny-tereshkova-d355c8 \
  --title "feat: Portable ZIP 同梱物の起動時健全性チェック (Refs #668)" \
  --body-file - <<'PRBODY'
... (上記 template)
PRBODY
```

---

## 参考

- spec: [`docs/superpowers/specs/2026-05-08-l2b-668-integrity-check-design.md`](../specs/2026-05-08-l2b-668-integrity-check-design.md)
- 上位 plan: [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](2026-05-07-l2-v020-roadmap.md)
- l2-workflow: [`docs/l2-workflow.md`](../../l2-workflow.md)
- Iron Law: `.claude/hooks/session-start.sh`
- 関連 PR: [#661](https://github.com/Idios/kobutachan-allaganeye/pull/661) (`ErrorModal`) / [#675](https://github.com/Idios/kobutachan-allaganeye/pull/675) (StateSwitcher dev only)
