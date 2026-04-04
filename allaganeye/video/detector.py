"""Match boundary detection using OpenCV frame analysis."""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from allaganeye.exceptions import VideoProcessingError


@dataclass
class BrightnessStats:
    """Frame brightness statistics collected during detection."""

    samples: list[tuple[float, float]] = field(default_factory=list)
    """List of (timestamp, brightness) tuples."""

    @property
    def min_brightness(self) -> float:
        if not self.samples:
            return 0.0
        return min(b for _, b in self.samples)

    @property
    def max_brightness(self) -> float:
        if not self.samples:
            return 0.0
        return max(b for _, b in self.samples)

    @property
    def mean_brightness(self) -> float:
        if not self.samples:
            return 0.0
        return sum(b for _, b in self.samples) / len(self.samples)

    def near_threshold(
        self, threshold: float, margin: float = 10.0
    ) -> list[tuple[float, float]]:
        """Return samples within margin of the threshold."""
        return [(t, b) for t, b in self.samples if abs(b - threshold) <= margin]


def detect_match_boundaries(
    video_path: Path,
    *,
    sample_interval: float = 1.0,
    blackout_threshold: float = 15.0,
    min_match_duration: float = 300.0,
    collect_brightness: bool = False,
) -> list[dict] | tuple[list[dict], BrightnessStats]:
    """Detect match boundaries by finding blackout frames.

    Samples frames at the given interval, detects blackout (low brightness)
    frames, and returns non-blackout segments that are longer than
    min_match_duration.

    If collect_brightness is True, returns a tuple of (segments, stats).
    Otherwise returns just the segments list.
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
        brightness_stats = BrightnessStats() if collect_brightness else None
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

            if brightness_stats is not None:
                brightness_stats.samples.append((timestamp, mean_brightness))

            if mean_brightness < blackout_threshold:
                blackout_times.append(timestamp)

            frame_idx += frame_step

    finally:
        cap.release()

    # Build segments from non-blackout regions
    segments = _extract_segments(
        blackout_times, duration, sample_interval, min_match_duration
    )

    if collect_brightness:
        assert brightness_stats is not None
        return segments, brightness_stats
    return segments


def _extract_segments(
    blackout_times: list[float],
    total_duration: float,
    sample_interval: float,
    min_match_duration: float,
) -> list[dict]:
    """Extract match segments from blackout timestamps.

    Groups consecutive blackout frames into blackout regions,
    then extracts gaps between them as match candidates.
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
        seg_end = blackout_regions[0][0]
        if seg_end - seg_start >= min_match_duration:
            segments.append({"start": seg_start, "end": seg_end})

    # Between blackout regions
    for i in range(len(blackout_regions) - 1):
        seg_start = blackout_regions[i][1]
        seg_end = blackout_regions[i + 1][0]
        if seg_end - seg_start >= min_match_duration:
            segments.append({"start": seg_start, "end": seg_end})

    # After last blackout
    last_end = blackout_regions[-1][1]
    if total_duration - last_end >= min_match_duration:
        segments.append({"start": last_end, "end": total_duration})

    return segments
