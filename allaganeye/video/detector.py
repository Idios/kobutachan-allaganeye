"""Match boundary detection using parallel ffmpeg frame probing."""

import logging
import os
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg

logger = logging.getLogger(__name__)

_SAMPLE_WIDTH = 320
_SAMPLE_HEIGHT = 180
_FRAME_SIZE = _SAMPLE_WIDTH * _SAMPLE_HEIGHT  # grayscale, 1 byte per pixel


def _resolve_workers(workers: int | None) -> int:
    """Resolve worker count: explicit value or auto-detect."""
    if workers is not None:
        return workers
    return min(os.cpu_count() or 4, 24)


def detect_match_boundaries(
    video_path: Path,
    *,
    duration_hint: float | None = None,
    sample_interval: float = 1.0,
    blackout_threshold: float = 15.0,
    min_match_duration: float = 300.0,
    min_blackout_duration: float = 3.0,
    use_gpu: bool = False,
    workers: int | None = None,
    src_resolution: tuple[int, int] | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> list[dict]:
    """Detect match boundaries by finding blackout frames.

    Args:
        duration_hint: Video duration in seconds from ffprobe.  Required
            to generate the list of sample timestamps.
        use_gpu: If True, use chunked parallel GPU decode instead of
            per-frame -ss probes.  Falls back to CPU on failure.
        src_resolution: (width, height) from probe.  When provided,
            scorebar-based filtering is applied to remove in-match
            blackouts and non-FL blackouts.
        progress_callback: Optional callback invoked after each sampled
            frame with ``(completed_count, total_samples, blackout_count)``.

    Returns list of dicts with 'start' and 'end' keys (seconds).
    """
    if duration_hint is None or duration_hint <= 0:
        raise VideoProcessingError(
            "Cannot determine video duration. Provide duration_hint via probe."
        )

    # Pass 1: scan for blackout frames
    if use_gpu:
        from allaganeye.video.gpu_detector import scan_gpu

        try:
            results = scan_gpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                progress_callback,
            )
        except VideoProcessingError:
            # GPU failed — fall back to CPU
            results = _scan_cpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                workers,
                progress_callback,
            )
    else:
        results = _scan_cpu(
            video_path,
            duration_hint,
            sample_interval,
            blackout_threshold,
            workers,
            progress_callback,
        )

    # Collect blackout timestamps in chronological order
    blackout_times = sorted(t for t, b in results.items() if b < blackout_threshold)

    # Group into regions and expand with transition frames (#71)
    blackout_regions = _group_blackout_regions(blackout_times, sample_interval)
    blackout_regions = _expand_regions_with_transitions(
        blackout_regions, results, sample_interval, _TRANSITION_THRESHOLD
    )

    # 2nd pass: refine blackout regions at fine interval (#77)
    refined_regions = _refine_blackout_regions(
        video_path, blackout_regions, blackout_threshold, duration_hint, workers
    )

    # Scorebar-based filtering: remove in-match and non-FL blackouts (#111)
    if src_resolution is not None:
        from allaganeye.video.scorebar import filter_blackouts_with_scorebar

        height = _scaled_height(src_resolution[0], src_resolution[1])
        refined_regions = filter_blackouts_with_scorebar(
            video_path, refined_regions, duration_hint, height, workers
        )

    effective_min = min(min_blackout_duration, _REFINED_MIN_BLACKOUT)
    return _filter_and_extract_segments(
        refined_regions,
        duration_hint,
        min_match_duration,
        effective_min,
    )


def _scan_cpu(
    video_path: Path,
    duration_hint: float,
    sample_interval: float,
    blackout_threshold: float,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> dict[float, float]:
    """CPU mode: parallel -ss probes, one ffmpeg process per frame."""
    timestamps = _generate_timestamps(duration_hint, sample_interval)
    if not timestamps:
        return {}

    total_samples = len(timestamps)
    max_workers = _resolve_workers(workers)

    results: dict[float, float] = {}
    blackout_count = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_single_frame, video_path, t): t for t in timestamps
        }
        for future in as_completed(futures):
            t = futures[future]
            brightness = future.result()
            results[t] = brightness
            completed += 1
            if brightness < blackout_threshold:
                blackout_count += 1
            if progress_callback is not None:
                progress_callback(completed, total_samples, blackout_count)

    return results


