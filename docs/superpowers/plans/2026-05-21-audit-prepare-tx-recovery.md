# audit-prepare transactional crash recovery (Issue #800) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `audit-prepare` の publish 3-op swap (rmtree + rename + replace) に tx-state sidecar (`<label>.tx.json`) を追加し、crash 時に次 run が auto-recover する。

**Architecture:** `<label>.tx.json` が単一 canonical state (`"consistent"` / `"swapping"`)。Step 3 開始時に "swapping" を atomic 書き込み (`.tx.json.new` → `os.replace`)、3-op swap 完了後に "consistent" に更新。Step 0 で "swapping" を検出したら artifacts (`<label>/` + `<label>.csv` + `<label>.tx.json`) を全消去して regenerate。`audit-compare` は worksheet を読まないため tx-state を見る必要なし。

**Tech Stack:** Python 3.13 / pathlib / json / pytest / monkeypatch (failure injection) / ruff / pyright

**Spec:** [docs/superpowers/specs/2026-05-20-audit-prepare-tx-recovery-design.md](../specs/2026-05-20-audit-prepare-tx-recovery-design.md)

**Branch:** `claude/audit-tx-recovery-800` (already created, base = `origin/develop-0.3.0`)

---

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/audit-prepare.py` | tx-state 定数 + 3 helpers (`_read_tx_state` / `_write_tx_state_atomic` / `_recover_stale_artifacts`) + `main()` Step 0/3a/3e の組み込み。step (3) コメントブロック更新 |
| `tests/test_audit_prepare.py` | helpers 単体テスト (Task 1-3) + main() 統合テスト (Task 4-5) + failure-injection tests (Task 6) |
| `docs/v030-baseline-audit.md` | "Known limitation (Issue #800)" 節を「解消済み」に更新 |
| `docs/superpowers/specs/2026-05-20-audit-prepare-tx-recovery-design.md` | (既 commit、変更なし) |

---

## Task 1: `_read_tx_state` helper

**Files:**

- Modify: `scripts/audit-prepare.py` (add constants + helper near top, after imports)
- Test: `tests/test_audit_prepare.py` (add unit tests at end of file)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_audit_prepare.py`:

```python
# --- Issue #800: tx-state helpers ---


def test_read_tx_state_returns_none_when_missing(tmp_path, capsys):
    """File-not-exist is legacy / first-run case; no warning."""
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    assert mod._read_tx_state(tx_path) is None
    assert capsys.readouterr().err == ""


def test_read_tx_state_returns_consistent_state(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    tx_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "consistent",
                "updated_at": "2026-05-21T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    result = mod._read_tx_state(tx_path)
    assert result is not None
    assert result["state"] == "consistent"


def test_read_tx_state_returns_swapping_state(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    tx_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "swapping",
                "updated_at": "2026-05-21T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    result = mod._read_tx_state(tx_path)
    assert result is not None
    assert result["state"] == "swapping"


@pytest.mark.parametrize(
    "payload,variant",
    [
        ("not valid json{{{", "invalid_json"),
        ('["a", "b"]', "non_dict"),
        ('{"schema_version": 2, "state": "consistent"}', "unknown_schema_version"),
        ('{"schema_version": 1, "state": "unknown"}', "unknown_state"),
    ],
)
def test_tx_state_corrupted_treated_as_missing(tmp_path, capsys, payload, variant):
    """All 4 corrupted variants return None + warn on stderr."""
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    tx_path.write_text(payload, encoding="utf-8")
    result = mod._read_tx_state(tx_path)
    assert result is None, f"variant={variant}"
    err = capsys.readouterr().err
    assert "WARNING" in err, f"variant={variant} stderr: {err!r}"
    assert str(tx_path) in err, f"variant={variant} stderr: {err!r}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_audit_prepare.py::test_read_tx_state_returns_none_when_missing -v`
Expected: `FAILED` with `AttributeError: module 'audit_prepare' has no attribute '_read_tx_state'`

- [ ] **Step 3: Add constants + `_read_tx_state` to `scripts/audit-prepare.py`**

In `scripts/audit-prepare.py`, after line 42 (`_DEFAULT_WORKSHEET_DIR = ...`), add:

```python

# Issue #800: tx-state sidecar for transactional crash recovery.
# `<label>.tx.json` holds the single canonical state of the last publish;
# crash mid-publish is detected by next run via state == "swapping" and
# recovered by wiping artifacts before regenerating.
_TX_SCHEMA_VERSION = 1
_TX_STATE_CONSISTENT = "consistent"
_TX_STATE_SWAPPING = "swapping"
```

Then after `build_worksheet_rows` (around line 124), add:

```python


def _read_tx_state(tx_path: Path) -> dict[str, Any] | None:
    """Return parsed tx-state, or None if file missing / corrupted / unknown shape.

    Returning None means "no committed transactional state" (= no recovery
    needed). File-not-exist is the legacy / first-run case (silent); all
    other "missing-equivalent" cases warn on stderr so the operator can
    debug why their tx-state was ignored.
    """
    if not tx_path.exists():
        return None
    try:
        data = json.loads(tx_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"WARNING: {tx_path} is unreadable ({exc}); treating as missing",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print(
            f"WARNING: {tx_path} top-level is not an object; treating as missing",
            file=sys.stderr,
        )
        return None
    if data.get("schema_version") != _TX_SCHEMA_VERSION:
        print(
            f"WARNING: {tx_path} has unsupported schema_version "
            f"{data.get('schema_version')!r} (expected {_TX_SCHEMA_VERSION}); "
            "treating as missing",
            file=sys.stderr,
        )
        return None
    if data.get("state") not in (_TX_STATE_CONSISTENT, _TX_STATE_SWAPPING):
        print(
            f"WARNING: {tx_path} has unknown state {data.get('state')!r}; "
            "treating as missing",
            file=sys.stderr,
        )
        return None
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_audit_prepare.py -k "tx_state or read_tx_state" -v`
Expected: All 7 tests PASS (1 returns_none + 2 returns_state + 4 parametrized corrupted)

- [ ] **Step 5: Run lint + type checks**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: `All checks passed!`

Run: `ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: no diff. If format errors, run `ruff format scripts/audit-prepare.py tests/test_audit_prepare.py` to fix.

Run: `pyright scripts/audit-prepare.py`
Expected: `0 errors, 0 warnings, 0 informations`

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #800 add _read_tx_state helper + tx-state constants

backwards-compat: file-not-exist は silent, JSON parse fail / non-dict /
unknown schema_version / unknown state は WARNING + None。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_write_tx_state_atomic` helper

**Files:**

- Modify: `scripts/audit-prepare.py` (add `datetime` import + helper after `_read_tx_state`)
- Test: `tests/test_audit_prepare.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_audit_prepare.py`:

