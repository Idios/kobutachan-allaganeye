"""Match boundary detection using parallel ffmpeg frame probing."""

import os
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError

_SAMPLE_WIDTH = 320
_SAMPLE_HEIGHT = 180
_FRAME_SIZE = _SAMPLE_WIDTH * _SAMPLE_HEIGHT  # grayscale, 1 byte per pixel


def detect_match_boundaries(
    video_path: Path,
    *,
    duration_hint: float | None = None,
    sample_interval: float = 1.0,
    blackout_threshold: float = 15.0,
    min_match_duration: float = 300.0,
    min_blackout_duration: float = 3.0,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> list[dict]:
    """Detect match boundaries by finding blackout frames.

    Uses parallel ffmpeg ``-ss`` probes to extract one frame per
    *sample_interval* seconds.  Each probe seeks to the target timestamp
    (keyframe-based input seeking) and decodes only one frame, avoiding
    the cost of decoding the entire stream.

    Args:
        duration_hint: Video duration in seconds from ffprobe.  Required
            to generate the list of sample timestamps.
        progress_callback: Optional callback invoked after each sampled
            frame with ``(completed_count, total_samples, blackout_count)``.

    Returns list of dicts with 'start' and 'end' keys (seconds).
    """
    if duration_hint is None or duration_hint <= 0:
        raise VideoProcessingError(
            "Cannot determine video duration. Provide duration_hint via probe."
        )

    timestamps = _generate_timestamps(duration_hint, sample_interval)
    if not timestamps:
        return []

    total_samples = len(timestamps)
    max_workers = min(os.cpu_count() or 4, 24)

    # Parallel -ss probes
    results: dict[float, float] = {}  # timestamp → brightness
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

    # Collect blackout timestamps in chronological order
    blackout_times = sorted(t for t, b in results.items() if b < blackout_threshold)

    return _extract_segments(
        blackout_times,
        duration_hint,
        sample_interval,
        min_match_duration,
        min_blackout_duration,
    )


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
        "ffmpeg",
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

    if len(result.stdout) < _FRAME_SIZE:
        return 255.0  # incomplete frame, treat as non-blackout

    return float(np.frombuffer(result.stdout[:_FRAME_SIZE], dtype=np.uint8).mean())


_BLACKOUT_PADDING = 3.0
"""Seconds to offset cut points into blackout regions.

With ``-c copy``, FFmpeg can only cut at keyframes (~2s apart for OBS).
By placing cut points inside blackout regions, keyframe drift never
clips actual match footage.
"""


def _extract_segments(
    blackout_times: list[float],
    total_duration: float,
    sample_interval: float,
    min_match_duration: float,
    min_blackout_duration: float = 3.0,
) -> list[dict]:
    """Extract match segments from blackout timestamps.

    Groups consecutive blackout frames into blackout regions,
    filters out regions shorter than *min_blackout_duration* (e.g.
    respawn blackouts), then extracts gaps between them as match
    candidates.

    Cut points are offset into the blackout regions by
    ``_BLACKOUT_PADDING`` so that keyframe-level imprecision in
    ``-c copy`` mode never clips match footage.
    """
    if not blackout_times:
        # No blackouts found — entire video is one segment
        if total_duration >= min_match_duration:
            return [{"start": 0.0, "end": total_duration}]
        return []

    # Group consecutive blackout times into regions
    tolerance = sample_interval * 2
    blackout_regions: list[tuple[float, float]] = []
    region_start = blackout_times[0]
    region_end = blackout_times[0]

    for t in blackout_times[1:]:
        if t - region_end <= tolerance:
            region_end = t
        else:
            blackout_regions.append((region_start, region_end))
            region_start = t
            region_end = t
    blackout_regions.append((region_start, region_end))

    # Filter out short blackout regions (e.g. respawn blackouts 1-2s)
    blackout_regions = [
        (s, e) for s, e in blackout_regions if e - s >= min_blackout_duration
    ]

    if not blackout_regions:
        # All blackouts were too short — treat as no blackouts
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