def _generate_timestamps(duration: float, interval: float) -> list[float]:
    """Generate sample timestamps from 0 to duration at given interval."""
    timestamps: list[float] = []
    t = 0.0
    while t < duration:
        timestamps.append(t)
        t += interval
    return timestamps


def _probe_single_frame(video_path: Path, timestamp: float) -> float:
    """Probe a single frame's mean brightness using ffmpeg -ss seek.

    Uses input seeking (``-ss`` before ``-i``) for fast keyframe-based
    access, then decodes exactly one frame at 320x180 grayscale.

    Returns the mean brightness (0-255).  Returns 255.0 on probe failure
    (treated as non-blackout to avoid false positives).
    """
    cmd = [
        find_ffmpeg(),
        "-threads",
        "1",
        "-ss",
        str(timestamp),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-s",
        f"{_SAMPLE_WIDTH}x{_SAMPLE_HEIGHT}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired:
        return 255.0  # treat timeout as non-blackout

    if result.returncode != 0:
        return 255.0  # ffmpeg error, treat as non-blackout

    if len(result.stdout) < _FRAME_SIZE:
        return 255.0  # incomplete frame, treat as non-blackout

    return float(np.frombuffer(result.stdout[:_FRAME_SIZE], dtype=np.uint8).mean())


def _probe_frame_rgb(
    video_path: Path, timestamp: float, height: int = _SAMPLE_HEIGHT
) -> bytes | None:
    """Probe a single frame as RGB24 raw bytes with aspect-ratio preservation.

    Uses ``-vf scale={width}:-2`` to preserve the source aspect ratio while
    scaling width to ``_SAMPLE_WIDTH``.  The caller provides the expected
    ``height`` (computed from the source aspect ratio) so the function can
    validate the output size.

    Returns None on probe failure (timeout, incomplete frame).
    """
    rgb_size = _SAMPLE_WIDTH * height * 3
    cmd = [
        find_ffmpeg(),
        "-threads",
        "1",
        "-ss",
        str(timestamp),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={_SAMPLE_WIDTH}:-2,format=rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired:
        return None

    if result.returncode != 0:
        return None

    if len(result.stdout) < rgb_size:
        return None

    return result.stdout[:rgb_size]


def _scaled_height(src_width: int, src_height: int) -> int:
    """Compute scaled height preserving aspect ratio, rounded to even."""
    h = round(_SAMPLE_WIDTH * src_height / src_width)
    h += h % 2  # round up to even (ffmpeg -2 requirement)
    return h


# Scorebar ROI as ratios of scaled frame dimensions.
# Narrowed to center-top to exclude party list (left) and minimap (right).
_SCOREBAR_ROI_X_START = 0.35
_SCOREBAR_ROI_X_END = 0.65
_SCOREBAR_ROI_Y_START = 0.0
_SCOREBAR_ROI_Y_END = 0.04


_SCOREBAR_CHANNEL_STD_THRESHOLD = 15.0
"""Minimum cross-section channel std for scorebar detection.

FL scorebar has 3GC color bands (red/blue/yellow).  When the ROI is split
into left/center/right thirds, at least one RGB channel shows significant
std across the three sections (26-48 for FL, ~5 for lobby, ~8-9 for queue).
Threshold 15.0 sits in the gap between queue max (~8.8) and FL min (~26).
"""


def _has_scorebar(raw_rgb: bytes | None, height: int) -> bool | None:
    """Determine if FL scorebar is present in the frame.

    Returns True if scorebar detected, False if not, or None if probe
    failed (raw_rgb is None).

    Criteria (lead-1 revised spec based on 3-section analysis, #121):
    - 20 < roi_brightness < 140 (FL match typical range)
    - max cross-section channel std > 15.0 (3GC color separation)
    """
    if raw_rgb is None:
        return None

    frame = np.frombuffer(raw_rgb, dtype=np.uint8).reshape(height, _SAMPLE_WIDTH, 3)
    x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
    x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
    y1 = int(height * _SCOREBAR_ROI_Y_START)
    y2 = int(height * _SCOREBAR_ROI_Y_END)
    roi = frame[y1:y2, x1:x2, :]

    roi_brightness = float(roi.mean())
    if not (20.0 < roi_brightness < 140.0):
        logger.debug(
            "scorebar: brightness=%.1f (out of 20-140 range) → False",
            roi_brightness,
        )
        return False

    # Split ROI into 3 sections and compute cross-section channel std
    w = roi.shape[1]
    sec_w = w // 3
    left = roi[:, :sec_w, :]
    center = roi[:, sec_w : 2 * sec_w, :]
    right = roi[:, 2 * sec_w :, :]

    section_means = []
    for section in (left, center, right):
        section_means.append(
            [
                float(section[:, :, 0].mean()),
                float(section[:, :, 1].mean()),
                float(section[:, :, 2].mean()),
            ]
        )

    channel_stds = [
        float(np.std([s[0] for s in section_means])),
        float(np.std([s[1] for s in section_means])),
        float(np.std([s[2] for s in section_means])),
    ]
    max_channel_std = max(channel_stds)
    detected = max_channel_std > _SCOREBAR_CHANNEL_STD_THRESHOLD

    logger.debug(
        "scorebar: brightness=%.1f  ch_std=[R=%.1f G=%.1f B=%.1f] max=%.1f thr=%.1f → %s",
        roi_brightness,
        channel_stds[0],
        channel_stds[1],
        channel_stds[2],
        max_channel_std,
        _SCOREBAR_CHANNEL_STD_THRESHOLD,
        detected,
    )

    return detected


_TRANSITION_THRESHOLD = 55.0
"""Brightness threshold for transition regions adjacent to blackouts.

Game frames are typically 60-120, while lobby/waiting screens are ~51.
Frames below this threshold that are adjacent to a blackout region are
included in the expanded region, allowing short blackouts followed by
lobby screens to be detected as match boundaries.
"""

_REFINE_INTERVAL = 0.25
"""Fine interval for 2nd-pass re-probing of blackout candidates."""

_REFINE_WINDOW = 5.0
"""Seconds to probe before and after each blackout region in pass 2."""

_REFINED_MIN_BLACKOUT = 1.5
"""Min blackout duration when using refined (0.25s) measurements.

At interval=0.25s, a 2.0s blackout measures ~1.5-1.75s (≥ 1.5 → detected)
while a 1.5s respawn measures ~1.0-1.25s (< 1.5 → filtered).
"""

_BLACKOUT_PADDING = 3.0
"""Seconds to offset cut points into blackout regions.

With ``-c copy``, FFmpeg can only cut at keyframes (~2s apart for OBS).
By placing cut points inside blackout regions, keyframe drift never
clips actual match footage.
"""


def _group_blackout_regions(
    blackout_times: list[float],
    sample_interval: float,
) -> list[tuple[float, float]]:
    """Group consecutive blackout timestamps into contiguous regions.

    Timestamps within ``sample_interval * 2`` of each other are merged
    into a single (start, end) region.
    """
    if not blackout_times:
        return []

    tolerance = sample_interval * 2
    regions: list[tuple[float, float]] = []
    region_start = blackout_times[0]
    region_end = blackout_times[0]
    for t in blackout_times[1:]:
        if t - region_end <= tolerance:
            region_end = t
        else:
            regions.append((region_start, region_end))
            region_start = t
            region_end = t
    regions.append((region_start, region_end))
    return regions


def _expand_regions_with_transitions(
    blackout_regions: list[tuple[float, float]],
    all_results: dict[float, float],
    sample_interval: float,
    transition_threshold: float,
) -> list[tuple[float, float]]:
    """Expand blackout regions to include adjacent transition frames.

    For each region, expands forward and backward through timestamps
    where brightness is below *transition_threshold*.  This captures
    lobby/waiting screens (~51 brightness) that follow match-boundary
    blackouts, making them long enough to pass the min_blackout_duration
    filter while leaving short respawn blackouts (followed by immediate
    60+ game frames) unchanged.
    """
    if not blackout_regions:
        return blackout_regions

    sorted_timestamps = sorted(all_results)

    expanded: list[tuple[float, float]] = []
    for reg_start, reg_end in blackout_regions:
        new_start = reg_start
        new_end = reg_end
        # Expand backward
        for t in reversed(sorted_timestamps):
            if t >= reg_start:
                continue
            if all_results[t] < transition_threshold:
                new_start = t
            else:
                break
        # Expand forward
        for t in sorted_timestamps:
            if t <= reg_end:
                continue
            if all_results[t] < transition_threshold:
                new_end = t
            else:
                break
        expanded.append((new_start, new_end))

    # Merge overlapping regions after expansion
    expanded.sort()
    merged: list[tuple[float, float]] = [expanded[0]]
    tolerance = sample_interval * 2
    for start, end in expanded[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= tolerance:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def _refine_blackout_regions(
    video_path: Path,
    blackout_regions: list[tuple[float, float]],
    blackout_threshold: float,
    total_duration: float,
    workers: int | None = None,
) -> list[tuple[float, float]]:
    """Re-probe blackout regions at fine interval for precise duration.

    For each region, probes ±_REFINE_WINDOW seconds at _REFINE_INTERVAL
    to get an accurate measurement of the blackout duration.  Returns
    updated regions with refined start/end times.
    """
    if not blackout_regions:
        return blackout_regions

    max_workers = _resolve_workers(workers)

    # Collect all timestamps to probe (deduplicated)
    probe_timestamps: set[float] = set()
    for reg_start, reg_end in blackout_regions:
        window_start = max(0.0, reg_start - _REFINE_WINDOW)
        window_end = min(total_duration, reg_end + _REFINE_WINDOW)
        t = window_start
        while t < window_end:
            probe_timestamps.add(round(t, 4))
            t += _REFINE_INTERVAL

    # Parallel probes
    results: dict[float, float] = {}
    sorted_probes = sorted(probe_timestamps)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_single_frame, video_path, t): t for t in sorted_probes
        }
        for future in as_completed(futures):
            t = futures[future]
            results[t] = future.result()

    # Re-extract blackout regions from fine-grained data
    fine_blackout_times = sorted(
        t for t, b in results.items() if b < blackout_threshold
    )
    return _group_blackout_regions(fine_blackout_times, _REFINE_INTERVAL)


def _filter_and_extract_segments(
    blackout_regions: list[tuple[float, float]],
    total_duration: float,
    min_match_duration: float,
    min_blackout_duration: float = 3.0,
) -> list[dict]:
    """Filter blackout regions by duration and extract match segments.

    Removes regions shorter than *min_blackout_duration*, then extracts
    gaps between remaining regions as match candidates.  Cut points are
    offset into the blackout regions by ``_BLACKOUT_PADDING`` so that
    keyframe-level imprecision in ``-c copy`` mode never clips match
    footage.
    """
    if not blackout_regions:
        if total_duration >= min_match_duration:
            return [{"start": 0.0, "end": total_duration}]
        return []

    # Filter out short blackout regions (e.g. respawn blackouts 1-2s)
    blackout_regions = [
        (s, e) for s, e in blackout_regions if e - s >= min_blackout_duration
    ]

    if not blackout_regions:
        if total_duration >= min_match_duration:
            return [{"start": 0.0, "end": total_duration}]
        return []

    # Extract segments between blackout regions
    segments: list[dict] = []

    # Before first blackout
    if blackout_regions[0][0] > 0:
        seg_start = 0.0
        seg_end = _padded_end(blackout_regions[0])
        seg_end = min(seg_end, total_duration)
        if seg_end - seg_start >= min_match_duration:
            segments.append({"start": seg_start, "end": seg_end})

    # Between blackout regions
    for i in range(len(blackout_regions) - 1):
        seg_start = _padded_start(blackout_regions[i])
        seg_start = max(seg_start, 0.0)
        seg_end = _padded_end(blackout_regions[i + 1])
        seg_end = min(seg_end, total_duration)
        if seg_end - seg_start >= min_match_duration:
            segments.append({"start": seg_start, "end": seg_end})

    # After last blackout
    seg_start = _padded_start(blackout_regions[-1])
    seg_start = max(seg_start, 0.0)
    if total_duration - seg_start >= min_match_duration:
        segments.append({"start": seg_start, "end": total_duration})

    return segments


def _padded_end(region: tuple[float, float]) -> float:
    """Offset the segment end into the blackout region start."""
    region_start, region_end = region
    region_duration = region_end - region_start
    effective_padding = min(_BLACKOUT_PADDING, region_duration / 2)
    return region_start + effective_padding


def _padded_start(region: tuple[float, float]) -> float:
    """Offset the segment start into the blackout region end."""
    region_start, region_end = region
    region_duration = region_end - region_start
    effective_padding = min(_BLACKOUT_PADDING, region_duration / 2)
    return region_end - effective_padding