```python


def test_write_tx_state_atomic_creates_file(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    mod._write_tx_state_atomic(tx_path, state="consistent")
    assert tx_path.exists()
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["state"] == "consistent"
    assert data["updated_at"].endswith("Z")  # ISO 8601 UTC


def test_write_tx_state_atomic_overwrites_existing(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    mod._write_tx_state_atomic(tx_path, state="swapping")
    mod._write_tx_state_atomic(tx_path, state="consistent")
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"


def test_write_tx_state_atomic_cleans_up_new_suffix(tmp_path):
    """No `.tx.json.new` should remain after successful write."""
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    mod._write_tx_state_atomic(tx_path, state="consistent")
    assert tx_path.exists()
    assert not (tmp_path / "obs.tx.json.new").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_audit_prepare.py::test_write_tx_state_atomic_creates_file -v`
Expected: `FAILED` with `AttributeError: module 'audit_prepare' has no attribute '_write_tx_state_atomic'`

- [ ] **Step 3: Add `datetime` import + helper to `scripts/audit-prepare.py`**

In `scripts/audit-prepare.py`, after `from concurrent.futures import ThreadPoolExecutor, as_completed` (around line 19), add:

```python
from datetime import datetime, timezone
```

After `_read_tx_state`, add:

```python


def _write_tx_state_atomic(tx_path: Path, *, state: str) -> None:
    """Atomically write tx-state via temp file + os.replace.

    On POSIX and Windows, replace() of a single file is atomic, so the
    on-disk tx-state is never partially-written. The temp file uses the
    `.new` suffix to match the existing artifact-staging convention.
    """
    payload = {
        "schema_version": _TX_SCHEMA_VERSION,
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    tx_new = tx_path.parent / (tx_path.name + ".new")
    tx_new.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tx_new.replace(tx_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_audit_prepare.py -k "write_tx_state_atomic" -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Verify existing tests still pass**

Run: `python -m pytest tests/test_audit_prepare.py -v`
Expected: All tests PASS (existing + new Task 1/2).

- [ ] **Step 6: Run lint + type checks**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: `All checks passed!`

Run: `ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: no diff.

Run: `pyright scripts/audit-prepare.py`
Expected: `0 errors`

- [ ] **Step 7: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #800 add _write_tx_state_atomic helper

`.tx.json.new` 経由の os.replace で single-file atomic 書き込み。
payload は schema_version=1 + state + ISO 8601 UTC updated_at。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_recover_stale_artifacts` helper

**Files:**

- Modify: `scripts/audit-prepare.py` (add helper after `_write_tx_state_atomic`)
- Test: `tests/test_audit_prepare.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_audit_prepare.py`:

```python


def test_recover_stale_artifacts_removes_all(tmp_path):
    mod = _load_module()
    per_boundary_dir = tmp_path / "obs"
    worksheet_csv = tmp_path / "obs.csv"
    tx_path = tmp_path / "obs.tx.json"

    per_boundary_dir.mkdir()
    (per_boundary_dir / "a.png").write_bytes(b"PNG")
    worksheet_csv.write_text("HEADER\n", encoding="utf-8")
    tx_path.write_text("{}", encoding="utf-8")

    mod._recover_stale_artifacts(
        per_boundary_dir=per_boundary_dir,
        worksheet_csv=worksheet_csv,
        tx_path=tx_path,
    )

    assert not per_boundary_dir.exists()
    assert not worksheet_csv.exists()
    assert not tx_path.exists()


def test_recover_stale_artifacts_idempotent_on_missing(tmp_path):
    """Helper must not raise when paths are already absent."""
    mod = _load_module()
    per_boundary_dir = tmp_path / "obs"
    worksheet_csv = tmp_path / "obs.csv"
    tx_path = tmp_path / "obs.tx.json"

    # All absent
    mod._recover_stale_artifacts(
        per_boundary_dir=per_boundary_dir,
        worksheet_csv=worksheet_csv,
        tx_path=tx_path,
    )


def test_recover_stale_artifacts_partial_state(tmp_path):
    """Helper handles 'dir exists but csv/tx absent' without error."""
    mod = _load_module()
    per_boundary_dir = tmp_path / "obs"
    worksheet_csv = tmp_path / "obs.csv"
    tx_path = tmp_path / "obs.tx.json"

    per_boundary_dir.mkdir()
    (per_boundary_dir / "a.png").write_bytes(b"PNG")

    mod._recover_stale_artifacts(
        per_boundary_dir=per_boundary_dir,
        worksheet_csv=worksheet_csv,
        tx_path=tx_path,
    )

    assert not per_boundary_dir.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_audit_prepare.py::test_recover_stale_artifacts_removes_all -v`
Expected: `FAILED` with `AttributeError: module 'audit_prepare' has no attribute '_recover_stale_artifacts'`

- [ ] **Step 3: Add `_recover_stale_artifacts` to `scripts/audit-prepare.py`**

After `_write_tx_state_atomic`, add:

```python


def _recover_stale_artifacts(
    *,
    per_boundary_dir: Path,
    worksheet_csv: Path,
    tx_path: Path,
) -> None:
    """Wipe artifacts when tx-state == swapping on startup.

    Idempotent. Does not raise on missing paths. Called from main() Step 0
    after _read_tx_state returns a swapping-state dict.
    """
    shutil.rmtree(per_boundary_dir, ignore_errors=True)
    worksheet_csv.unlink(missing_ok=True)
    tx_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_audit_prepare.py -k "recover_stale_artifacts" -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Run lint + type checks + full test sweep**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: `All checks passed!`

Run: `ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: no diff.

Run: `pyright scripts/audit-prepare.py`
Expected: `0 errors`

Run: `python -m pytest tests/test_audit_prepare.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #800 add _recover_stale_artifacts helper

`<label>/` + `<label>.csv` + `<label>.tx.json` を ignore_errors / missing_ok で
全消去するヘルパ。idempotent + 部分状態安全。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire tx-state marker into main() Step 3

**Files:**

- Modify: `scripts/audit-prepare.py` (main() — add `tx_path` + Step 3a/3e)
- Test: `tests/test_audit_prepare.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_audit_prepare.py`:

