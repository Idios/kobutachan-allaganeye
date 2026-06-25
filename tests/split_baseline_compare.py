"""Helpers for split (-c copy) bit-exact baseline comparison (#844 W5, P2-22).

Non-test module (no test_ prefix -> pytest does not collect it). Imported by the
slow gate in test_v030_baseline_regression.py and unit-tested in
test_split_baseline_compare.py. Mirrors the tests/presence_harness.py pattern.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Chunked SHA-256 (avoids loading multi-GB split outputs into memory)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def diff_split_against_baseline(
    out_dir: Path, expected_splits: list[dict]
) -> list[str]:
    """Return human-readable mismatch lines; empty list == bit-exact match.

    Size and sha256 are checked independently, so a single damaged file may
    produce two entries (one size line and one sha256 line) to surface the full
    defect picture in one run. The produced ``*.mp4`` set is also compared against
    the expected set, so an extra/duplicate/trailing output file is flagged (a
    true output-set gate, not just a per-expected-file check).
    """
    problems: list[str] = []
    for sp in expected_splits:
        produced = out_dir / sp["output_file"]
        if not produced.exists():
            problems.append(f"missing output: {sp['output_file']}")
            continue
        size = produced.stat().st_size
        if size != sp["size_bytes"]:
            problems.append(f"{sp['output_file']} size {size} != {sp['size_bytes']}")
        sha = sha256_file(produced)
        if sha != sp["sha256"]:
            problems.append(
                f"{sp['output_file']} sha256 {sha[:12]} != {sp['sha256'][:12]}"
            )
    expected_names = {sp["output_file"] for sp in expected_splits}
    produced_names = {p.name for p in out_dir.glob("*.mp4")}
    for extra in sorted(produced_names - expected_names):
        problems.append(f"unexpected output file: {extra}")
    return problems
