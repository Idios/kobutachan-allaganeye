"""Compare detection result JSON files for regression testing.

Compares metadata.json files (baseline vs current) bit-exactly after dropping
the time-varying `detected_at` field. Used for v0.3.0 L3 Pillar 3 (perf) and
Phase 2b (scorebar ROI) regression detection.

Usage:
    python scripts/compare-baseline.py <baseline.json> <current.json>

Exit codes:
    0: bit-exact match
    1: any difference detected
    2: file load error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def normalize_metadata(raw: dict) -> dict:
    """Project `raw` to the baseline surface defined in spec §8.2.

    Spec §8.2 defines the metadata baseline as `matches` + `gaps`, excluding
    `detected_at` and all other top-level fields (which may evolve independently
    of detection regression — e.g., `source`, `detection_params`, `system_info`).
    """
    return {
        "matches": raw.get("matches", []),
        "gaps": raw.get("gaps", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    args = parser.parse_args(argv)

    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        current = json.loads(args.current.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    norm_baseline = normalize_metadata(baseline)
    norm_current = normalize_metadata(current)

    if norm_baseline == norm_current:
        print(
            "MATCH: baseline and current are bit-exact on spec §8.2 surface (matches + gaps)."
        )
        return 0

    print("DIFF: baseline and current differ.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