```python


def test_main_writes_tx_state_consistent_after_publish(tmp_path, monkeypatch):
    """After successful main() the tx-state file exists with state=consistent (#800)."""
    mod = _load_module()
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    metadata = {
        "schema_version": "1",
        "source": "20260116/fake.mkv",
        "matches": [
            {
                "index": 1,
                "start_time": 49.125,
                "end_time": 1054.5,
                "duration": 1005.375,
                "type": "fl_match",
            },
        ],
        "gaps": [],
    }
    (baseline_dir / "obs-fake.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    video_dir = tmp_path / "videos"
    (video_dir / "20260116").mkdir(parents=True)
    (video_dir / "20260116" / "fake.mkv").write_bytes(b"")
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)
    monkeypatch.setattr(mod, "export_sample_frames", lambda **kw: None)

    worksheet_dir = tmp_path / "audit-worksheet"
    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    tx_path = worksheet_dir / "obs-fake.tx.json"
    assert tx_path.exists()
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["state"] == "consistent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audit_prepare.py::test_main_writes_tx_state_consistent_after_publish -v`
Expected: `FAILED` because `obs-fake.tx.json` does not exist (main() does not yet write it)

- [ ] **Step 3: Modify `main()` in `scripts/audit-prepare.py`**

Find this block (around line 266-269):

```python
    per_boundary_dir = args.worksheet_dir / args.recording_label
    per_boundary_dir_new = args.worksheet_dir / f"{args.recording_label}.new"
    worksheet_csv = args.worksheet_dir / f"{args.recording_label}.csv"
    worksheet_csv_new = args.worksheet_dir / f"{args.recording_label}.csv.new"
```

Add a new line after it:

```python
    tx_path = args.worksheet_dir / f"{args.recording_label}.tx.json"
```

Find the step (3) swap block (around line 333-336):

```python
    if per_boundary_dir.exists():
        shutil.rmtree(per_boundary_dir)
    per_boundary_dir_new.rename(per_boundary_dir)
    worksheet_csv_new.replace(worksheet_csv)
```

Wrap it with tx-state markers:

```python
    args.worksheet_dir.mkdir(parents=True, exist_ok=True)
    _write_tx_state_atomic(tx_path, state=_TX_STATE_SWAPPING)
    if per_boundary_dir.exists():
        shutil.rmtree(per_boundary_dir)
    per_boundary_dir_new.rename(per_boundary_dir)
    worksheet_csv_new.replace(worksheet_csv)
    _write_tx_state_atomic(tx_path, state=_TX_STATE_CONSISTENT)
```

The `args.worksheet_dir.mkdir(parents=True, exist_ok=True)` line is required because `_write_tx_state_atomic` writes into `args.worksheet_dir`, which may not exist yet on first run (Step 1 only creates `<label>.new` subdir, not the parent). Without this, the test `test_main_writes_tx_state_consistent_after_publish` fails on first run with FileNotFoundError.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_audit_prepare.py::test_main_writes_tx_state_consistent_after_publish -v`
Expected: PASS.

- [ ] **Step 5: Verify all existing tests still pass**

Run: `python -m pytest tests/test_audit_prepare.py -v`
Expected: All tests PASS (existing 3 atomic-flow tests + Task 1/2/3 unit tests + this new test).

In particular, the existing tests `test_main_atomic_success_replaces_old_artifacts` and `test_main_recovers_from_stale_new_dir` should continue to pass (they don't read tx-state so they don't care about its presence).

- [ ] **Step 6: Run lint + type checks**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: `All checks passed!`

Run: `ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: no diff.

Run: `pyright scripts/audit-prepare.py`
Expected: `0 errors`

- [ ] **Step 7: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #800 wire tx-state marker into main() Step 3

Step 3a で "swapping" を atomic 書き込み、3-op swap 完了後 Step 3e で "consistent"
に更新。worksheet_dir.mkdir を Step 3 直前に追加 (`.tx.json` 親 dir 不在対応)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire Step 0 recovery + backwards-compat tests

**Files:**

- Modify: `scripts/audit-prepare.py` (main() — add Step 0 before Step 1)
- Test: `tests/test_audit_prepare.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_audit_prepare.py`:

```python


def _seed_baseline_for_main(tmp_path, monkeypatch, label="obs-fake"):
    """Helper: build a minimal baseline + video tree usable by main()."""
    mod = _load_module()
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir(exist_ok=True)
    metadata = {
        "schema_version": "1",
        "source": "20260116/fake.mkv",
        "matches": [
            {
                "index": 1,
                "start_time": 49.125,
                "end_time": 1054.5,
                "duration": 1005.375,
                "type": "fl_match",
            },
        ],
        "gaps": [],
    }
    (baseline_dir / f"{label}.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    video_dir = tmp_path / "videos"
    (video_dir / "20260116").mkdir(parents=True, exist_ok=True)
    (video_dir / "20260116" / "fake.mkv").write_bytes(b"")
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)
    monkeypatch.setattr(mod, "export_sample_frames", lambda **kw: None)
    return mod, baseline_dir


def test_main_step0_recovers_from_swapping_state(tmp_path, monkeypatch, capsys):
    """tx-state == 'swapping' on startup -> wipe + regenerate + WARNING (#800)."""
    mod, baseline_dir = _seed_baseline_for_main(tmp_path, monkeypatch)
    worksheet_dir = tmp_path / "audit-worksheet"
    worksheet_dir.mkdir()
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"
    tx_path = worksheet_dir / "obs-fake.tx.json"

    # Seed mid-crash state: tx="swapping", stale dir, stale csv
    per_boundary_dir.mkdir()
    (per_boundary_dir / "old.txt").write_text("OLD", encoding="utf-8")
    worksheet_csv.write_text("OLD_HEADER\n", encoding="utf-8")
    mod._write_tx_state_atomic(tx_path, state="swapping")

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    # Recovery happened: old wiped, new regenerated, tx="consistent"
    assert not (per_boundary_dir / "old.txt").exists()
    assert per_boundary_dir.exists()
    assert "OLD_HEADER" not in worksheet_csv.read_text(encoding="utf-8")
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"

    # WARNING was emitted on stderr
    err = capsys.readouterr().err
    assert "crashed mid-publish" in err


def test_tx_state_missing_legacy_compat(tmp_path, monkeypatch, capsys):
    """tx.json absent (legacy baseline) -> no recovery, normal regenerate (#800)."""
    mod, baseline_dir = _seed_baseline_for_main(tmp_path, monkeypatch)
    worksheet_dir = tmp_path / "audit-worksheet"
    worksheet_dir.mkdir()
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"

    # Seed legacy state: dir + csv exist but NO tx.json
    per_boundary_dir.mkdir()
    (per_boundary_dir / "legacy.txt").write_text("LEGACY", encoding="utf-8")
    worksheet_csv.write_text("LEGACY_HEADER\n", encoding="utf-8")

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    # Normal regenerate (legacy content overwritten by atomic swap)
    assert not (per_boundary_dir / "legacy.txt").exists()
    # No recovery WARNING in stderr
    err = capsys.readouterr().err
    assert "crashed mid-publish" not in err

    # tx.json is now created with state=consistent
    tx_path = worksheet_dir / "obs-fake.tx.json"
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"


def test_no_recovery_when_state_consistent(tmp_path, monkeypatch, capsys):
    """tx-state == 'consistent' on startup -> no recovery, normal regenerate (#800)."""
    mod, baseline_dir = _seed_baseline_for_main(tmp_path, monkeypatch)
    worksheet_dir = tmp_path / "audit-worksheet"
    worksheet_dir.mkdir()
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"
    tx_path = worksheet_dir / "obs-fake.tx.json"

    # Seed clean prior-run state
    per_boundary_dir.mkdir()
    (per_boundary_dir / "prev.txt").write_text("PREV", encoding="utf-8")
    worksheet_csv.write_text("PREV_HEADER\n", encoding="utf-8")
    mod._write_tx_state_atomic(tx_path, state="consistent")

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    # Normal regenerate (prev content overwritten by atomic swap)
    assert not (per_boundary_dir / "prev.txt").exists()
    # No recovery WARNING in stderr
    err = capsys.readouterr().err
    assert "crashed mid-publish" not in err

    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_audit_prepare.py::test_main_step0_recovers_from_swapping_state -v`
