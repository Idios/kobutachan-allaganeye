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


_FINDING_ORDER = ("silent_miss", "false_positive", "boundary_shift", "agreed")


def _format_delta(delta: float | None) -> str:
    if delta is None:
        return "—"
    return f"{delta:+.3f}"


def _format_ts(ts: float | None) -> str:
    if ts is None:
        return "—"
    return f"{ts:.3f}"


def format_markdown(
    findings: list[dict[str, Any]],
    *,
    label: str,
    baseline: dict[str, Any],
    ground_truth: dict[str, Any],
) -> str:
    tolerance = ground_truth.get("tolerance_sec", 1)
    baseline_match_count = len(baseline.get("matches", []))
    gt_match_count = len(ground_truth.get("matches", []))
    source = baseline.get("source", "(unknown)")

    counts = {kind: 0 for kind in _FINDING_ORDER}
    for f in findings:
        counts[f["finding_type"]] = counts.get(f["finding_type"], 0) + 1

    lines: list[str] = []
    lines.append(f"## {label}")
    lines.append("")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Ground truth: {gt_match_count} matches (Idios manual)")
    lines.append(f"- Current baseline: {baseline_match_count} matches")
    lines.append(f"- Tolerance: ±{tolerance}s")
    lines.append(
        f"- Findings: {counts['silent_miss']} silent_miss / "
        f"{counts['false_positive']} false_positive / "
        f"{counts['boundary_shift']} boundary_shift / "
        f"{counts['agreed']} agreed"
    )
    lines.append("")
    lines.append("### Findings")
    lines.append("")
    lines.append(
        "| # | Type | Match | Boundary | Baseline ts | Ground truth ts | Delta | Classification (a/b/c) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    sorted_findings = sorted(
        findings, key=lambda f: _FINDING_ORDER.index(f["finding_type"])
    )
    for i, f in enumerate(sorted_findings, start=1):
        match_idx: int | str
        if f.get("match_index_gt") is not None:
            match_idx = f["match_index_gt"]
        elif f.get("match_index_baseline") is not None:
            match_idx = f["match_index_baseline"]
        else:
            match_idx = "—"
        lines.append(
            f"| {i} "
            f"| {f['finding_type']} "
            f"| {match_idx} "
            f"| {f['boundary']} "
            f"| {_format_ts(f['baseline_ts'])} "
            f"| {_format_ts(f['ground_truth_ts'])} "
            f"| {_format_delta(f['delta_sec'])} "
            f"| (TBD by Idios) |"
        )
    return "\n".join(lines)


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
