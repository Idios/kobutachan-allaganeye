"""Match boundary detection using ffmpeg frame sampling."""

import subprocess
from collections.abc import Callable
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
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> list[dict]:
    """Detect match boundaries by finding blackout frames.

    Uses ffmpeg to sample frames at the given interval, converting to
    low-resolution grayscale for fast brightness analysis.  This avoids
    the OpenCV VideoCapture bottleneck of sequentially walking every
    frame in large MKV files.

    Args:
        duration_hint: Video duration in seconds from ffprobe.  Used to
            estimate total sample count for progress reporting.
        progress_callback: Optional callback invoked at each sampled frame
            with ``(sample_index, total_samples, blackout_count)``.  Allows
            the caller to display progress without coupling detector to UI.

    Returns list of dicts with 'start' and 'end' keys (seconds).
    """
    blackout_times = _sample_brightness_ffmpeg(
        video_path,
        sample_interval=sample_interval,
        blackout_threshold=blackout_threshold,
        duration_hint=duration_hint,
        progress_callback=progress_callback,
    )

    duration = duration_hint if duration_hint is not None and duration_hint > 0 else 0.0
    if duration <= 0:
        # Estimate duration from last sample timestamp
        if blackout_times:
            duration = blackout_times[-1] + sample_interval
        else:
            # No blackouts and no duration hint — cannot determine duration
            raise VideoProcessingError(
                "Cannot determine video duration. Provide duration_hint via probe."
            )

    return _extract_segments(
        blackout_times, duration, sample_interval, min_match_duration
    )


def _sample_brightness_ffmpeg(
    video_path: Path,
    *,
    sample_interval: float,
    blackout_threshold: float,
    duration_hint: float | None,
    progress_callback: Callable[[int, int, int], None] | None,
) -> list[float]:
    """Sample frame brightness using ffmpeg pipe.

    Runs ffmpeg with a ``select`` filter to extract one frame per
    *sample_interval* seconds, scaled to 320x180 grayscale.  Raw pixel
    data is piped to Python for brightness analysis.
    """
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-vf",
        f"select='not(mod(t\\,{sample_interval}))',setpts=N/FRAME_RATE/TB",
        "-vsync",
        "vfr",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-s",
        f"{_SAMPLE_WIDTH}x{_SAMPLE_HEIGHT}",
        "pipe:1",
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e

    total_samples = 0
    if duration_hint is not None and duration_hint > 0:
        total_samples = int(duration_hint / sample_interval)

    blackout_times: list[float] = []
    sample_idx = 0

    try:
        while True:
            raw = proc.stdout.read(_FRAME_SIZE)
            if len(raw) < _FRAME_SIZE:
                break
            brightness = float(np.frombuffer(raw, dtype=np.uint8).mean())
            timestamp = sample_idx * sample_interval
            if brightness < blackout_threshold:
                blackout_times.append(timestamp)

            if progress_callback is not None:
                progress_callback(sample_idx, total_samples, len(blackout_times))

            sample_idx += 1
    finally:
        proc.stdout.close()
        proc.wait()

    if proc.returncode != 0 and sample_idx == 0:
        stderr = proc.stderr.read().decode(errors="replace")[-500:]
        proc.stderr.close()
        raise VideoProcessingError(f"ffmpeg frame sampling failed: {stderr}")
    if proc.stderr:
        proc.stderr.close()

    return blackout_times


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