Expected: `FAILED` — recovery does not happen (Step 0 not yet wired); the swapping state is overwritten without the recovery WARNING being emitted, and the test fails on `assert "crashed mid-publish" in err`.

- [ ] **Step 3: Add Step 0 recovery to `main()` in `scripts/audit-prepare.py`**

Find this block in `main()` (after path setup, before Step 1 pre-clean — around line 270):

```python
    tx_path = args.worksheet_dir / f"{args.recording_label}.tx.json"

    # (1) Pre-clean any stale temp residue from a prior crashed run.
```

Insert Step 0 between `tx_path = ...` and the `# (1)` comment:

```python
    tx_path = args.worksheet_dir / f"{args.recording_label}.tx.json"

    # (0) Recovery-on-start: if a prior run crashed mid-publish, the
    # tx-state will be "swapping" and the on-disk artifacts are in an
    # unknown state. Wipe everything so Step 2 regenerates from scratch.
    # Backwards-compat: tx.json absent (legacy baseline) or "consistent"
    # (clean prior run) skips recovery.
    tx = _read_tx_state(tx_path)
    if tx is not None and tx["state"] == _TX_STATE_SWAPPING:
        print(
            f"WARNING: previous {args.recording_label} run crashed mid-publish; "
            "cleaning up stale artifacts before regenerating",
            file=sys.stderr,
        )
        _recover_stale_artifacts(
            per_boundary_dir=per_boundary_dir,
            worksheet_csv=worksheet_csv,
            tx_path=tx_path,
        )

    # (1) Pre-clean any stale temp residue from a prior crashed run.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_audit_prepare.py -k "step0 or legacy_compat or no_recovery_when" -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Verify all existing + new tests still pass**

Run: `python -m pytest tests/test_audit_prepare.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Run lint + type checks**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: `All checks passed!`

Run: `ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: no diff.

Run: `pyright scripts/audit-prepare.py`
Expected: `0 errors`

- [ ] **Step 7: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #800 wire Step 0 recovery into main()

tx.state == "swapping" を検出したら artifacts (`<label>/` + `<label>.csv` +
`<label>.tx.json`) を全消去 + WARNING を stderr に 1 行出力。tx.json 不在
(legacy baseline) と "consistent" は recovery skip (backwards compat)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Failure-injection tests for crash points W1 / W2 / before-commit

**Files:**

- Test: `tests/test_audit_prepare.py` (add 3 failure-injection tests)

これらの test は実装変更を伴わない (impl は Task 1-5 で完了済)。Task 1-5 の helpers / wiring が正しければ、失敗注入で crash → recovery cycle が成立することを確認する。test が落ちた場合は Task 1-5 の bug を意味するので、test 修正でなく impl 修正に回す。

- [ ] **Step 1: Write the 3 failure-injection tests**

Append to `tests/test_audit_prepare.py`:

```python


def test_recovers_from_crash_after_rmtree(tmp_path, monkeypatch, capsys):
    """W1 window: crash AFTER rmtree old per_boundary_dir, BEFORE rename .new.

    Mid-crash state: dir gone, csv old, tx.json "swapping".
    Next run: Step 0 sees "swapping" + wipes + regenerates.
    """
    mod, baseline_dir = _seed_baseline_for_main(tmp_path, monkeypatch)
    worksheet_dir = tmp_path / "audit-worksheet"
    worksheet_dir.mkdir()
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"
    tx_path = worksheet_dir / "obs-fake.tx.json"

    # Seed clean prior-run state
    per_boundary_dir.mkdir()
    (per_boundary_dir / "old.txt").write_text("OLD", encoding="utf-8")
    worksheet_csv.write_text("OLD_HEADER\n", encoding="utf-8")
    mod._write_tx_state_atomic(tx_path, state="consistent")

    # Inject crash: shutil.rmtree raises AFTER deleting per_boundary_dir once
    original_rmtree = mod.shutil.rmtree
    crashed = {"value": False}

    def crashing_rmtree(path, *args, **kwargs):
        original_rmtree(path, *args, **kwargs)
        if not crashed["value"] and Path(path) == per_boundary_dir:
            crashed["value"] = True
            raise RuntimeError("simulated crash after rmtree")

    monkeypatch.setattr(mod.shutil, "rmtree", crashing_rmtree)

    with pytest.raises(RuntimeError, match="simulated crash"):
        mod.main(
            [
                "obs-fake",
                "--baseline-dir",
                str(baseline_dir),
                "--worksheet-dir",
                str(worksheet_dir),
            ]
        )

    # Mid-crash state: tx="swapping", dir gone, csv still old
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "swapping"
    assert not per_boundary_dir.exists()
    assert worksheet_csv.read_text(encoding="utf-8") == "OLD_HEADER\n"

    # Restore rmtree for recovery run
    monkeypatch.setattr(mod.shutil, "rmtree", original_rmtree)

    # Re-run audit-prepare: Step 0 recovery
    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    # Recovered state: tx="consistent", regenerated artifacts
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"
    assert per_boundary_dir.exists()
    assert worksheet_csv.exists()
    assert "OLD_HEADER" not in worksheet_csv.read_text(encoding="utf-8")

    # WARNING was emitted
    err = capsys.readouterr().err
    assert "crashed mid-publish" in err


