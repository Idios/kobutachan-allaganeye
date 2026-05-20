"""Audit compare: classify diffs between current baseline and Idios ground truth.

Compares matches[] from tests/baselines/v0.3.0/<label>.metadata.json against
tests/baselines/v0.3.0/ground-truth/<label>.json with tolerance_sec from the
ground truth file (default 5s, see spec §3.2). Emits a markdown finding table
ready to paste into docs/v030-baseline-audit.md.

See: docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md §3.3 / §5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Reconfigure stdout to UTF-8 so the rendered markdown (which contains the
# U+00B1 character in the "Tolerance: ±Ns" line) is not mangled by the
# default cp932 codec on Windows terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


_REQUIRED_GROUND_TRUTH_FIELDS = (
    "source_file",
    "source_dir_label",
    "tolerance_sec",
    "matches",
    "source_size_bytes",
)


def validate_ground_truth_against_baseline(
    baseline: dict[str, Any],
    ground_truth: dict[str, Any],
    *,
    recording_label: str | None = None,
    actual_source_size: int | None = None,
) -> None:
    """Reject ground-truth files that do not describe the same recording.

    Raises ValueError if any of the following hold:
    - required schema fields are absent
    - baseline `source` != ground truth `source_file`
    - `recording_label` was supplied and != ground truth `source_dir_label`
    - `actual_source_size` was supplied and != ground truth `source_size_bytes`

    Codex adversarial reviews (2026-05-20 round 1 + round 2) flagged that
    matching only the relative source path is insufficient: a replaced /
    truncated recording at the same path, or a copy-pasted ground-truth
    file with the wrong label, would silently certify stale findings.
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
    if actual_source_size is not None and "source_size_bytes" in ground_truth:
        gt_size = ground_truth["source_size_bytes"]
        if gt_size != actual_source_size:
            raise ValueError(
                f"video file size ({actual_source_size}) does not match "
                f"ground truth source_size_bytes ({gt_size}); "
                "the recording may have been replaced or truncated"
            )


def _pair_matches_by_overlap(
    baseline_matches: list[dict[str, Any]],
    ground_truth_matches: list[dict[str, Any]],
) -> list[tuple[int | None, int | None]]:
    """Pair (baseline_idx, gt_idx) by greedy max time-range overlap.

    Each ground-truth match consumes at most one baseline match (whichever
    overlaps it the most). Unpaired ground-truth matches become
    `silent_miss` candidates; unpaired baseline matches become
    `false_positive` candidates. Pairing at match-level (not flat boundary
    level) ensures that an extra baseline match plus a missing ground-truth
    match are reported as both `false_positive` and `silent_miss` rather
    than collapsing into a single `boundary_shift` (Codex high finding,
    2026-05-20).
    """
    pairs: list[tuple[int | None, int | None]] = []
    used_baseline: set[int] = set()
    for g_i, g_m in enumerate(ground_truth_matches):
        g_start = float(g_m["start_time"])
        g_end = float(g_m["end_time"])
        best_b: int | None = None
        best_overlap: float = 0.0
        for b_i, b_m in enumerate(baseline_matches):
            if b_i in used_baseline:
                continue
            b_start = float(b_m["start_time"])
            b_end = float(b_m["end_time"])
            overlap = max(0.0, min(g_end, b_end) - max(g_start, b_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_b = b_i
        if best_overlap > 0:
            assert best_b is not None  # best_overlap > 0 implies best_b was set
            pairs.append((best_b, g_i))
            used_baseline.add(best_b)
        else:
            pairs.append((None, g_i))
    for b_i in range(len(baseline_matches)):
        if b_i not in used_baseline:
            pairs.append((b_i, None))
    return pairs


def classify_findings(
    baseline: dict[str, Any], ground_truth: dict[str, Any]
) -> list[dict[str, Any]]:
    """Classify each baseline / ground-truth boundary into the 4 finding types.

    Algorithm (rewritten 2026-05-20 per Codex finding): pair matches by
    maximum time-range overlap first, then evaluate per-paired-pair start
    and end deltas against `tolerance_sec`. Unpaired matches emit two
    boundary-level findings (silent_miss or false_positive).
    """
    tolerance = float(ground_truth.get("tolerance_sec", 5))
    baseline_matches = baseline.get("matches", [])
    gt_matches = ground_truth.get("matches", [])
    pairs = _pair_matches_by_overlap(baseline_matches, gt_matches)

    findings: list[dict[str, Any]] = []
    for b_i, g_i in pairs:
        if b_i is not None and g_i is not None:
            b_m = baseline_matches[b_i]
            g_m = gt_matches[g_i]
            for kind, key in (("start", "start_time"), ("end", "end_time")):
                b_ts = float(b_m[key])
                g_ts = float(g_m[key])
                delta = g_ts - b_ts
                finding_type = "agreed" if abs(delta) <= tolerance else "boundary_shift"
                findings.append(
                    {
                        "finding_type": finding_type,
                        "match_index_gt": g_m.get("index"),
                        "boundary": kind,
                        "baseline_ts": b_ts,
                        "ground_truth_ts": g_ts,
                        "delta_sec": delta,
                    }
                )
        elif b_i is None and g_i is not None:
            g_m = gt_matches[g_i]
            for kind, key in (("start", "start_time"), ("end", "end_time")):
                findings.append(
                    {
                        "finding_type": "silent_miss",
                        "match_index_gt": g_m.get("index"),
                        "boundary": kind,
                        "baseline_ts": None,
                        "ground_truth_ts": float(g_m[key]),
                        "delta_sec": None,
                    }
                )
        elif b_i is not None and g_i is None:
            b_m = baseline_matches[b_i]
            for kind, key in (("start", "start_time"), ("end", "end_time")):
                findings.append(
                    {
                        "finding_type": "false_positive",
                        "match_index_gt": None,
                        "match_index_baseline": b_m.get("index"),
                        "boundary": kind,
                        "baseline_ts": float(b_m[key]),
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
    tolerance = ground_truth.get("tolerance_sec", 5)
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

    actual_source_size: int | None = None
    sample_video_dir = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if sample_video_dir and "source" in baseline:
        video_candidate = Path(sample_video_dir) / baseline["source"]
        if video_candidate.exists():
            actual_source_size = video_candidate.stat().st_size

    try:
        validate_ground_truth_against_baseline(
            baseline,
            ground_truth,
            recording_label=args.recording_label,
            actual_source_size=actual_source_size,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

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
