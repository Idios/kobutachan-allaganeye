"""Tests for scripts/audit-compare.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit-compare.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("audit_compare", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classify_findings_all_agreed():
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 49.125, "end_time": 1054.5, "type": "fl_match"},
        ]
    }
    ground_truth = {
        "matches": [
            {"index": 1, "start_time": 49, "end_time": 1055, "type": "fl_match"},
        ],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["agreed", "agreed"]


def test_classify_findings_silent_miss():
    """Ground truth has a boundary that baseline does not."""
    mod = _load_module()
    baseline = {"matches": []}
    ground_truth = {
        "matches": [
            {"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"},
        ],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["silent_miss", "silent_miss"]


def test_classify_findings_false_positive():
    """Baseline has a boundary that ground truth does not."""
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"},
        ]
    }
    ground_truth = {"matches": [], "tolerance_sec": 1}
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["false_positive", "false_positive"]


def test_classify_findings_boundary_shift():
    """Same boundary count but timestamp drifts beyond tolerance."""
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"},
        ]
    }
    ground_truth = {
        "matches": [
            # start within tolerance, end drifts by 5s
            {"index": 1, "start_time": 50.5, "end_time": 1005, "type": "fl_match"},
        ],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["agreed", "boundary_shift"]


def test_classify_findings_includes_delta():
    """Each finding records baseline / ground truth ts and delta."""
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"}
        ]
    }
    ground_truth = {
        "matches": [
            {"index": 1, "start_time": 53, "end_time": 1000, "type": "fl_match"}
        ],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    shift = findings[0]
    assert shift["finding_type"] == "boundary_shift"
    assert shift["baseline_ts"] == 50
    assert shift["ground_truth_ts"] == 53
    assert shift["delta_sec"] == pytest.approx(3.0)


def test_format_markdown_contains_header_and_table():
    mod = _load_module()
    findings = [
        {
            "finding_type": "agreed",
            "match_index_gt": 1,
            "boundary": "start",
            "baseline_ts": 49.125,
            "ground_truth_ts": 49,
            "delta_sec": -0.125,
        },
        {
            "finding_type": "boundary_shift",
            "match_index_gt": 3,
            "boundary": "end",
            "baseline_ts": 3367.125,
            "ground_truth_ts": 3230.5,
            "delta_sec": -136.625,
        },
        {
            "finding_type": "silent_miss",
            "match_index_gt": 4,
            "boundary": "start",
            "baseline_ts": None,
            "ground_truth_ts": 4000.0,
            "delta_sec": None,
        },
    ]
    baseline = {"source": "20260116/2026-01-16.mkv", "matches": [{}, {}, {}]}
    ground_truth = {
        "source_dir_label": "obs-20260116",
        "tolerance_sec": 1,
        "matches": [{}, {}, {}, {}],
    }
    out = mod.format_markdown(
        findings, label="obs-20260116", baseline=baseline, ground_truth=ground_truth
    )
    assert "## obs-20260116" in out
    # Note: format_markdown emits literal U+00B1 (plus-minus); build the expected
    # substring via chr() so this source file stays pure ASCII (test_ascii_guard).
    assert f"Tolerance: {chr(0x00B1)}1" in out
    assert "Ground truth: 4 matches" in out
    assert "Current baseline: 3 matches" in out
    # Table contains all 3 findings
    assert "agreed" in out
    assert "boundary_shift" in out
    assert "silent_miss" in out
    assert "-136.625" in out


def test_validate_ground_truth_against_baseline_ok():
    mod = _load_module()
    baseline = {"source": "20260116/x.mkv", "matches": []}
    ground_truth = {
        "source_file": "20260116/x.mkv",
        "source_dir_label": "obs-20260116",
        "tolerance_sec": 5,
        "matches": [],
    }
    mod.validate_ground_truth_against_baseline(baseline, ground_truth)


def test_validate_ground_truth_source_mismatch_raises():
    mod = _load_module()
    baseline = {"source": "20260116/x.mkv", "matches": []}
    ground_truth = {
        "source_file": "20260118/y.mkv",
        "source_dir_label": "obs-20260118",
        "tolerance_sec": 5,
        "matches": [],
    }
    with pytest.raises(ValueError, match="does not match"):
        mod.validate_ground_truth_against_baseline(baseline, ground_truth)


def test_validate_ground_truth_missing_fields_raises():
    mod = _load_module()
    baseline = {"source": "x", "matches": []}
    ground_truth = {"source_file": "x", "matches": []}
    with pytest.raises(ValueError, match="missing required fields"):
        mod.validate_ground_truth_against_baseline(baseline, ground_truth)


def test_classify_findings_extra_baseline_match_yields_false_positive_not_shift():
    """Baseline has an extra match that GT does not. The new matcher should
    classify it as 2x false_positive, not silently absorb as boundary_shift."""
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 100, "end_time": 200, "type": "fl_match"},
            {"index": 2, "start_time": 500, "end_time": 600, "type": "fl_match"},
        ]
    }
    ground_truth = {
        "matches": [
            {"index": 1, "start_time": 100, "end_time": 200, "type": "fl_match"},
        ],
        "tolerance_sec": 5,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = sorted(f["finding_type"] for f in findings)
    assert types == ["agreed", "agreed", "false_positive", "false_positive"]


def test_classify_findings_missing_gt_match_yields_silent_miss_not_shift():
    """GT has an extra match that baseline does not. Should be 2x silent_miss."""
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 100, "end_time": 200, "type": "fl_match"},
        ]
    }
    ground_truth = {
        "matches": [
            {"index": 1, "start_time": 100, "end_time": 200, "type": "fl_match"},
            {"index": 2, "start_time": 500, "end_time": 600, "type": "fl_match"},
        ],
        "tolerance_sec": 5,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = sorted(f["finding_type"] for f in findings)
    assert types == ["agreed", "agreed", "silent_miss", "silent_miss"]


def test_validate_ground_truth_recording_label_mismatch_raises():
    """source_file matches but source_dir_label is wrong -> reject."""
    mod = _load_module()
    baseline = {"source": "20260116/x.mkv", "matches": []}
    ground_truth = {
        "source_file": "20260116/x.mkv",
        "source_dir_label": "obs-WRONG-LABEL",
        "tolerance_sec": 5,
        "matches": [],
    }
    with pytest.raises(ValueError, match="source_dir_label"):
        mod.validate_ground_truth_against_baseline(
            baseline, ground_truth, recording_label="obs-20260116"
        )


def test_validate_ground_truth_source_size_mismatch_raises():
    """source_file matches but on-disk file size differs from ground truth -> reject."""
    mod = _load_module()
    baseline = {"source": "20260116/x.mkv", "matches": []}
    ground_truth = {
        "source_file": "20260116/x.mkv",
        "source_dir_label": "obs-20260116",
        "source_size_bytes": 12345,
        "tolerance_sec": 5,
        "matches": [],
    }
    with pytest.raises(ValueError, match="source_size_bytes"):
        mod.validate_ground_truth_against_baseline(
            baseline, ground_truth, actual_source_size=99999
        )


def test_validate_ground_truth_recording_label_skipped_when_not_provided():
    """validate without recording_label should not raise on label issues."""
    mod = _load_module()
    baseline = {"source": "x.mkv", "matches": []}
    ground_truth = {
        "source_file": "x.mkv",
        "source_dir_label": "anything",
        "tolerance_sec": 5,
        "matches": [],
    }
    mod.validate_ground_truth_against_baseline(baseline, ground_truth)
