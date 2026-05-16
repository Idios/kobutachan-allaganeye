"""Scorebar-based blackout classification for FL match detection."""

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from math import ceil
from pathlib import Path

import numpy as np

from allaganeye.audio.matcher import BgmHit
from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import (
    DetectionStats,
    _SAMPLE_WIDTH,
    _SCOREBAR_METHOD,
    _SCOREBAR_ROI_X_END,
    _SCOREBAR_ROI_X_START,
    _SCOREBAR_ROI_Y_END,
    _SCOREBAR_ROI_Y_START,
    _has_scorebar,
    _has_scorebar_v2,
    _probe_frame_rgb,
    _probe_frame_rgb_hires,
    _resolve_workers,
)

logger = logging.getLogger(__name__)


def _probe_scorebar_context(
    video_path: Path,
    timestamps: list[float],
    height: int,
    workers: int | None,
) -> tuple[list[bool | None], list[bytes | None]]:
    """Probe multiple timestamps and return has_scorebar + raw frames.

    Returns a tuple of two lists aligned with *timestamps*:
    - scorebar results: True/False/None per frame
    - raw RGB frame bytes: bytes/None per frame (low-res for static detection)

    When ``_SCOREBAR_METHOD == "v2"``, probes at 1920x1080 for GC-emblem
    3-point AND detection.  V2 False is used as-is (no V1 fallback) to
    avoid V1 FP on lobby backgrounds that would prevent correct merge
    of match_boundary pairs.  V2 FN on UI-hidden in-match frames is
    acceptable because ``classify_blackout``'s 3-frame majority vote
    and downstream merge logic handle isolated false negatives.

    Duplicate timestamps are probed only once; results are shared.
    """
    max_workers = _resolve_workers(workers)
    use_v2 = _SCOREBAR_METHOD == "v2"
    unique_ts = sorted(set(timestamps))
    scorebar_results: dict[float, bool | None] = {}
    raw_frames: dict[float, bytes | None] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Always probe low-res for static screen detection (classify_blackout)
        lo_futures = {
            pool.submit(_probe_frame_rgb, video_path, t, height): t for t in unique_ts
        }
        # V2: also probe high-res for emblem detection
        hi_futures: dict[Future[bytes | None], float] = {}
        if use_v2:
            hi_futures = {
                pool.submit(_probe_frame_rgb_hires, video_path, t): t for t in unique_ts
            }

        # Collect low-res results
        for future in as_completed(lo_futures):
            t = lo_futures[future]
            try:
                raw = future.result()
            except VideoProcessingError:
                raw = None
            raw_frames[t] = raw

        # Collect high-res results and run V2 detection
        hi_raws: dict[float, bytes | None] = {}
        if use_v2:
            for future in as_completed(hi_futures):
                t = hi_futures[future]
                try:
                    raw = future.result()
                except VideoProcessingError:
                    raw = None
                hi_raws[t] = raw

        # Determine scorebar results.
        # V2 True -> True (high specificity, eliminates lobby FP).
        # V2 False -> False (V1 fallback disabled: V1 has FP on lobby
        #   backgrounds that prevent correct merge of match_boundary
        #   pairs; V2 FN on UI-hidden in-match frames is acceptable
        #   because classify_blackout's 3-frame majority vote and
        #   downstream merge logic handle isolated FN).
        # V2 None -> V1 (opencv not installed).
        for t in unique_ts:
            if use_v2:
                v2_result = _has_scorebar_v2(hi_raws.get(t))
                if v2_result is not None:
                    scorebar_results[t] = v2_result
                else:
                    # V2 failed (e.g. no opencv) -> use V1
                    scorebar_results[t] = _has_scorebar(raw_frames[t], height)
            else:
                scorebar_results[t] = _has_scorebar(raw_frames[t], height)

    return (
        [scorebar_results[t] for t in timestamps],
        [raw_frames[t] for t in timestamps],
    )


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

