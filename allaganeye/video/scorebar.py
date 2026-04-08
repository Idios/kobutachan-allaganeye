"""Scorebar-based blackout classification for FL match detection."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
from pathlib import Path

import numpy as np

from allaganeye.video.detector import (
    _SAMPLE_WIDTH,
    _SCOREBAR_ROI_X_END,
    _SCOREBAR_ROI_X_START,
    _SCOREBAR_ROI_Y_END,
    _SCOREBAR_ROI_Y_START,
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

    Returns a list aligned with *timestamps*: True/False/None per frame.
    Duplicate timestamps are probed only once; results are shared.
    """
    max_workers = _resolve_workers(workers)
    unique_ts = sorted(set(timestamps))
    results: dict[float, bool | None] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_frame_rgb, video_path, t, height): t for t in unique_ts
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


_STATIC_SCREEN_MAD_THRESHOLD = 0.5
"""Max scorebar-ROI MAD to consider consecutive frames as a static screen.

Loading/result screens are pixel-identical across seconds, giving MAD ≈ 0.
FL match frames always differ (character motion, particles) with MAD > 1.5.
Threshold 0.5 sits well inside the gap.
"""


def _is_static_screen(
    video_path: Path,
    timestamps: list[float],
    height: int,
    workers: int | None,
) -> bool:
    """Detect static screens (loading/result) via scorebar ROI frame diff.

    Probes frames at the given timestamps and computes the mean absolute
    difference (MAD) of the scorebar ROI pixels between consecutive pairs.
    If the **minimum** MAD across all pairs is below threshold, the frames
    show a static screen.

    Using min() tolerates a single screen transition within the window
    (one pair may have high MAD from a screen change, but the next pair
    will be static).

    Returns False if fewer than 2 frames are successfully probed.
    """
    max_workers = _resolve_workers(workers)
    unique_ts = sorted(set(timestamps))

    raw_frames: dict[float, bytes | None] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_frame_rgb, video_path, t, height): t for t in unique_ts
        }
        for future in as_completed(futures):
            t = futures[future]
            raw_frames[t] = future.result()

    ordered = [raw_frames[t] for t in unique_ts]
    valid = [r for r in ordered if r is not None]
    if len(valid) < 2:
        return False

    x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
    x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
    y1 = int(height * _SCOREBAR_ROI_Y_START)
    y2 = int(height * _SCOREBAR_ROI_Y_END)

    rois = []
    for raw in valid:
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, _SAMPLE_WIDTH, 3)
        rois.append(frame[y1:y2, x1:x2, :].astype(np.int16))

    mads = []
    for i in range(len(rois) - 1):
        mad = float(np.mean(np.abs(rois[i] - rois[i + 1])))
        mads.append(mad)

    min_mad = min(mads)
    is_static = min_mad < _STATIC_SCREEN_MAD_THRESHOLD

    logger.debug(
        "static_screen: timestamps=%s mads=%s min=%.2f thr=%.1f → %s",
        [f"{t:.1f}" for t in unique_ts],
        [f"{m:.2f}" for m in mads],
        min_mad,
        _STATIC_SCREEN_MAD_THRESHOLD,
        is_static,
    )

    return is_static


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

    # Override scorebar detection on static screens (loading/result).
    # Loading screens can trigger _has_scorebar due to color patterns
    # that mimic scorebar channel separation.  (#201)
    if pre_has and post_has:
        if _is_static_screen(video_path, post_timestamps, height, workers):
            logger.debug(
                "static_screen override: post side [%.1f-%.1f]",
                region[0],
                region[1],
            )
            post_has = False
        if pre_has and post_has:
            if _is_static_screen(video_path, pre_timestamps, height, workers):
                logger.debug(
                    "static_screen override: pre side [%.1f-%.1f]",
                    region[0],
                    region[1],
                )
                pre_has = False

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


_MERGE_MAX_SCOREBAR_HITS = 2
"""Max scorebar detections in gap probes to still allow merging.

A single borderline false positive (channel std just above threshold)
should not block merging of consecutive match_boundary pairs.  Real
FL match content produces scorebar hits on 4+ out of 9 probe points.
Allowing up to 1 hit (< 2) absorbs non-deterministic ffmpeg seek
variations at threshold boundaries.  (#200)
"""

_MERGE_GAP_MAX = 600.0
"""Maximum gap (seconds) between consecutive match_boundary regions to merge.

FL match transitions often produce two blackouts separated by a non-FL
segment (result screen, lobby, queue).  When the gap is short and has no
scorebar at any of 9 probe points, the two boundaries are merged into
one spanning the full transition.

Measured gap durations (non-FL content between FL matches):
- Result screen: 83-266s (1.4-4.4min)
- Lobby/queue: 232-468s (3.9-7.8min)
600s (10min) covers observed lobby gaps with margin.  9-point scorebar
probes guard against merging real FL match content.
"""


def filter_blackouts_with_scorebar(
    video_path: Path,
    blackout_regions: list[tuple[float, float]],
    duration: float,
    height: int,
    workers: int | None = None,
) -> tuple[list[tuple[float, float]], list[str]]:
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

    Returns:
        Tuple of (filtered_regions, filtered_classifications).
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
) -> tuple[list[tuple[float, float]], list[str]]:
    """Merge consecutive match_boundary pairs separated by non-FL content.

    FL match transitions often produce two blackouts:
      FL Match → blackout₁ (match_boundary) → lobby/result → blackout₂ (match_boundary) → FL Match
    The intermediate non-FL segment creates a false short "match".

    When two consecutive match_boundary regions have a gap < _MERGE_GAP_MAX
    and the gap midpoint has no scorebar, merge them into one region.

    Returns:
        Tuple of (merged_regions, merged_classifications).
    """
    if len(regions) < 2:
        return regions, classifications

    merged: list[tuple[float, float]] = []
    merged_cls: list[str] = []
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
                    gap_start + (gap_end - gap_start) * k / 10 for k in range(1, 10)
                ]
                probe_results = _probe_scorebar_context(
                    video_path, probe_points, height, workers
                )
                all_valid = all(r is not None for r in probe_results)
                scorebar_count = sum(1 for r in probe_results if r is True)
                if all_valid and scorebar_count < _MERGE_MAX_SCOREBAR_HITS:
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
                    merged_cls.append("match_boundary")
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
        merged_cls.append(classifications[i])
        i += 1

    return merged, merged_cls
