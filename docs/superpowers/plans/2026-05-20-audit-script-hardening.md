# audit-{prepare,compare} reproducibility hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `scripts/audit-{prepare,compare}.py` so future re-runs cannot silently corrupt audit state — make `source_size_bytes` validation mandatory (R3#1) and rewrite `audit-prepare.main()` into a temp-sibling + atomic-rename flow (R3#2).

**Architecture:** Two-script refactor driven by TDD. `audit-compare.py` gets a tightened ground-truth schema (`source_size_bytes` REQUIRED), a `skip_source_size_check` parameter on `validate_ground_truth_against_baseline`, and `main()` fail-close + `--skip-source-size-check` CLI flag. `audit-prepare.main()` is rewritten to generate all artifacts in `<label>.new/` + `<label>.csv.new`, then atomically rename / replace on full success (failures leave old artifacts intact).

**Tech Stack:** Python 3.10+, pytest, ruff, pyright, markdownlint-cli2.

**Spec:** [docs/superpowers/specs/2026-05-20-audit-script-hardening-design.md](../specs/2026-05-20-audit-script-hardening-design.md)

**Branch:** `claude/audit-hardening-798` (off `develop-0.3.0`)

---

## File Structure

| File | Responsibility | Touched in tasks |
| --- | --- | --- |
| `scripts/audit-compare.py` | Schema validation + fail-close + skip flag | 1, 2, 3, 4 |
| `scripts/audit-prepare.py` | Atomic temp-sibling generation flow | 5 |
| `tests/test_audit_compare.py` | R3#1 tests + existing-test schema fixture updates | 1, 2, 3, 4 |
| `tests/test_audit_prepare.py` | R3#2 atomic-flow tests | 5 |
| `docs/v030-baseline-audit.md` | Retrospect addendum (R3#1/R3#2 解消) | 6 |

## Existing-test impact (R3#1)

Tightening `_REQUIRED_GROUND_TRUTH_FIELDS` to include `source_size_bytes` will break 4 existing tests whose ground_truth fixtures omit it. Adding `skip_source_size_check` with the "raise when actual=None and not skipped" default will break another 4 calls (overlapping set). Both fix-ups are mechanical and are included in Tasks 1 and 2 below.

Affected existing tests (in `tests/test_audit_compare.py`):

1. `test_validate_ground_truth_against_baseline_ok` (L161-170)
2. `test_validate_ground_truth_source_mismatch_raises` (L173-183)
3. `test_validate_ground_truth_recording_label_mismatch_raises` (L235-248)
4. `test_validate_ground_truth_recording_label_skipped_when_not_provided` (L268-278)

`test_validate_ground_truth_missing_fields_raises` (L186-191) and `test_validate_ground_truth_source_size_mismatch_raises` (L251-265) do not need updating (they remain correct under the new schema).

---

### Task 1: source_size_bytes REQUIRED in schema

**Files:**

- Modify: `scripts/audit-compare.py:27-32` (`_REQUIRED_GROUND_TRUTH_FIELDS`)
- Modify: `tests/test_audit_compare.py:161-170` / `173-183` / `235-248` / `268-278` (add `source_size_bytes` to 4 existing fixtures)
- Modify: `tests/test_audit_compare.py` (append 1 new test)

- [ ] **Step 1: Add new failing test**

Append to `tests/test_audit_compare.py`:

```python
def test_validate_ground_truth_rejects_missing_source_size_bytes():
    """source_size_bytes is REQUIRED in ground-truth schema (R3#1)."""
    mod = _load_module()
    baseline = {"source": "20260116/x.mkv", "matches": []}
    ground_truth = {
        "source_file": "20260116/x.mkv",
        "source_dir_label": "obs-20260116",
        "tolerance_sec": 5,
        "matches": [],
        # source_size_bytes intentionally missing
    }
    with pytest.raises(ValueError, match="missing required fields"):
        mod.validate_ground_truth_against_baseline(baseline, ground_truth)
```

- [ ] **Step 2: Run new test to verify it fails**

Run: `python -m pytest tests/test_audit_compare.py::test_validate_ground_truth_rejects_missing_source_size_bytes -v`
Expected: FAIL — `DID NOT RAISE <class 'ValueError'>` (because current `_REQUIRED_GROUND_TRUTH_FIELDS` does not include `source_size_bytes`).

- [ ] **Step 3: Tighten the schema**

In `scripts/audit-compare.py`, replace the `_REQUIRED_GROUND_TRUTH_FIELDS` tuple:

```python
_REQUIRED_GROUND_TRUTH_FIELDS = (
    "source_file",
    "source_dir_label",
    "tolerance_sec",
    "matches",
    "source_size_bytes",
)
```

- [ ] **Step 4: Add source_size_bytes to 4 existing test fixtures**

In `tests/test_audit_compare.py`, add `"source_size_bytes": 12345,` to the ground_truth dict in each of:

1. `test_validate_ground_truth_against_baseline_ok` — between `"matches": []` and the closing brace:

   ```python
   ground_truth = {
       "source_file": "20260116/x.mkv",
       "source_dir_label": "obs-20260116",
       "tolerance_sec": 5,
       "matches": [],
       "source_size_bytes": 12345,
   }
   ```

2. `test_validate_ground_truth_source_mismatch_raises` — same insertion in its ground_truth dict.

3. `test_validate_ground_truth_recording_label_mismatch_raises` — same insertion.

4. `test_validate_ground_truth_recording_label_skipped_when_not_provided` — same insertion.

- [ ] **Step 5: Run new + existing validate tests to verify all pass**

Run: `python -m pytest tests/test_audit_compare.py -v -k "validate"`
Expected: PASS — new test now raises ValueError (schema tightened), and the 4 existing tests still pass with their updated fixtures.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-compare.py tests/test_audit_compare.py
git commit -m "$(cat <<'EOF'
feat(audit): #798 R3#1 — source_size_bytes REQUIRED in ground-truth schema

_REQUIRED_GROUND_TRUTH_FIELDS に source_size_bytes 追加。既存テスト 4 件の fixture も schema 順守。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: validate gains skip_source_size_check parameter

**Files:**

- Modify: `scripts/audit-compare.py:35-83` (`validate_ground_truth_against_baseline`)
- Modify: `tests/test_audit_compare.py:161-170` / `173-183` / `235-248` / `268-278` (add `skip_source_size_check=True` to 4 existing call sites that do not pass `actual_source_size`)
- Modify: `tests/test_audit_compare.py` (append 2 new tests)

- [ ] **Step 1: Add 2 new failing tests**

Append to `tests/test_audit_compare.py`:

```python
def test_validate_rejects_none_actual_size_when_check_enabled():
    """actual_source_size=None + skip=False (default) raises (R3#1)."""
    mod = _load_module()
    baseline = {"source": "x.mkv", "matches": []}
    ground_truth = {
        "source_file": "x.mkv",
        "source_dir_label": "obs-fake",
        "tolerance_sec": 5,
        "matches": [],
        "source_size_bytes": 12345,
    }
    with pytest.raises(ValueError, match="actual_source_size is required"):
        mod.validate_ground_truth_against_baseline(baseline, ground_truth)


def test_validate_skip_flag_bypasses_size_check():
    """skip_source_size_check=True allows actual_source_size=None to pass (R3#1)."""
    mod = _load_module()
    baseline = {"source": "x.mkv", "matches": []}
    ground_truth = {
        "source_file": "x.mkv",
        "source_dir_label": "obs-fake",
        "tolerance_sec": 5,
        "matches": [],
        "source_size_bytes": 12345,
    }
    # Should not raise even though actual_source_size is None
    mod.validate_ground_truth_against_baseline(
        baseline, ground_truth, skip_source_size_check=True
    )
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `python -m pytest tests/test_audit_compare.py::test_validate_rejects_none_actual_size_when_check_enabled tests/test_audit_compare.py::test_validate_skip_flag_bypasses_size_check -v`
Expected: FAIL — `DID NOT RAISE` for the first test (current impl silently skips when `actual_source_size is None`) and `TypeError: validate_ground_truth_against_baseline() got an unexpected keyword argument 'skip_source_size_check'` for the second.

- [ ] **Step 3: Refactor validate function**

In `scripts/audit-compare.py`, replace the entire `validate_ground_truth_against_baseline` function (`L35-83`) with:

```python
def validate_ground_truth_against_baseline(
    baseline: dict[str, Any],
    ground_truth: dict[str, Any],
    *,
    recording_label: str | None = None,
    actual_source_size: int | None = None,
    skip_source_size_check: bool = False,
) -> None:
    """Reject ground-truth files that do not describe the same recording.

    Raises ValueError if any of the following hold:
    - required schema fields are absent
    - baseline `source` != ground truth `source_file`
    - `recording_label` was supplied and != ground truth `source_dir_label`
    - `skip_source_size_check` is False and `actual_source_size` is None
    - `skip_source_size_check` is False and the resolved video size does not
      match ground truth `source_size_bytes`

    Codex adversarial reviews (2026-05-20 rounds 1-3) flagged that matching
    only the relative source path is insufficient: a replaced / truncated
    recording at the same path, or a silently skipped size check when the
    sample dir is unset, would certify stale findings. Schema + actual size
    are now both required by default; operators opt out explicitly via
    `skip_source_size_check=True` (Issue #798).
    """
    missing = [f for f in _REQUIRED_GROUND_TRUTH_FIELDS if f not in ground_truth]
    if missing:
        raise ValueError(
            f"ground truth missing required fields: {missing}. "
            f"Required: {list(_REQUIRED_GROUND_TRUTH_FIELDS)}"
        )
    baseline_source = baseline.get("source")
    gt_source = ground_truth.get("source_file")
    if baseline_source != gt_source:
        raise ValueError(
            f"baseline source ({baseline_source!r}) does not match "
            f"ground truth source_file ({gt_source!r}); "
            "this ground-truth file describes a different recording"
        )
    if recording_label is not None:
        gt_label = ground_truth.get("source_dir_label")
        if gt_label != recording_label:
            raise ValueError(
                f"recording label ({recording_label!r}) does not match "
                f"ground truth source_dir_label ({gt_label!r})"
            )
    if not skip_source_size_check:
        if actual_source_size is None:
            raise ValueError(
                "actual_source_size is required for source_size_bytes "
                "validation. Set ALLAGANEYE_SAMPLE_VIDEO_DIR + ensure the "
                "video resolves on disk, or pass skip_source_size_check=True "
                "explicitly."
            )
        gt_size = ground_truth["source_size_bytes"]
        if gt_size != actual_source_size:
            raise ValueError(
                f"video file size ({actual_source_size}) does not match "
                f"ground truth source_size_bytes ({gt_size}); "
                "the recording may have been replaced or truncated"
            )
```

- [ ] **Step 4: Add skip_source_size_check=True to 4 existing validate calls**

Existing calls in `tests/test_audit_compare.py` that currently rely on silent-skip-when-actual-None:

1. `test_validate_ground_truth_against_baseline_ok` (L170):

   ```python
   mod.validate_ground_truth_against_baseline(
       baseline, ground_truth, skip_source_size_check=True
   )
   ```

2. `test_validate_ground_truth_source_mismatch_raises` (L182-183):

   ```python
   with pytest.raises(ValueError, match="does not match"):
       mod.validate_ground_truth_against_baseline(
           baseline, ground_truth, skip_source_size_check=True
       )
   ```

3. `test_validate_ground_truth_recording_label_mismatch_raises` (L246-248):

   ```python
   with pytest.raises(ValueError, match="source_dir_label"):
       mod.validate_ground_truth_against_baseline(
           baseline,
           ground_truth,
           recording_label="obs-20260116",
           skip_source_size_check=True,
       )
   ```

4. `test_validate_ground_truth_recording_label_skipped_when_not_provided` (L278):

   ```python
   mod.validate_ground_truth_against_baseline(
       baseline, ground_truth, skip_source_size_check=True
   )
   ```

- [ ] **Step 5: Run full validate test suite to verify all pass**

Run: `python -m pytest tests/test_audit_compare.py -v -k "validate"`
Expected: PASS — new 2 tests pass with refactored impl; 4 existing tests pass with skip flag opt-in; `test_validate_ground_truth_source_size_mismatch_raises` still passes (it provides matching `actual_source_size`, not affected by skip flag).

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-compare.py tests/test_audit_compare.py
git commit -m "$(cat <<'EOF'
feat(audit): #798 R3#1 — validate gains skip_source_size_check parameter

actual_source_size=None + skip=False (default) で raise。
明示的 skip 時のみ size check bypass。既存テスト 4 件は skip=True で opt-out。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: audit-compare main fails close when video unresolvable

**Files:**

- Modify: `scripts/audit-compare.py:270-323` (`main`)
- Modify: `tests/test_audit_compare.py` (append 2 new tests)

- [ ] **Step 1: Add 2 new failing tests**

Append to `tests/test_audit_compare.py`:

```python
def test_main_video_unresolved_fails_close(tmp_path, monkeypatch, capsys):
    """ALLAGANEYE_SAMPLE_VIDEO_DIR unset -> exit 3 + stderr ERROR (R3#1)."""
    import json as _json

    mod = _load_module()
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    gt_dir = baseline_dir / "ground-truth"
    gt_dir.mkdir()

    (baseline_dir / "obs-fake.metadata.json").write_text(
        _json.dumps({"source": "fake.mkv", "matches": []}),
        encoding="utf-8",
    )
    (gt_dir / "obs-fake.json").write_text(
        _json.dumps(
            {
                "source_file": "fake.mkv",
                "source_dir_label": "obs-fake",
                "tolerance_sec": 5,
                "matches": [],
                "source_size_bytes": 12345,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", raising=False)

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--ground-truth-dir",
            str(gt_dir),
        ]
    )
    assert rc == 3
    captured = capsys.readouterr()
    # Task 3 WARNING (env unset): distinguishes Task 3 impl from Task 2-only state
    assert "ALLAGANEYE_SAMPLE_VIDEO_DIR is not set" in captured.err
    # Task 2 ERROR (validate raises and main catches): downstream of WARNING
    assert "actual_source_size is required" in captured.err


def test_main_video_missing_in_env_fails_close(tmp_path, monkeypatch, capsys):
    """env set but video file absent -> exit 3 + stderr ERROR (R3#1)."""
    import json as _json

    mod = _load_module()
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    gt_dir = baseline_dir / "ground-truth"
    gt_dir.mkdir()
    video_dir = tmp_path / "videos"  # empty, no fake.mkv inside
    video_dir.mkdir()

    (baseline_dir / "obs-fake.metadata.json").write_text(
        _json.dumps({"source": "fake.mkv", "matches": []}),
        encoding="utf-8",
    )
    (gt_dir / "obs-fake.json").write_text(
        _json.dumps(
            {
                "source_file": "fake.mkv",
                "source_dir_label": "obs-fake",
                "tolerance_sec": 5,
                "matches": [],
                "source_size_bytes": 12345,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--ground-truth-dir",
            str(gt_dir),
        ]
    )
    assert rc == 3
    captured = capsys.readouterr()
    # Task 3 WARNING (file missing): distinguishes Task 3 impl from Task 2-only state
    assert "does not exist" in captured.err
    # Task 2 ERROR (validate raises and main catches)
    assert "actual_source_size is required" in captured.err
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `python -m pytest tests/test_audit_compare.py::test_main_video_unresolved_fails_close tests/test_audit_compare.py::test_main_video_missing_in_env_fails_close -v`
Expected: FAIL — both tests assert the Task-3-introduced WARNING messages (`"ALLAGANEYE_SAMPLE_VIDEO_DIR is not set"` / `"does not exist"`) in stderr. After Task 2 alone, main does NOT emit these WARNINGs (it silently sets `actual_source_size = None`, then validate raises with the "actual_source_size is required" ERROR which propagates through main's existing `except ValueError: return 3`). So `rc == 3` already holds post-Task-2 but the WARNING assertions FAIL until Task 3 adds the explicit stderr context.

- [ ] **Step 3: Refactor main() to explicit fail-close**

In `scripts/audit-compare.py`, replace the `main()` body section that resolves `actual_source_size` (currently L296-301) with explicit handling. Keep the rest of `main()` intact. Specifically, the existing block:

```python
    actual_source_size: int | None = None
    sample_video_dir = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if sample_video_dir and "source" in baseline:
        video_candidate = Path(sample_video_dir) / baseline["source"]
        if video_candidate.exists():
            actual_source_size = video_candidate.stat().st_size
```

is replaced by:

```python
    actual_source_size: int | None = None
    sample_video_dir = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if sample_video_dir and "source" in baseline:
        video_candidate = Path(sample_video_dir) / baseline["source"]
        if video_candidate.exists():
            actual_source_size = video_candidate.stat().st_size
        else:
            print(
                f"WARNING: ALLAGANEYE_SAMPLE_VIDEO_DIR is set ({sample_video_dir!r}) "
                f"but {video_candidate} does not exist; "
                "source_size_bytes validation will fail unless "
                "--skip-source-size-check is passed.",
                file=sys.stderr,
            )
    elif not sample_video_dir:
        print(
            "WARNING: ALLAGANEYE_SAMPLE_VIDEO_DIR is not set; "
            "source_size_bytes validation will fail unless "
            "--skip-source-size-check is passed.",
            file=sys.stderr,
        )
```

The actual `return 3` is already produced by the existing `except ValueError as exc: return 3` block downstream — Task 2's new "actual_source_size is required" error message bubbles up through there. The new WARNING lines only clarify the failure mode for operators.

- [ ] **Step 4: Run new + existing main tests**

Run: `python -m pytest tests/test_audit_compare.py -v -k "main"`
Expected: PASS — both new tests now see `rc == 3` and stderr contains `actual_source_size is required`. Existing main tests (if any) still pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit-compare.py tests/test_audit_compare.py
git commit -m "$(cat <<'EOF'
feat(audit): #798 R3#1 — main fails close when video unresolvable

ALLAGANEYE_SAMPLE_VIDEO_DIR 未設定 / video 不在で WARNING + 後続 validate が raise → exit 3。
silent skip path を撤廃。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: audit-compare --skip-source-size-check CLI flag

**Files:**

- Modify: `scripts/audit-compare.py:270-323` (`main`)
- Modify: `tests/test_audit_compare.py` (append 1 new test)

- [ ] **Step 1: Add new failing test**

Append to `tests/test_audit_compare.py`:

```python
def test_main_skip_flag_proceeds_without_video(tmp_path, monkeypatch, capsys):
    """--skip-source-size-check bypasses size check + emits stderr WARNING (R3#1)."""
    import json as _json

    mod = _load_module()
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    gt_dir = baseline_dir / "ground-truth"
    gt_dir.mkdir()

    (baseline_dir / "obs-fake.metadata.json").write_text(
        _json.dumps({"source": "fake.mkv", "matches": []}),
        encoding="utf-8",
    )
    (gt_dir / "obs-fake.json").write_text(
        _json.dumps(
            {
                "source_file": "fake.mkv",
                "source_dir_label": "obs-fake",
                "tolerance_sec": 5,
                "matches": [],
                "source_size_bytes": 12345,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", raising=False)

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--ground-truth-dir",
            str(gt_dir),
            "--skip-source-size-check",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "--skip-source-size-check" in captured.err
    assert "skipped" in captured.err.lower()
```

- [ ] **Step 2: Run new test to verify it fails**

Run: `python -m pytest tests/test_audit_compare.py::test_main_skip_flag_proceeds_without_video -v`
Expected: FAIL — `argparse: unrecognized arguments: --skip-source-size-check` (current `main()` does not declare the flag).

- [ ] **Step 3: Add argparse flag + wire to validate call**

In `scripts/audit-compare.py`, add to the argument parser (right after existing `--ground-truth-dir`):

```python
    parser.add_argument(
        "--skip-source-size-check",
        action="store_true",
        help="Skip source_size_bytes verification (operator escape; "
        "logged to stderr; ground-truth schema validation is NOT skipped).",
    )
```

Then, between the (existing) `actual_source_size` resolution block and the `validate_ground_truth_against_baseline` call, add the WARNING block:

```python
    if args.skip_source_size_check:
        print(
            "WARNING: --skip-source-size-check is set; source_size_bytes "
            "verification skipped. Ground-truth schema validation still runs.",
            file=sys.stderr,
        )
```

Update the `validate_ground_truth_against_baseline` call to pass the flag:

```python
    try:
        validate_ground_truth_against_baseline(
            baseline,
            ground_truth,
            recording_label=args.recording_label,
            actual_source_size=actual_source_size,
            skip_source_size_check=args.skip_source_size_check,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
```

- [ ] **Step 4: Run new + existing tests**

Run: `python -m pytest tests/test_audit_compare.py -v`
Expected: PASS — new skip-flag test passes; existing fail-close tests still pass (their argv does not include `--skip-source-size-check`); all other tests untouched.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit-compare.py tests/test_audit_compare.py
git commit -m "$(cat <<'EOF'
feat(audit): #798 R3#1 — --skip-source-size-check CLI flag

operator escape path 追加。flag 指定時 stderr に WARNING + validate へ skip 伝搬。
schema validation は skip しない (REQUIRED 5 field は依然 enforce)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: audit-prepare atomic flow refactor

**Files:**

- Modify: `scripts/audit-prepare.py:227-296` (`main`)
- Modify: `tests/test_audit_prepare.py` (append 3 new tests)

- [ ] **Step 1: Add 3 new failing tests**

Append to `tests/test_audit_prepare.py`:

```python
def test_main_atomic_success_replaces_old_artifacts(tmp_path, monkeypatch):
    """Success run atomically replaces old artifacts; no .new residue (R3#2)."""
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
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"

    # Seed pre-existing artifacts so we can verify they get replaced
    per_boundary_dir.mkdir(parents=True)
    (per_boundary_dir / "stale.txt").write_text("STALE", encoding="utf-8")
    worksheet_csv.write_text("STALE_HEADER\n", encoding="utf-8")

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
    # Stale must be gone, new artifacts present
    assert not (per_boundary_dir / "stale.txt").exists()
    assert "STALE_HEADER" not in worksheet_csv.read_text(encoding="utf-8")
    # No .new suffix residue
    assert not (worksheet_dir / "obs-fake.new").exists()
    assert not (worksheet_dir / "obs-fake.csv.new").exists()


def test_main_atomic_failure_preserves_old_artifacts(tmp_path, monkeypatch):
    """Failure mid-run keeps old artifacts intact; .new cleaned up (R3#2)."""
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

    # export_brightness_csv succeeds; export_sample_frames raises -> mid-run failure
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)

    def _fail(**kw):
        raise RuntimeError("simulated export failure")

    monkeypatch.setattr(mod, "export_sample_frames", _fail)

    worksheet_dir = tmp_path / "audit-worksheet"
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"

    # Seed pre-existing artifacts that must survive the failure
    per_boundary_dir.mkdir(parents=True)
    (per_boundary_dir / "keep.txt").write_text("KEEP", encoding="utf-8")
    worksheet_csv.write_text("KEEP_HEADER\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="simulated export failure"):
        mod.main(
            [
                "obs-fake",
                "--baseline-dir",
                str(baseline_dir),
                "--worksheet-dir",
                str(worksheet_dir),
            ]
        )

    # Old artifacts must be intact
    assert (per_boundary_dir / "keep.txt").read_text(encoding="utf-8") == "KEEP"
    assert worksheet_csv.read_text(encoding="utf-8") == "KEEP_HEADER\n"
    # .new suffix dirs cleaned up
    assert not (worksheet_dir / "obs-fake.new").exists()
    assert not (worksheet_dir / "obs-fake.csv.new").exists()


def test_main_recovers_from_stale_new_dir(tmp_path, monkeypatch):
    """Stale .new dir from prior crash is pre-cleaned and new run succeeds (R3#2)."""
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
    # Seed stale .new dir (simulating prior crash mid-write)
    stale_new = worksheet_dir / "obs-fake.new"
    stale_new.mkdir(parents=True)
    (stale_new / "junk.txt").write_text("JUNK", encoding="utf-8")
    stale_csv_new = worksheet_dir / "obs-fake.csv.new"
    stale_csv_new.write_text("JUNK\n", encoding="utf-8")

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
    # Stale .new must be gone (replaced by either rename target or cleanup)
    assert not stale_new.exists()
    assert not stale_csv_new.exists()
    # Final artifacts in place
    assert (worksheet_dir / "obs-fake.csv").exists()
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `python -m pytest tests/test_audit_prepare.py -v -k "atomic or recovers"`
Expected: FAIL — current `main()` does `shutil.rmtree(per_boundary_dir)` immediately, so the "preserves old artifacts" test will fail (stale.txt seed deleted before exception). The "success replaces" test may or may not pass depending on whether the existing flow happens to clean up correctly, but the `.new` suffix dirs cannot exist (they don't get created) — so the assertion `assert not (worksheet_dir / "obs-fake.new").exists()` passes trivially but the assertion that old `stale.txt` is gone may or may not hold cleanly.

- [ ] **Step 3: Rewrite audit-prepare main() with atomic flow**

In `scripts/audit-prepare.py`, replace the `main()` body from `metadata = json.loads(...)` (L261) through the end of the function (L296) with:

```python
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rows = build_worksheet_rows(metadata)

    video_path = resolve_video_path(metadata["source"])

    per_boundary_dir = args.worksheet_dir / args.recording_label
    per_boundary_dir_new = args.worksheet_dir / f"{args.recording_label}.new"
    worksheet_csv = args.worksheet_dir / f"{args.recording_label}.csv"
    worksheet_csv_new = args.worksheet_dir / f"{args.recording_label}.csv.new"

    # (1) Pre-clean any stale temp residue from a prior crashed run.
    # Existing final artifacts are untouched until step (3).
    if per_boundary_dir_new.exists():
        shutil.rmtree(per_boundary_dir_new)
    worksheet_csv_new.unlink(missing_ok=True)
    per_boundary_dir_new.mkdir(parents=True, exist_ok=True)

    # (2) Generate everything into the temp sibling. On any failure leave
    # existing final artifacts intact and clean up the temp.
    try:
        for row in rows:
            ts = float(row["timestamp_sec"])
            export_brightness_csv(
                video_path=video_path,
                boundary_timestamp=ts,
                out_path=per_boundary_dir_new / row["brightness_csv_ref"],
                window_sec=args.window_sec,
                interval_sec=args.interval_sec,
            )
            export_sample_frames(
                video_path=video_path,
                boundary_timestamp=ts,
                out_dir=per_boundary_dir_new,
            )
        write_worksheet_csv(rows, worksheet_csv_new)
    except Exception:
        if per_boundary_dir_new.exists():
            shutil.rmtree(per_boundary_dir_new)
        worksheet_csv_new.unlink(missing_ok=True)
        raise

    # (3) All-success: swap temp into final position. POSIX: atomic. Windows:
    # rmtree + rename has a brief window where per_boundary_dir is absent,
    # but next-run pre-clean recovers any in-progress state cleanly.
    if per_boundary_dir.exists():
        shutil.rmtree(per_boundary_dir)
    per_boundary_dir_new.rename(per_boundary_dir)
    worksheet_csv_new.replace(worksheet_csv)

    print(f"Worksheet: {worksheet_csv}", file=sys.stderr)
    print(f"Per-boundary artifacts: {per_boundary_dir}", file=sys.stderr)
    return 0
```

- [ ] **Step 4: Run new + existing audit-prepare tests**

Run: `python -m pytest tests/test_audit_prepare.py -v`
Expected: PASS — 3 new R3#2 tests pass; existing 11 tests still pass (the temp-sibling flow is transparent to `build_worksheet_rows` / `resolve_video_path` / `export_*` callsites; `test_main_writes_worksheet_csv` still observes the final `obs-fake.csv` at the same path).

- [ ] **Step 5: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #798 R3#2 — atomic temp-sibling + rename flow

audit-prepare.main() を <label>.new/ + <label>.csv.new 経由の atomic flow に書き直し。
mid-run failure で旧 artifacts intact、success で atomic replace。
stale .new dir からの recovery も pre-cleanup で対応。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: audit doc retrospect addendum

**Files:**

- Modify: `docs/v030-baseline-audit.md` (last section "Iteration 1 PoC retrospect (applied)")

- [ ] **Step 1: Add retrospect note**

Append a new section to `docs/v030-baseline-audit.md` after the existing "Iteration 1 PoC retrospect (applied)" section:

```markdown
## Codex round 3 follow-up (Issue #798, applied 2026-05-20)

PR #799 merge 後の Codex Round 3 finding 2 件を Issue #798 で消化:

1. **R3#1 source_size validation tightening** — `_REQUIRED_GROUND_TRUTH_FIELDS` に `source_size_bytes` を追加し REQUIRED 化。`audit-compare.py` main は video 未解決時に exit 3 で fail-close、operator escape は `--skip-source-size-check` flag 経由 (stderr に WARNING)。`validate_ground_truth_against_baseline` に `skip_source_size_check` parameter 追加
2. **R3#2 atomic re-run** — `audit-prepare.main()` を `<label>.new/` + `<label>.csv.new` 経由の atomic flow に書き直し。mid-run failure 時は旧 artifacts intact、success 時に rename / replace で swap、前 run crash 由来の stale `.new` も次 run の pre-cleanup で recover

なお Iteration 1 retrospect item 4 の "adjacent boundary PNG overwriting" は本 follow-up の scope 外 (低 impact + Iron Law 3 scope 維持、Issue #798 §7 out of scope 明記)。
```

- [ ] **Step 2: Verify markdownlint passes**

Run: `bash scripts/check-markdownlint.sh docs/v030-baseline-audit.md`
Expected: `Summary: 0 error(s)`.

- [ ] **Step 3: Commit**

```bash
git add docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs(audit): #798 retrospect addendum — Codex round 3 follow-up applied

R3#1 / R3#2 の解消を audit doc に記録。PNG overwriting は §7 out of scope。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Full QA gate + Iron Law 6 Pre-flight

**Files:** (none modified unless the QA gate surfaces fixups)

- [ ] **Step 1: Full test suite**

Run: `python -m pytest -v`
Expected: all tests pass, including the new R3#1 (4 tests) + R3#2 (3 tests) + the audit doc unchanged behavior.

- [ ] **Step 2: ruff check + format**

Run:

```bash
ruff check .
ruff format --check .
```

Expected: no errors. If any, fix in place and `git commit -m "chore(audit): #798 ruff fixups"`.

- [ ] **Step 3: pyright**

Run: `pyright`
Expected: no errors. If any, fix in place and commit.

- [ ] **Step 4: markdownlint full sweep**

Run: `bash scripts/check-markdownlint.sh`
Expected: `Summary: 0 error(s)` across all .md files.

- [ ] **Step 5: Iron Law 6 Pre-flight Step 0 (parallel PR hard gate)**

Run: `gh pr list --search "#798" --state open --repo Idios/kobutachan-allaganeye`
Expected: zero matches (no other in-flight PR for this issue).

- [ ] **Step 6: Iron Law 6 Pre-flight Steps 1-2 (base sync)**

Run:

```bash
git fetch origin develop-0.3.0
git log HEAD..origin/develop-0.3.0 --oneline
```

If any unpicked commits exist downstream of develop-0.3.0 that touch `scripts/audit-*.py` or `tests/test_audit_*.py`, rebase or merge before continuing. Expected normally: empty list.

- [ ] **Step 7: Iron Law 6 Pre-flight Step 4 (parallel re-check)**

Run: `gh pr list --search "#798 audit hardening" --state all --repo Idios/kobutachan-allaganeye`
Expected: zero matches besides this branch.

- [ ] **Step 8: Iron Law 6 Pre-flight Step 5 (Codex adversarial-review)**

Hand off to operator (Idios) to invoke:

```text
/codex:adversarial-review focus="Issue #798 implementation — verify R3#1 (source_size_bytes REQUIRED + skip flag + fail-close) and R3#2 (audit-prepare atomic flow). Probe for Iron Law 3 scope creep, encoding boundary issues, Windows directory-rename atomicity, race conditions between rmtree+rename, and any leftover silent-skip paths. Verify spec §6 acceptance criteria 1-9 are satisfied." --wait
```

Address any (A) findings inline before pushing the PR. (B) findings → new issue. (C) findings → existing issue comment.

- [ ] **Step 9: Push branch and open PR**

Run:

```bash
git push origin claude/audit-hardening-798
gh pr create \
  --base develop-0.3.0 \
  --title "feat(audit): #798 audit-{prepare,compare} reproducibility hardening" \
  --body-file - <<'EOF'
## 期待値

`scripts/audit-{prepare,compare}.py` の future re-run reproducibility を強化する。Codex Round 3 (Issue #798) で残った 2 件の medium finding を消化:

- R3#1: `source_size_bytes` を REQUIRED ground-truth field 化 + audit-compare main fail-close + `--skip-source-size-check` operator escape
- R3#2: audit-prepare main を `<label>.new/` + `<label>.csv.new` 経由の atomic rename / replace flow に書き直し

## 現状

- 親 audit deliverable PR: #799 (merged into develop-0.3.0 as `d1b3ac3`)
- Codex Round 3 finding は本 PR で消化
- 5 ground-truth files (`obs-2026{0116,0118,0119,0127,0209}.json`) は既に `source_size_bytes` を持つため schema migration 不要

## 修正内容

| Task | 変更 |
| --- | --- |
| 1 | `_REQUIRED_GROUND_TRUTH_FIELDS` に `source_size_bytes` 追加 |
| 2 | `validate_ground_truth_against_baseline` に `skip_source_size_check` parameter 追加 |
| 3 | `audit-compare` main で video 未解決時 WARNING + fail-close (exit 3) |
| 4 | `audit-compare` に `--skip-source-size-check` CLI flag |
| 5 | `audit-prepare` main を temp-sibling + atomic rename flow に書き直し |
| 6 | `docs/v030-baseline-audit.md` retrospect 節に R3 follow-up 記録 |

## Self-Test Report

- [x] `python -m pytest -v` PASS
- [x] `ruff check .` clean
- [x] `ruff format --check .` clean
- [x] `pyright` clean
- [x] `bash scripts/check-markdownlint.sh` clean
- [x] `/codex:adversarial-review` 実行 (Step 8、結果: <0 findings | A 件本 PR 内 fix>)

## 関連

- 親 issue: #798
- predecessor PR: #799 (#796 audit deliverable)
- spec: `docs/superpowers/specs/2026-05-20-audit-script-hardening-design.md`
- plan: `docs/superpowers/plans/2026-05-20-audit-script-hardening.md`
- 並行 deferred issue: #797 (本 PR scope 外、PR #793 merge 後の verification 待ち)

Refs #798
EOF
```

Expected: PR opens against `develop-0.3.0` with Iron Law 4 compliant body (no Closes/Fixes/Resolves).

- [ ] **Step 10: Hand off to `/iterate-review`**

After PR open, invoke `/iterate-review <PR#>` (user or agent path per `docs/l2-workflow.md`) for the review-fix loop to convergence. Loop terminal state: all (A)/(B)/(C) zero, summary comment posted, LGTM signal to operator for manual merge.

---

## Self-Review

**Spec coverage check** (against `docs/superpowers/specs/2026-05-20-audit-script-hardening-design.md`):

| Spec section | Task(s) | Coverage |
| --- | --- | --- |
| §3.1 schema constant change | Task 1 | ✓ |
| §3.1 validate skip_source_size_check parameter | Task 2 | ✓ |
| §3.1 validate raises when actual=None and not skipped | Task 2 | ✓ |
| §3.1 main fail-close on unresolved video | Task 3 | ✓ |
| §3.1 --skip-source-size-check flag + stderr WARNING | Task 4 | ✓ |
| §3.2 R3#2 temp-sibling + atomic rename | Task 5 | ✓ |
| §3.3 audit doc addendum | Task 6 | ✓ |
| §5.1 R3#1 tests (5 listed) | Task 1 (1) + Task 2 (2) + Task 3 (2) + Task 4 (1) | ✓ |
| §5.2 R3#2 tests (3 listed) | Task 5 (3) | ✓ |
| §6 受け入れ条件 1-7 | Tasks 1-5 | ✓ |
| §6 受け入れ条件 8 (full QA gate) | Task 7 Steps 1-4 | ✓ |
| §6 受け入れ条件 9 (Codex Pre-flight) | Task 7 Step 8 | ✓ |
| §7 out of scope (#797 / PNG overwriting) | Plan does not touch detector path; PNG handling unchanged | ✓ |

**Placeholder scan**: no TBD / "add appropriate error handling" / "similar to Task N". All code blocks contain full source. All commands are runnable.

**Type consistency check**:

- `_REQUIRED_GROUND_TRUTH_FIELDS` (Task 1) is the exact identifier referenced in Task 2's validate body and the new tests.
- `skip_source_size_check` parameter (Task 2) is the exact identifier used in Task 4's main call and the new test argv `--skip-source-size-check`.
- `.new` suffix convention (Task 5) consistent across tests, implementation, and recovery test.
- Filenames `obs-fake.csv` / `obs-fake.csv.new` / `obs-fake.new` consistent in Task 5 tests and impl.

**TDD discipline**: every task has Step 1 (failing test) → Step 2 (verify fails) → Step 3 (implement) → Step 4 (verify passes) → Step 5 (commit). Task 7 is the integration gate, no test addition.

**Commit boundaries**: each task ends in one commit. 6 implementation commits + 1 doc commit + optional QA fixups + push. Total expected commits on the branch before PR: 6-8.