def test_recovers_from_crash_after_dir_rename(tmp_path, monkeypatch, capsys):
    """W2 window: crash AFTER per_boundary_dir_new.rename, BEFORE csv replace.

    Mid-crash state: new dir + old csv, tx.json "swapping".
    Next run: Step 0 wipes new dir + old csv + tx, regenerates.
    """
    mod, baseline_dir = _seed_baseline_for_main(tmp_path, monkeypatch)
    worksheet_dir = tmp_path / "audit-worksheet"
    worksheet_dir.mkdir()
    per_boundary_dir = worksheet_dir / "obs-fake"
    per_boundary_dir_new = worksheet_dir / "obs-fake.new"
    worksheet_csv = worksheet_dir / "obs-fake.csv"
    tx_path = worksheet_dir / "obs-fake.tx.json"

    # Seed clean prior-run state
    per_boundary_dir.mkdir()
    (per_boundary_dir / "old.txt").write_text("OLD", encoding="utf-8")
    worksheet_csv.write_text("OLD_HEADER\n", encoding="utf-8")
    mod._write_tx_state_atomic(tx_path, state="consistent")

    # Inject crash: Path.rename raises AFTER renaming per_boundary_dir_new -> per_boundary_dir
    original_rename = Path.rename
    crashed = {"value": False}

    def crashing_rename(self, target, *args, **kwargs):
        result = original_rename(self, target, *args, **kwargs)
        if (
            not crashed["value"]
            and Path(self) == per_boundary_dir_new
            and Path(target) == per_boundary_dir
        ):
            crashed["value"] = True
            raise RuntimeError("simulated crash after dir rename")
        return result

    monkeypatch.setattr(Path, "rename", crashing_rename)

    with pytest.raises(RuntimeError, match="simulated crash"):
        mod.main(
            [
                "obs-fake",
                "--baseline-dir",
                str(baseline_dir),
                "--worksheet-dir",
                str(worksheet_dir),
            ]
        )

    # Mid-crash state: tx="swapping", new dir present, old csv still there
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "swapping"
    assert per_boundary_dir.exists()
    assert not (per_boundary_dir / "old.txt").exists()  # new content
    assert worksheet_csv.read_text(encoding="utf-8") == "OLD_HEADER\n"

    # Restore rename for recovery run
    monkeypatch.setattr(Path, "rename", original_rename)

    # Re-run audit-prepare: Step 0 recovery
    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    # Recovered state
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"
    assert per_boundary_dir.exists()
    assert worksheet_csv.exists()
    assert "OLD_HEADER" not in worksheet_csv.read_text(encoding="utf-8")

    err = capsys.readouterr().err
    assert "crashed mid-publish" in err


def test_recovers_from_crash_before_tx_commit(tmp_path, monkeypatch, capsys):
    """crash AFTER csv replace, BEFORE final tx="consistent" write.

    Mid-crash state: new dir + new csv, tx.json still "swapping" (= wasteful regenerate).
    Next run: Step 0 wipes everything + regenerates (content correct but tx not committed).
    """
    mod, baseline_dir = _seed_baseline_for_main(tmp_path, monkeypatch)
    worksheet_dir = tmp_path / "audit-worksheet"
    worksheet_dir.mkdir()
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"
    tx_path = worksheet_dir / "obs-fake.tx.json"

    # Seed clean prior-run state
    per_boundary_dir.mkdir()
    (per_boundary_dir / "old.txt").write_text("OLD", encoding="utf-8")
    worksheet_csv.write_text("OLD_HEADER\n", encoding="utf-8")
    mod._write_tx_state_atomic(tx_path, state="consistent")

    # Inject crash: _write_tx_state_atomic raises on the 2nd call (consistent commit)
    original_write = mod._write_tx_state_atomic
    call_count = {"value": 0}

    def crashing_write(path, *, state):
        call_count["value"] += 1
        if call_count["value"] == 2 and state == "consistent":
            raise RuntimeError("simulated crash before tx commit")
        original_write(path, state=state)

    monkeypatch.setattr(mod, "_write_tx_state_atomic", crashing_write)

    with pytest.raises(RuntimeError, match="simulated crash before tx commit"):
        mod.main(
            [
                "obs-fake",
                "--baseline-dir",
                str(baseline_dir),
                "--worksheet-dir",
                str(worksheet_dir),
            ]
        )

    # Mid-crash state: tx still "swapping", new dir + new csv on disk
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "swapping"
    assert per_boundary_dir.exists()
    assert not (per_boundary_dir / "old.txt").exists()  # new content
    assert "OLD_HEADER" not in worksheet_csv.read_text(encoding="utf-8")

    # Restore for recovery run
    monkeypatch.setattr(mod, "_write_tx_state_atomic", original_write)

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    # Recovered state
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"
    assert per_boundary_dir.exists()
    assert worksheet_csv.exists()

    err = capsys.readouterr().err
    assert "crashed mid-publish" in err
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_audit_prepare.py -k "recovers_from_crash" -v`
Expected: All 3 tests PASS.

If any test FAILS, do NOT modify the test — that signals a bug in Task 1-5 impl. Trace the failure back to the relevant task and fix the impl.

- [ ] **Step 3: Run full test sweep to confirm no regression**

Run: `python -m pytest tests/test_audit_prepare.py -v`
Expected: All tests PASS (existing 3 atomic-flow tests + Task 1/2/3 unit tests + Task 4/5 integration tests + Task 6 failure-injection tests).

Total test count after this task: 3 (existing) + 4 (Task 1) + 3 (Task 2) + 3 (Task 3) + 1 (Task 4) + 3 (Task 5) + 3 (Task 6) = 20 tests in the audit_prepare module. Plus the pre-existing tests for `build_worksheet_rows` / `_format_timestamp` / `resolve_video_path` / `write_worksheet_csv` / `test_main_writes_worksheet_csv` (existing before this task).

- [ ] **Step 4: Run lint + type checks**

Run: `ruff check tests/test_audit_prepare.py`
Expected: `All checks passed!`

Run: `ruff format --check tests/test_audit_prepare.py`
Expected: no diff.

Run: `pyright scripts/audit-prepare.py`
Expected: `0 errors`

- [ ] **Step 5: Commit**

```bash
git add tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
test(audit): #800 failure-injection tests for W1 / W2 / before-tx-commit

3 つの crash point each で「crash 注入 → mid-crash state assert → recovery
run → recovered state assert」のフルサイクルを検証。monkeypatch で
shutil.rmtree / Path.rename / _write_tx_state_atomic を path filter 付き wrap。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update step (3) comment block + v030 audit doc

**Files:**

- Modify: `scripts/audit-prepare.py:304-332` (step (3) コメントブロック)
- Modify: `docs/v030-baseline-audit.md` ("Known limitation (Issue #800)" 節)

- [ ] **Step 1: Update step (3) comment block in `scripts/audit-prepare.py`**

After Task 4 + 5 the swap block now looks like:

```python
    args.worksheet_dir.mkdir(parents=True, exist_ok=True)
    _write_tx_state_atomic(tx_path, state=_TX_STATE_SWAPPING)
    if per_boundary_dir.exists():
        shutil.rmtree(per_boundary_dir)
    per_boundary_dir_new.rename(per_boundary_dir)
    worksheet_csv_new.replace(worksheet_csv)
    _write_tx_state_atomic(tx_path, state=_TX_STATE_CONSISTENT)
```

