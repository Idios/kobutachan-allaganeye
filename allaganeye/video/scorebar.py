"""Scorebar-based blackout classification for FL match detection."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
from pathlib import Path

from allaganeye.video.detector import (
    _has_scorebar,
    _probe_frame_rgb,
    _resolve_workers,
)

logger = logging.getLogger(__name__)


def _probe_scorebar_context(
    video_path: Path,
    timestamps: list[float],
    height: int,
    workers: int | None,
) -> list[bool | None]:
    """Probe multiple timestamps and return has_scorebar for each.

    Returns a list aligned with timestamps: True/False/None per frame.
    """
    max_workers = _resolve_workers(workers)
    results: dict[float, bool | None] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_frame_rgb, video_path, t, height): t for t in timestamps
        }
        for future in as_completed(futures):
            t = futures[future]
            raw = future.result()
            results[t] = _has_scorebar(raw, height)

    return [results[t] for t in timestamps]


def _majority_scorebar(results: list[bool | None]) -> bool | None:
    """Majority vote from scorebar results, ignoring None (probe failures).

    Returns None if no successful probes.
    """
    valid = [r for r in results if r is not None]
    if not valid:
        return None
    return sum(valid) >= ceil(len(valid) / 2)


def classify_blackout(
    video_path: Path,
    region: tuple[float, float],
    duration: float,
    height: int,
    workers: int | None = None,
) -> str:
    """Classify a blackout region by scorebar context.

    Probes 3 frames before and 3 frames after the blackout at 1s intervals.
    Uses majority vote on has_scorebar to determine context.

    Returns one of:
    - ``"in_match"``: both sides have scorebar → in-match blackout (#107)
    - ``"match_boundary"``: one side has scorebar → match start/end
    - ``"non_fl"``: neither side has scorebar → non-FL blackout (#109)
    - ``"unknown"``: all probes failed on either side → keep boundary (safe)
    """
    pre_timestamps = sorted(set(max(0.0, region[0] - d) for d in (3.0, 2.0, 1.0)))
    post_timestamps = sorted(set(min(duration, region[1] + d) for d in (1.0, 2.0, 3.0)))

    pre_results = _probe_scorebar_context(video_path, pre_timestamps, height, workers)
    post_results = _probe_scorebar_context(video_path, post_timestamps, height, workers)

    pre_has = _majority_scorebar(pre_results)
    post_has = _majority_scorebar(post_results)

    if pre_has is None or post_has is None:
        classification = "unknown"
    elif pre_has and post_has:
        classification = "in_match"
    elif pre_has or post_has:
        classification = "match_boundary"
    else:
        classification = "non_fl"

    logger.debug(
        "classify region [%.1f-%.1f] (%.1fs): "
        "pre=%s (votes=%s) post=%s (votes=%s) → %s",
        region[0],
        region[1],
        region[1] - region[0],
        pre_has,
        pre_results,
        post_has,
        post_results,
        classification,
    )

    return classification


_IN_MATCH_MAX_DURATION = 3.5
"""Maximum blackout duration to consider as in-match (e.g. character down).

Only ``"in_match"`` blackouts shorter than this are removed.  Longer
``"in_match"`` blackouts are FL match boundaries and must be kept.

Threshold: character down = 1.0-2.0s (refined measurement), short FL
boundary = 4.5s+.  3.5s sits in the gap with 1.5s margin on each side.
"""


_MERGE_GAP_MAX = 600.0
"""Maximum gap (seconds) between consecutive match_boundary regions to merge.

FL match transitions often produce two blackouts separated by a non-FL
segment (result screen, lobby, queue).  When the gap is short and has no
scorebar at the midpoint, the two boundaries are merged into one spanning
the full transition.
"""


def filter_blackouts_with_scorebar(
    video_path: Path,
    blackout_regions: list[tuple[float, float]],
    duration: float,
    height: int,
    workers: int | None = None,
) -> list[tuple[float, float]]:
    """Filter blackout regions using scorebar context and duration.

    Removes:
    - Short ``"in_match"`` blackouts (< 3.5s, e.g. character down, #107)
    - ``"non_fl"`` blackouts (non-FL content boundaries, #109)

    Keeps:
    - Long ``"in_match"`` blackouts (>= 3.5s, FL match boundaries)
    - ``"match_boundary"`` (FL match start/end)
    - ``"unknown"`` (probe failure → safe side, keep boundary)

    Post-processing:
    - Merges consecutive ``"match_boundary"`` pairs separated by non-FL
      content (result screen / lobby) into a single boundary region.
    """
    kept: list[tuple[float, float]] = []
    classifications: list[str] = []
    for region in blackout_regions:
        classification = classify_blackout(
            video_path, region, duration, height, workers
        )
        region_duration = region[1] - region[0]

        if classification == "in_match" and region_duration < _IN_MATCH_MAX_DURATION:
            logger.info(
                "REMOVE [%.1f-%.1f] (%.1fs): %s (short in_match)",
                region[0],
                region[1],
                region_duration,
                classification,
            )
            continue
        if classification == "non_fl":
            logger.info(
                "REMOVE [%.1f-%.1f] (%.1fs): %s",
                region[0],
                region[1],
                region_duration,
                classification,
            )
            continue

        logger.info(
            "KEEP   [%.1f-%.1f] (%.1fs): %s",
            region[0],
            region[1],
            region_duration,
            classification,
        )
        kept.append(region)
        classifications.append(classification)

    return _merge_boundary_pairs(
        video_path, kept, classifications, duration, height, workers
    )


def _merge_boundary_pairs(
    video_path: Path,
    regions: list[tuple[float, float]],
    classifications: list[str],
    duration: float,
    height: int,
    workers: int | None,
) -> list[tuple[float, float]]:
    """Merge consecutive match_boundary pairs separated by non-FL content.

    FL match transitions often produce two blackouts:
      FL Match → blackout₁ (match_boundary) → lobby/result → blackout₂ (match_boundary) → FL Match
    The intermediate non-FL segment creates a false short "match".

    When two consecutive match_boundary regions have a gap < _MERGE_GAP_MAX
    and the gap midpoint has no scorebar, merge them into one region.
    """
    if len(regions) < 2:
        return regions

    merged: list[tuple[float, float]] = []
    i = 0
    while i < len(regions):
        if (
            i + 1 < len(regions)
            and classifications[i] == "match_boundary"
            and classifications[i + 1] == "match_boundary"
        ):
            gap = regions[i + 1][0] - regions[i][1]
            if gap <= _MERGE_GAP_MAX:
                # Probe 9 points evenly across the gap to reliably
                # detect FL match content (scorebar intermittently visible)
                gap_start = regions[i][1]
                gap_end = regions[i + 1][0]
                probe_points = [
                    gap_start + (gap_end - gap_start) * k / 10
                    for k in range(1, 10)
                ]
                probe_results = [
                    _has_scorebar(_probe_frame_rgb(video_path, t, height), height)
                    for t in probe_points
                ]
                all_valid = all(r is not None for r in probe_results)
                any_scorebar = any(r is True for r in probe_results)
                if all_valid and not any_scorebar:
                    merged_region = (regions[i][0], regions[i + 1][1])
                    logger.info(
                        "MERGE  [%.1f-%.1f] + [%.1f-%.1f] → [%.1f-%.1f] "
                        "(gap=%.0fs, probes=%s)",
                        regions[i][0],
                        regions[i][1],
                        regions[i + 1][0],
                        regions[i + 1][1],
                        merged_region[0],
                        merged_region[1],
                        gap,
                        probe_results,
                    )
                    merged.append(merged_region)
                    i += 2
                    continue
                logger.debug(
                    "NO-MERGE [%.1f-%.1f] + [%.1f-%.1f] (gap=%.0fs, probes=%s)",
                    regions[i][0],
                    regions[i][1],
                    regions[i + 1][0],
                    regions[i + 1][1],
                    gap,
                    probe_results,
                )
        merged.append(regions[i])
        i += 1

    return merged
