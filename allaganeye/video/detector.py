"""Match boundary detection using OpenCV frame analysis."""

from pathlib import Path

import cv2
import numpy as np

from allaganeye.exceptions import VideoProcessingError


def detect_match_boundaries(
    video_path: Path,
    *,
    sample_interval: float = 1.0,
    blackout_threshold: float = 15.0,
    min_match_duration: float = 300.0,
) -> list[dict]:
    """Detect match boundaries by finding blackout frames.

    Samples frames at the given interval, detects blackout (low brightness)
    frames, and returns non-blackout segments that are longer than
    min_match_duration.

    Returns list of dicts with 'start' and 'end' keys (seconds).
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise VideoProcessingError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0 or total_frames <= 0:
            raise VideoProcessingError(
                "Cannot read video properties (fps or frame count)"
            )

        duration = total_frames / fps
        frame_step = int(fps * sample_interval)
        if frame_step < 1:
            frame_step = 1

        # Collect brightness values at sampled positions
        blackout_times: list[float] = []
        frame_idx = 0
        consecutive_failures = 0
        max_consecutive_failures = 3

        while frame_idx < total_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    raise VideoProcessingError(
                        f"Failed to read {max_consecutive_failures} consecutive "
                        f"frames at position {frame_idx}/{total_frames}"
                    )
                frame_idx += frame_step
                continue

            consecutive_failures = 0
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = float(np.mean(gray))
            timestamp = frame_idx / fps

            if mean_brightness < blackout_threshold:
                blackout_times.append(timestamp)

            frame_idx += frame_step

    finally:
        cap.release()

    # Build segments from non-blackout regions
    return _extract_segments(
        blackout_times, duration, sample_interval, min_match_duration
    )


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
) -> list[dict]:
    """Extract match segments from blackout timestamps.

    Groups consecutive blackout frames into blackout regions,
    then extracts gaps between them as match candidates.

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