The existing 29-line `ATOMICITY LIMITATIONS` comment block (currently between `# (3) All-success: swap temp into final position.` and the `if per_boundary_dir.exists():` line) was added in #798 to document that the swap is non-transactional. After #800, the crash windows are detectable + auto-recoverable via tx-state, so this comment needs to be rewritten.

Open `scripts/audit-prepare.py` and find the line `# (3) All-success: swap temp into final position.` (current line 302). Replace the entire block from that line through the end of the `ATOMICITY LIMITATIONS` comment (which ends around line 332 with `# §9 Risks #1.`) with this updated block:

```python
    # (3) All-success: swap temp into final position.
    #
    # The 3-op swap (rmtree + rename + replace) is non-atomic, so a crash
    # between any two ops leaves filesystem state inconsistent. Issue #800
    # added a tx-state sidecar (`<label>.tx.json`) that is marked
    # "swapping" before the swap starts and "consistent" only after csv
    # replace succeeds. Step 0 of the next `audit-prepare` run reads the
    # tx-state, and if it is still "swapping" wipes all artifacts before
    # regenerating from scratch (`_recover_stale_artifacts`).
    #
    # Both Codex-flagged windows are now detect + auto-recover safe:
    #   - After rmtree, before rename (W1):
    #       Mid-crash: per_boundary_dir gone, worksheet_csv still old.
    #       Next run: tx="swapping" -> wipe old csv + tx -> regenerate.
    #   - After rename, before replace (W2):
    #       Mid-crash: per_boundary_dir new, worksheet_csv still old.
    #       Next run: tx="swapping" -> wipe new dir + old csv + tx -> regenerate.
    #
    # The tx-state file itself is published via `.tx.json.new` + os.replace
    # so its write is single-file atomic on Windows + POSIX.
```

- [ ] **Step 2: Update `docs/v030-baseline-audit.md`**

Find the "Known limitation (Issue #800)" subsection (added in PR #801 / commit `78d0cdf`). Read the current content first:

```bash
grep -n "Known limitation" docs/v030-baseline-audit.md
```

Open the file, locate the heading `### Known limitation (Issue #800)`, and prepend a "解消" notice plus replace the body to reflect the fix. The new section should read:

```markdown
### Known limitation (Issue #800) — RESOLVED 2026-05-21

`audit-prepare.main()` の step (3) atomic swap には 3-op (rmtree + rename + replace) で構成された crash window があったが、Issue #800 で `<label>.tx.json` sidecar (tx-state) を導入して検出 + 次 run auto-recover を実装した。

- W1 (`rmtree` 後 / `rename` 前) と W2 (`rename` 後 / `replace` 前) は次 `audit-prepare` 実行時に `state == "swapping"` が読み取られ、artifacts を全消去してから regenerate する
- tx-state 自身は `.tx.json.new` 経由の `os.replace` で single-file atomic 書き込み
- backwards-compat: tx.json 不在 (legacy baseline) / "consistent" は recovery skip

詳細仕様は `docs/superpowers/specs/2026-05-20-audit-prepare-tx-recovery-design.md`、実装は PR #<新 PR 番号> (Task 8 で番号確定)。
```

`<新 PR 番号>` は Task 8 で確定する。Task 7 commit 段階では `#<PR-pending>` 等のプレースホルダで commit せず、Task 8 で PR 作成後にこの番号を埋めて再 commit する。

- [ ] **Step 3: Verify markdownlint passes**

Run: `bash scripts/check-markdownlint.sh docs/v030-baseline-audit.md`
Expected: `Summary: 0 error(s)`

If errors, refer to `docs/markdownlint-guide.md` §typical fixes.

- [ ] **Step 4: Verify no regression in test suite**

Run: `python -m pytest tests/test_audit_prepare.py -v`
Expected: All tests PASS (comment changes do not affect behavior).

- [ ] **Step 5: Run lint + type checks on script**

Run: `ruff check scripts/audit-prepare.py`
Expected: `All checks passed!`

Run: `ruff format --check scripts/audit-prepare.py`
Expected: no diff.

- [ ] **Step 6: Commit (placeholder PR number)**

```bash
git add scripts/audit-prepare.py docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs(audit): #800 update step (3) comment + v030 audit doc

step (3) コメントブロックを「ATOMICITY LIMITATIONS (Issue #800 で
manifest / epoch / atomic pointer pattern を tracking 中)」から
「tx-state で detect + auto-recover」に書き換え。
docs/v030-baseline-audit.md の "Known limitation (Issue #800)"
subsection に RESOLVED notice を追加。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Task 8 で PR 番号確定後、必要なら `gh pr comment` で fix の reference を補足する (commit を amend しない、新規 commit で対応)。

---

## Task 8: PR creation (Iron Law 6 Pre-flight + Codex adversarial-review)

> このタスクは Idios の手動操作を含む。subagent では Step 5 (Codex adversarial-review handoff) を実行せず、prompt を準備して Idios に提示する。

**Files:**

- (none — git/gh commands only)

- [ ] **Step 1: Iron Law 6 Pre-flight Step 0 — parallel PR check (<1s hard gate)**

Run:

```bash
gh pr list --search "800" --state open --repo Idios/kobutachan-allaganeye
```

Expected: 0 件 (本 PR を出す前なので open は無し)。1 件以上ある場合は STOP し AskUserQuestion で「同 issue 並行 PR が既にある。続けるか調整するか」を user に問う。

- [ ] **Step 2: Iron Law 6 Pre-flight Step 1 — base 同期**

Run:

```bash
git fetch origin develop-0.3.0
```

- [ ] **Step 3: Iron Law 6 Pre-flight Step 2 — 取り込み未済 commit 確認**

Run:

```bash
git log HEAD..origin/develop-0.3.0 --oneline
```

Expected: 0 行 (branch を新規に `origin/develop-0.3.0` から切ったため、base に未済 commit は無いはず)。1 行以上ある場合は `git merge origin/develop-0.3.0` でマージ + コンフリクトがあれば解消。

- [ ] **Step 4: Iron Law 6 Pre-flight Step 3 — touched files 交差判定**

Run:

```bash
git diff origin/develop-0.3.0 --name-only
```

Expected:

```text
docs/superpowers/plans/2026-05-21-audit-prepare-tx-recovery.md
docs/superpowers/specs/2026-05-20-audit-prepare-tx-recovery-design.md
docs/v030-baseline-audit.md
scripts/audit-prepare.py
tests/test_audit_prepare.py
```

(plan は本 Task 8 開始前に commit 済を想定。未 commit ならまず plan も commit する)

- [ ] **Step 5: Iron Law 6 Pre-flight Step 4 — 並行 PR 重複再確認**

Run:

```bash
gh pr list --search "800" --state all --repo Idios/kobutachan-allaganeye
```

Expected: 0 件 (本 PR がまだ無いため)。Step 0 と同じ search だが state が `all` で closed merged も含む。

- [ ] **Step 6: Iron Law 6 Pre-flight Step 5 — Codex adversarial-review handoff to Idios**

> Codex CLI invocation は subagent からは行えない (project rule で skill 経由のみ)。本 step は Idios が手動で `/codex:adversarial-review` を invoke する handoff prompt を準備するに留まる。

push 前に PR 作成予定の summary を準備:

Branch: `claude/audit-tx-recovery-800`
Base: `develop-0.3.0`
Summary: `feat(audit): #800 audit-prepare transactional crash recovery (tx-state sidecar)`

Idios に提示する Codex adversarial-review prompt template:

```text
EXECUTOR: dispatch (origin=claude/audit-tx-recovery-800, generated=2026-05-21)

Please invoke the following review before PR creation:

/codex:adversarial-review focus="Issue #800 implementation on claude/audit-tx-recovery-800 -- verify tx-state sidecar (`<label>.tx.json`) design covers all 3 crash points (W1: after rmtree before rename / W2: after rename before csv replace / before-tx-commit: after csv replace before final 'consistent' write). Probe for: Iron Law 3 scope creep, encoding boundary issues (Windows MSYS / cp932 in tx.json read/write), Windows file-rename atomicity gaps for the tx.json.new -> tx.json replace, race conditions between _read_tx_state and concurrent main() invocations (out-of-scope but call it out), residual silent-skip paths in _read_tx_state error branches, WARNING message stderr/stdout segregation, backwards compat behavior when tx.json is missing vs corrupted vs unknown schema_version / unknown state. Verify spec §6 acceptance criteria 1-11 are satisfied." --wait
```

Idios の指示待ち:

- (A) Codex finding ゼロ → Step 7 で push + PR 作成
- (B) Codex finding あり → 各 finding を分類 ((A) PR 内修正 / (B) 別 issue / (C) 既存 issue 追記) して対応 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)。本 PR の解決後に Step 7 へ
- (C) Codex 不在 (token 枯渇等) → fallback で superpowers `requesting-code-review` subagent を起動 (`docs/l2-workflow.md` §「Codex fallback」)。fallback notice を PR 本文に必須記載