Loading/result screens are pixel-identical across seconds, giving MAD ~= 0.
FL match frames always differ (character motion, particles) with MAD > 1.5.
Threshold 0.5 sits well inside the gap.
"""


def _is_static_from_frames(
    raw_frames: Sequence[bytes | None],
    height: int,
) -> bool:
    """Detect static screens (loading/result) via scorebar ROI frame diff.

    Computes the mean absolute difference (MAD) of the scorebar ROI pixels
    between consecutive frame pairs.  If the **minimum** MAD across all
    pairs is below threshold, the frames show a static screen.

    Using min() tolerates a single screen transition within the window
    (one pair may have high MAD from a screen change, but the next pair
    will be static).  False positives from ffmpeg keyframe aliasing are
    mitigated by the A1+A2 checks in ``_has_scorebar``, which reduce the
    number of blackouts reaching the ``in_match`` classification path
    where this check is applied.

    Returns False if fewer than 2 valid frames are provided.
    """
    valid = [r for r in raw_frames if r is not None]
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
        "static_screen: frames=%d mads=%s min=%.2f thr=%.1f -> %s",
        len(raw_frames),
        [f"{m:.2f}" for m in mads],
        min_mad,
        _STATIC_SCREEN_MAD_THRESHOLD,
        is_static,
    )

    return is_static


_IN_MATCH_MAX_DURATION = 3.5
"""Maximum blackout duration to consider as in-match (e.g. character down).

Only ``"in_match"`` blackouts shorter than this are removed.  Longer
``"in_match"`` blackouts are FL match boundaries and must be kept.

