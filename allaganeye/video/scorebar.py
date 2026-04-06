"""Scorebar-based blackout classification for FL match detection."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
from pathlib import Path

from allaganeye.video.detector import (
    _has_scorebar,
    _probe_frame_rgb,
    _resolve_workers,
)


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
    pre_timestamps = [max(0.0, region[0] - d) for d in (3.0, 2.0, 1.0)]
    post_timestamps = [min(duration, region[1] + d) for d in (1.0, 2.0, 3.0)]

    pre_results = _probe_scorebar_context(video_path, pre_timestamps, height, workers)
    post_results = _probe_scorebar_context(video_path, post_timestamps, height, workers)

    pre_has = _majority_scorebar(pre_results)
    post_has = _majority_scorebar(post_results)

    if pre_has is None or post_has is None:
        return "unknown"
    if pre_has and post_has:
        return "in_match"
    if pre_has or post_has:
        return "match_boundary"
    return "non_fl"


_IN_MATCH_MAX_DURATION = 5.0
"""Maximum blackout duration to consider as in-match (e.g. character down).

Only ``"in_match"`` blackouts shorter than this are removed.  Longer
``"in_match"`` blackouts are FL match boundaries (7s+ for Pattern A,
20s+ for Pattern B after transition expansion) and must be kept.

Threshold: character down = 1.5-3s (refined), FL boundary = 7s+.
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
    - Short ``"in_match"`` blackouts (< 5s, e.g. character down, #107)
    - ``"non_fl"`` blackouts (non-FL content boundaries, #109)

    Keeps:
    - Long ``"in_match"`` blackouts (>= 5s, FL match boundaries)
    - ``"match_boundary"`` (FL match start/end)
    - ``"unknown"`` (probe failure → safe side, keep boundary)
    """
    kept: list[tuple[float, float]] = []
    for region in blackout_regions:
        classification = classify_blackout(
            video_path, region, duration, height, workers
        )
        region_duration = region[1] - region[0]

        if classification == "in_match" and region_duration < _IN_MATCH_MAX_DURATION:
            continue  # short in_match = character down → remove
        if classification == "non_fl":
            continue  # non-FL → remove

        kept.append(region)
    return kept