- [ ] **Step 7: Push branch**

Codex review が clean (or 全 finding 解消) になったら:

```bash
git push -u origin claude/audit-tx-recovery-800
```

- [ ] **Step 8: Create PR**

```bash
gh pr create \
  --base develop-0.3.0 \
  --repo Idios/kobutachan-allaganeye \
  --title "feat(audit): #800 audit-prepare transactional crash recovery" \
  --body "$(cat <<'EOF'
## 期待値

`scripts/audit-prepare.main()` step (3) の 3-op swap (rmtree + rename + replace) で発生しうる W1 / W2 crash window を検出 + 次 run auto-recover する。

## 現状

Issue #798 (PR #801) で W1 / W2 を `docs/superpowers/specs/2026-05-20-audit-script-hardening-design.md` §3.2 / §9 で trade-off として明示し、`scripts/audit-prepare.py:304-332` でも文書化した。Codex adversarial-review が W1 / W2 を指摘し、Issue #800 として follow-up を tracking していた。

## 修正内容

- `scripts/audit-prepare.py`: tx-state 定数 + 3 helpers (`_read_tx_state` / `_write_tx_state_atomic` / `_recover_stale_artifacts`) を追加。`main()` に Step 0 (recovery-on-start) と Step 3a/3e (tx-state marker) を組み込み
- `<label>.tx.json` schema = `{schema_version: 1, state: "consistent"|"swapping", updated_at: ISO 8601 UTC}`
- 書き込みは `.tx.json.new` 経由の `os.replace` で single-file atomic
- backwards-compat: tx.json 不在 / JSON parse fail / non-dict / unknown schema_version / unknown state は通常 flow を許容 (file 不在以外は WARNING を stderr に 1 行)
- `tests/test_audit_prepare.py`: 13 件の新規 test 追加 (helpers 単体 9 件 + main() 統合 3 件 + failure-injection 3 件)
- `scripts/audit-prepare.py:304-332` step (3) コメントブロックを「detect + auto-recover」に書き換え
- `docs/v030-baseline-audit.md` "Known limitation (Issue #800)" subsection を RESOLVED に更新

## 受け入れ条件 (spec §6 と同一)

- [x] Step 3 開始時に `<label>.tx.json` を state="swapping" で atomic 書き込み
- [x] Step 3 完了時 (csv replace 直後) に state="consistent" で atomic 書き込み
- [x] main() Step 0 で state=="swapping" 検出 → artifacts + tx.json 全消去 + WARNING 出力
- [x] tx.json 不在 / parse fail / non-dict / 未知 schema_version / 未知 state を backwards-compat で通常 flow (file 不在以外は WARNING)
- [x] tx-state 書き込みは `.tx.json.new` + `os.replace` で single-file atomic
- [x] failure-injection tests 6 件 green (W1 / W2 / before-tx-commit / no-recovery-consistent / legacy-compat / corrupted-parametrize)
- [x] 既存 `test_audit_prepare.py` 3 件 (atomic_success / atomic_failure / recovers_from_stale_new_dir) 引き続き green
- [x] ruff check / ruff format --check / pyright / pytest 全 green
- [x] `docs/v030-baseline-audit.md` "Known limitation" を RESOLVED 更新
- [x] step (3) コメントブロックを「detect + auto-recover」に更新
- [ ] PR 作成 Pre-flight Step 5 `/codex:adversarial-review` で additional crash window 指摘ゼロ

## Self-Test Report

machine-verified:
- [x] `python -m pytest tests/test_audit_prepare.py -v` (20+ tests passed)
- [x] `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py` clean
- [x] `ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py` clean
- [x] `pyright scripts/audit-prepare.py` 0 errors
- [x] `bash scripts/check-markdownlint.sh docs/v030-baseline-audit.md` clean
- [x] Iron Law 6 Pre-flight Step 0-5 通過

machine-unverifiable:
- 実機 audit-prepare 実行による operator 視点 UX 確認 (Idios 検証推奨、複数 boundary で `.tx.json` cleanup 動作確認)

## 関連

- Refs #800 (本 PR で対応)
- Refs #796 (親 audit issue) / #798 (predecessor hardening PR #801)
- spec: `docs/superpowers/specs/2026-05-20-audit-prepare-tx-recovery-design.md`
- plan: `docs/superpowers/plans/2026-05-21-audit-prepare-tx-recovery.md`

[hopeful-germain-8ffc43]
EOF
)"
```