Threshold: character down = 1.0-2.0s (refined measurement), short FL
boundary = 4.5s+.  3.5s sits in the gap with 1.5s margin on each side.
"""


_AUDIO_PROMOTE_WINDOW_POST = 60.0
"""Seconds AFTER a blackout to search for a Fanfare peak when promoting
``"in_match"`` to ``"match_boundary"`` (#288).

Fanfare plays during the match-start cinematic, landing 0-60s past the
end of a boundary blackout on the recordings validated in #271.  A
post-blackout-only window (rather than +-60s symmetric) avoids promoting
in-match character-down blackouts that happen to precede a legitimate
Fanfare from the next match.  The pre-side of a real boundary blackout
has no Fanfare by construction -- Fanfare never plays during an ongoing
match.
"""


def _has_nearby_fanfare_hit(
    region: tuple[float, float],
    audio_hits: Sequence[BgmHit],
    window: float = _AUDIO_PROMOTE_WINDOW_POST,
) -> BgmHit | None:
    """Return the first Fanfare hit within *window* seconds AFTER *region* end.

    A hit qualifies when ``region_end <= hit.timestamp <= region_end + window``.
    Returns ``None`` when no hit qualifies.
    """
    lo = region[1]
    hi = region[1] + window
    for hit in audio_hits:
        if lo <= hit["timestamp"] <= hi:
            return hit
    return None


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

    For short blackouts (< ``_IN_MATCH_MAX_DURATION``) classified as
    ``"in_match"``, applies static screen detection: if the post or pre
    frames are pixel-identical (loading/result screen), the scorebar
    detection is overridden to ``False``, changing the classification to
    ``"match_boundary"``.  This prevents loading screens that pass the
    A1+A2 checks from being misclassified as in-match.  (#201)

    Re-probe fallback (#524): when both pre and post probes return
    ``False`` or ``None`` (i.e. the region would classify as ``non_fl``
    or ``unknown``), re-probes pre/post symmetrically at
    ``region_width + 1/2/3s`` further out.  4K Windows Game DVR has a
    ~3s fade-in/out that pushes ``+1/2/3s`` probes inside the blackout,
    causing scorebar detection to fail.  Offsetting by ``region_width``
    pushes the probes safely past the fade.  Re-probe results override
    the original only when not ``None``; sides that already returned
    ``True`` are not re-probed.

    Returns one of:
    - ``"in_match"``: both sides have scorebar -> in-match blackout (#107)
    - ``"match_boundary"``: one side has scorebar -> match start/end
    - ``"non_fl"``: neither side has scorebar -> non-FL blackout (#109)
    - ``"unknown"``: all probes failed on either side -> keep boundary (safe)
    """
    pre_timestamps = sorted(set(max(0.0, region[0] - d) for d in (3.0, 2.0, 1.0)))
    post_timestamps = sorted(set(min(duration, region[1] + d) for d in (1.0, 2.0, 3.0)))

    pre_results, pre_frames = _probe_scorebar_context(
        video_path, pre_timestamps, height, workers
    )
    post_results, post_frames = _probe_scorebar_context(
        video_path, post_timestamps, height, workers
    )

    pre_has = _majority_scorebar(pre_results)
    post_has = _majority_scorebar(post_results)

    # Re-probe fallback when neither side detected scorebar (#524).
    # Long fade-in/out on 4K Game DVR pushes the +1/2/3s probes inside
    # the blackout; offsetting by region_width clears the fade band.
    if pre_has is not True and post_has is not True:
        region_width = region[1] - region[0]
        existing_pre_ts = set(pre_timestamps)
        existing_post_ts = set(post_timestamps)
        pre_re_timestamps = [
            t
            for t in sorted(
                set(max(0.0, region[0] - (region_width + d)) for d in (3.0, 2.0, 1.0))
            )
            if t not in existing_pre_ts
        ]
        post_re_timestamps = [
            t
            for t in sorted(
                set(
                    min(duration, region[1] + (region_width + d))
                    for d in (1.0, 2.0, 3.0)
                )
            )
            if t not in existing_post_ts
        ]

        pre_re_results: list[bool | None] = []
        post_re_results: list[bool | None] = []
        if pre_re_timestamps:
            pre_re_results, _ = _probe_scorebar_context(
                video_path, pre_re_timestamps, height, workers
            )
        if post_re_timestamps:
            post_re_results, _ = _probe_scorebar_context(
                video_path, post_re_timestamps, height, workers
            )
        pre_has_re = _majority_scorebar(pre_re_results)
        post_has_re = _majority_scorebar(post_re_results)

        if pre_has_re is not None:
            pre_has = pre_has_re
        if post_has_re is not None:
            post_has = post_has_re

        logger.debug(
            "classify re-probe region [%.1f-%.1f] (%.1fs): "
            "pre_re_ts=%s pre_re=%s votes=%s "
            "post_re_ts=%s post_re=%s votes=%s -> pre=%s post=%s",
            region[0],
            region[1],
            region_width,
            pre_re_timestamps,
            pre_has_re,
            pre_re_results,
            post_re_timestamps,
            post_has_re,
            post_re_results,
            pre_has,
            post_has,
        )

    # Override scorebar detection on static screens (loading/result).
    # Loading screens can pass _has_scorebar A1+A2 checks due to complex
    # color patterns.  Static frame-diff catches them.  (#201)
    # Only apply to short blackouts (< _IN_MATCH_MAX_DURATION) that would
    # be removed as in_match.  Long blackouts are kept regardless, and
    # overriding them creates unwanted merge candidates that cause
    # baseline match loss on contiguous-match recordings.
    region_duration = region[1] - region[0]
    if pre_has and post_has and region_duration < _IN_MATCH_MAX_DURATION:
        if _is_static_from_frames(post_frames, height):
            logger.debug(
                "static_screen override: post side [%.1f-%.1f]",
                region[0],
                region[1],
            )
            post_has = False
        if pre_has and post_has:
            if _is_static_from_frames(pre_frames, height):
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
        "pre=%s (votes=%s) post=%s (votes=%s) -> %s",
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


_MERGE_GAP_MAX: float | None = None
"""Maximum gap (seconds) between consecutive match_boundary regions to merge.

``None`` means no limit -- any gap is eligible for merge as long as all
9 probe points show no scorebar.  This is safe because V2 scorebar
detection (GC-emblem 3-point AND at 1080p) reliably detects in-match
frames: an FL match is 15-20 minutes, so at least 2-3 of 9 evenly
spaced probes would detect scorebar within a match, preventing false
merges.  Lobby/queue waits can exceed 1 hour during off-peak, so a
fixed upper bound would miss legitimate merge opportunities.
"""


def filter_blackouts_with_scorebar(
    video_path: Path,
    blackout_regions: list[tuple[float, float]],
    duration: float,
    height: int,
    workers: int | None = None,
    *,
    audio_hits: Sequence[BgmHit] | None = None,
    stats: DetectionStats | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[tuple[float, float]], list[str]]:
    """Filter blackout regions using scorebar context and duration.

    Removes:
    - Short ``"in_match"`` blackouts (< 3.5s, e.g. character down, #107)
    - ``"non_fl"`` blackouts (non-FL content boundaries, #109)

    Keeps:
    - Long ``"in_match"`` blackouts (>= 3.5s, FL match boundaries)
    - ``"match_boundary"`` (FL match start/end)
    - ``"unknown"`` (probe failure -> safe side, keep boundary)

    Audio promotion (#288):
    When *audio_hits* is provided, a blackout initially classified as
    ``"in_match"`` is promoted to ``"match_boundary"`` if any Fanfare
    peak falls within +-60s of the region.  This rescues boundaries that
    scorebar afterimage (visible ~30s past match end) causes to be
    misclassified.

    Post-processing:
    - Merges consecutive ``"match_boundary"`` pairs separated by non-FL
      content (result screen / lobby) into a single boundary region.

    Returns:
        Tuple of (filtered_regions, filtered_classifications).
    """
    kept: list[tuple[float, float]] = []
    classifications: list[str] = []
    raw_counts: dict[str, int] = {
        "match_boundary": 0,
        "in_match": 0,
        "non_fl": 0,
        "unknown": 0,
    }
    audio_promotions = 0
    total_regions = len(blackout_regions)
    for idx, region in enumerate(blackout_regions):
        classification = classify_blackout(
            video_path, region, duration, height, workers
        )
        if progress_callback is not None:
            progress_callback(idx + 1, total_regions)
        region_duration = region[1] - region[0]
        raw_counts[classification if classification in raw_counts else "unknown"] += 1

        if classification == "in_match" and audio_hits is not None:
            hit = _has_nearby_fanfare_hit(region, audio_hits)
            if hit is not None:
                logger.info(
                    "PROMOTE [%.1f-%.1f] (%.1fs): in_match -> match_boundary "
                    "(fanfare t=%.1f sim=%.3f)",
                    region[0],
                    region[1],
                    region_duration,
                    hit["timestamp"],
                    hit["similarity"],
                )
                classification = "match_boundary"
                audio_promotions += 1

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

    if stats is not None:
        stats["scorebar_match_boundary"] = raw_counts["match_boundary"]
        stats["scorebar_in_match"] = raw_counts["in_match"]
        stats["scorebar_non_fl"] = raw_counts["non_fl"]
        stats["scorebar_unknown"] = raw_counts["unknown"]
        stats["audio_promotions"] = audio_promotions

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
      FL Match -> blackout1 (match_boundary) -> lobby/result -> blackout2 (match_boundary) -> FL Match
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
            if _MERGE_GAP_MAX is None or gap <= _MERGE_GAP_MAX:
                # Probe 9 points evenly across the gap to reliably
                # detect FL match content (scorebar intermittently visible)
                gap_start = regions[i][1]
                gap_end = regions[i + 1][0]
                probe_points = [
                    gap_start + (gap_end - gap_start) * k / 10 for k in range(1, 10)
                ]
                probe_results, _ = _probe_scorebar_context(
                    video_path,
                    probe_points,
                    height,
                    workers,
                )
                all_valid = all(r is not None for r in probe_results)
                any_scorebar = any(r is True for r in probe_results)
                if all_valid and not any_scorebar:
                    merged_region = (regions[i][0], regions[i + 1][1])
                    logger.info(
                        "MERGE  [%.1f-%.1f] + [%.1f-%.1f] -> [%.1f-%.1f] "
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
