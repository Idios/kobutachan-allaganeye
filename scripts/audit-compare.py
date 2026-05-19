"""Audit compare: classify diffs between current baseline and Idios ground truth.

Compares matches[] from tests/baselines/v0.3.0/<label>.metadata.json against
tests/baselines/v0.3.0/ground-truth/<label>.json with tolerance_sec from the
ground truth file (default 1s). Emits a markdown finding table ready to paste
into docs/v030-baseline-audit.md.

See: docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md §3.3 / §5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _extract_boundaries(
    matches: list[dict[str, Any]],
) -> list[tuple[int | None, str, float]]:
    """Return (index, kind, timestamp) for each match start/end."""
    out: list[tuple[int | None, str, float]] = []
    for m in matches:
        out.append((m.get("index"), "start", float(m["start_time"])))
        out.append((m.get("index"), "end", float(m["end_time"])))
    return out


def classify_findings(
    baseline: dict[str, Any], ground_truth: dict[str, Any]
) -> list[dict[str, Any]]:
    """Classify each ground_truth / baseline boundary into the 4 finding types."""
    tolerance = float(ground_truth.get("tolerance_sec", 1))
    b_boundaries = _extract_boundaries(baseline.get("matches", []))
    g_boundaries = _extract_boundaries(ground_truth.get("matches", []))

    matched_b: set[int] = set()
    findings: list[dict[str, Any]] = []

    # Walk ground truth: find best match in baseline within tolerance
    for g_idx, g_kind, g_ts in g_boundaries:
        best_b: int | None = None
        best_delta: float = float("inf")
        for i, (_b_idx, b_kind, b_ts) in enumerate(b_boundaries):
            if i in matched_b or b_kind != g_kind:
                continue
            delta = abs(g_ts - b_ts)
            if delta < best_delta:
                best_delta = delta
                best_b = i
        if best_b is not None and best_delta <= tolerance:
            matched_b.add(best_b)
            _b_idx_match, _b_kind_match, b_ts_match = b_boundaries[best_b]
            findings.append(
                {
                    "finding_type": "agreed",
                    "match_index_gt": g_idx,
                    "boundary": g_kind,
                    "baseline_ts": b_ts_match,
                    "ground_truth_ts": g_ts,
                    "delta_sec": g_ts - b_ts_match,
                }
            )
        elif best_b is not None and best_delta > tolerance:
            # Closest baseline boundary exists but outside tolerance -> shift
            matched_b.add(best_b)
            _b_idx_match, _b_kind_match, b_ts_match = b_boundaries[best_b]
            findings.append(
                {
                    "finding_type": "boundary_shift",
                    "match_index_gt": g_idx,
                    "boundary": g_kind,
                    "baseline_ts": b_ts_match,
                    "ground_truth_ts": g_ts,
                    "delta_sec": g_ts - b_ts_match,
                }
            )
        else:
            findings.append(
                {
                    "finding_type": "silent_miss",
                    "match_index_gt": g_idx,
                    "boundary": g_kind,
                    "baseline_ts": None,
                    "ground_truth_ts": g_ts,
                    "delta_sec": None,
                }
            )

    # Unmatched baseline boundaries -> false positive
    for i, (b_idx, b_kind, b_ts) in enumerate(b_boundaries):
        if i in matched_b:
            continue
        findings.append(
            {
                "finding_type": "false_positive",
                "match_index_gt": None,
                "match_index_baseline": b_idx,
                "boundary": b_kind,
                "baseline_ts": b_ts,
                "ground_truth_ts": None,
                "delta_sec": None,
            }
        )

    return findings


def format_markdown(
    findings: list[dict[str, Any]],
    *,
    label: str,
    baseline: dict[str, Any],
    ground_truth: dict[str, Any],
) -> str:
    """Format findings as a markdown section. Filled in Task 8."""
    return f"## {label}\n\n(format_markdown stub — {len(findings)} findings)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording_label", help="e.g., obs-20260116")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path("tests/baselines/v0.3.0"),
    )
    parser.add_argument(
        "--ground-truth-dir",
        type=Path,
        default=Path("tests/baselines/v0.3.0/ground-truth"),
    )
    args = parser.parse_args(argv)

    baseline_path = args.baseline_dir / f"{args.recording_label}.metadata.json"
    ground_truth_path = args.ground_truth_dir / f"{args.recording_label}.json"

    for p in (baseline_path, ground_truth_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 2

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))

    findings = classify_findings(baseline, ground_truth)
    print(
        format_markdown(
            findings,
            label=args.recording_label,
            baseline=baseline,
            ground_truth=ground_truth,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
