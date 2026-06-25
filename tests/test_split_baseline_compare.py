"""Fast unit tests for the split bit-exact comparator (#844 W5, P2-22).

Non-slow (no video needed) so it runs in the default CI lane and provides the
red-verification that the gate actually FIRES on a sha/size/missing mismatch.
"""

from __future__ import annotations

from pathlib import Path

from tests.split_baseline_compare import diff_split_against_baseline, sha256_file


def test_matching_baseline_reports_no_problems(tmp_path: Path) -> None:
    f = tmp_path / "match_001.mp4"
    f.write_bytes(b"hello world")
    problems = diff_split_against_baseline(
        tmp_path,
        [{"output_file": "match_001.mp4", "size_bytes": 11, "sha256": sha256_file(f)}],
    )
    assert problems == []


def test_mismatch_baseline_fires(tmp_path: Path) -> None:
    f = tmp_path / "match_001.mp4"
    f.write_bytes(b"hello world")
    problems = diff_split_against_baseline(
        tmp_path,
        [
            {"output_file": "match_001.mp4", "size_bytes": 999, "sha256": "aa" * 32},
            {"output_file": "match_002.mp4", "size_bytes": 1, "sha256": "bb" * 32},
        ],
    )
    assert any("size" in p for p in problems)
    assert any("sha256" in p for p in problems)
    assert any("missing" in p for p in problems)


def test_unexpected_output_file_fires(tmp_path: Path) -> None:
    """An extra produced *.mp4 not in the baseline must be flagged (output-set gate)."""
    expected_file = tmp_path / "match_001.mp4"
    expected_file.write_bytes(b"hello world")
    (tmp_path / "match_002.mp4").write_bytes(b"surprise extra segment")
    problems = diff_split_against_baseline(
        tmp_path,
        [
            {
                "output_file": "match_001.mp4",
                "size_bytes": 11,
                "sha256": sha256_file(expected_file),
            }
        ],
    )
    assert any("unexpected output file" in p for p in problems)
    assert any("match_002.mp4" in p for p in problems)