(注: PR 本文は HEREDOC + `cat << 'EOF' ... EOF` で日本語 UTF-8 保護、`feedback_gh_command_ja_heredoc.md` 準拠)

- [ ] **Step 9: PR 番号確定後、v030 audit doc の `<新 PR 番号>` を実 PR 番号で置換 (Task 7 placeholder を解決)**

```bash
# 実際の PR 番号を確認
gh pr view --repo Idios/kobutachan-allaganeye --json number,url
```

`docs/v030-baseline-audit.md` の `<新 PR 番号>` を実 PR 番号で置換 → 新規 commit:

```bash
git add docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs: #800 v030 audit doc PR 番号を確定値に置換

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin claude/audit-tx-recovery-800
```

- [ ] **Step 10: `/iterate-review <PR#>` 自走呼出 を Idios に handoff**

> Codex adversarial-review (Step 6) は PR 作成前の Iron Law 6 Pre-flight Step 5。これとは別に PR 作成後 `/iterate-review` で review-fix ループを回す。本 skill (writing-plans / subagent-driven-development) からは invoke せず、Idios の手動操作。

Idios に handoff:

```text
EXECUTOR: dispatch (origin=claude/audit-tx-recovery-800, generated=2026-05-21)

PR #<PR番号> 作成完了。次のステップを invoke してください:

/iterate-review <PR番号>
```

`<PR番号>` は Step 8 で確定する番号。

---

## Self-Review

After writing this plan, checking against the spec:

### 1. Spec coverage

| Spec section | Plan task |
| --- | --- |
| §3.1 ファイル構造 (`<label>.tx.json` + `.tx.json.new` 追加) | Task 1 (定数 + read), Task 2 (write), Task 4 (main 統合) |
| §3.2 tx-state schema (schema_version=1, state, updated_at) | Task 1 (read validation), Task 2 (write payload) |
| §3.3 主要フロー (Step 0 + 3a + 3e) | Task 4 (Step 3a/3e), Task 5 (Step 0) |
| §3.4 Recovery 表 (全 crash point) | Task 5 + Task 6 で全 case test 化 |
| §3.5 audit-compare 変更なし | (touched files に audit-compare.py 含めず、無対応で正解) |
| §4 components table | Task 1-3 (helpers), Task 4-5 (main), Task 7 (docs + comment) |
| §4.1 helper sketch | Task 1-3 で完全実装 (sketch の通り) |
| §4.2 main() 改修 | Task 4 (Step 3), Task 5 (Step 0) |
| §5 failure-injection (3 crash + 1 no-crash + 1 legacy + 1 corrupted) | Task 6 (3 crash) + Task 5 (legacy + no_recovery) + Task 1 (corrupted parametrize) |
| §5.1 injection 手法 | Task 6 step 1 の 3 個別 test 各々で `monkeypatch.setattr` wrap |
| §5.2 既存 test regression | Task 4 step 5 + Task 5 step 5 で `pytest -v` 全 run |
| §6 受け入れ条件 #1-#11 | Task 8 step 8 PR 本文の `## 受け入れ条件` で逐条チェック |
| §7 Out of scope | Plan 全タスクは scope 内、Issue #797 / multi-process lock / 真の atomic publish は Out of scope §7 で除外宣言 |
| §8 関連 | Task 8 step 8 PR 本文 `## 関連` で参照 |
| §9 Risks register | 各 risk の mitigation は impl + test で担保 (risk #1 = §3.2 atomic write / risk #2 = §3.2 fallback / risk #3-4 = §3.4 recovery table / risk #5 = §7 Out of scope / risk #6 = Task 5 test_tx_state_missing_legacy_compat / risk #7 = Task 6 deterministic injection) |

Gap: なし。spec の全 section が plan の task でカバーされている。

### 2. Placeholder scan

- "TBD" / "TODO" / "implement later" / "fill in details" / "Add appropriate error handling" / "handle edge cases" / "Write tests for the above" → 全 task で actual code を記載済
- `<新 PR 番号>` placeholder は Task 7 step 2 で commit 直後に Task 8 step 9 で確定値に置換する明示的な後処理が定義されている (= placeholder 残置ではなく時系列的に解決される設計)
- `<PR番号>` placeholder は Task 8 step 8 の出力で確定 → step 9 / step 10 で参照する流れ (= 時系列的に解決される)
- "Similar to Task N" の reference は 0 件 (全 task に独立した code block を含めている)

### 3. Type consistency

- `_read_tx_state(tx_path: Path) -> dict[str, Any] | None` (Task 1 で定義) → Task 5 で `tx = _read_tx_state(tx_path)` として使用、`tx["state"]` の引き方も一致 ✓
- `_write_tx_state_atomic(tx_path: Path, *, state: str) -> None` (Task 2 で定義) → Task 4 / Task 5 / Task 6 で `state=_TX_STATE_SWAPPING` / `state=_TX_STATE_CONSISTENT` / `state="swapping"` (test 内) / `state="consistent"` (test 内) として使用 ✓
- `_recover_stale_artifacts(*, per_boundary_dir, worksheet_csv, tx_path) -> None` (Task 3 で定義) → Task 5 で同じ keyword arg で呼出 ✓
- 定数 `_TX_SCHEMA_VERSION=1`, `_TX_STATE_CONSISTENT="consistent"`, `_TX_STATE_SWAPPING="swapping"` (Task 1 で定義) → Task 2 (payload), Task 4 / Task 5 (main wiring) で参照、Task 6 (test 内では文字列リテラル "swapping" / "consistent" を使用)。test 内で `mod._TX_STATE_SWAPPING` を使ってもよいが、リテラルでも equivalent ✓
- `tx_path = args.worksheet_dir / f"{args.recording_label}.tx.json"` (Task 4 で定義) → Task 5 で同じ tx_path を使用 ✓

Inconsistency: なし。

### 4. Architecture coherence

- 「読み手は人間のみ」(spec §2.1) → audit-compare 側無変更 (Task の touched files に含めず) ✓
- 「3 helpers + main() 2 拡張点」 → Task 1-3 + Task 4-5 で対応 ✓
- 「tx-state は single source of truth」 → 全 recovery 判定が `_read_tx_state` 経由 (Task 5 Step 0) ✓
- 「`.tx.json.new` 経由 atomic write」 → Task 2 で `tx_new.replace(tx_path)` ✓
- 「Iron Law 6 Pre-flight」 → Task 8 で Step 0-5 + handoff prompt ✓

---

## Plan complete — execution choice

Plan complete and saved to `docs/superpowers/plans/2026-05-21-audit-prepare-tx-recovery.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
