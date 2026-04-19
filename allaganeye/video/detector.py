"""Match boundary detection using parallel ffmpeg frame probing."""

import logging
import os
import subprocess
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TypedDict

import numpy as np

from allaganeye.audio.matcher import BgmHit
from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg


class MatchBoundary(TypedDict):
    """A detected match segment with start/end times and type."""

    start: float
    end: float
    type: str


class DetectionStats(TypedDict, total=False):
    """Pipeline statistics populated by :func:`detect_match_boundaries`.

    All keys are optional; callers pass an empty dict which the detector
    populates as each phase completes.  Used for ``--verbose`` output
    (issue #336 Phase 1).
    """

    mode: str  # "CPU" or "GPU"
    pass1_samples: int
    pass1_blackout_frames: int
    pass1_elapsed_s: float
    pass2_regions: int
    pass2_elapsed_s: float
    scorebar_match_boundary: int
    scorebar_in_match: int
    scorebar_non_fl: int
    scorebar_unknown: int
    audio_promotions: int


logger = logging.getLogger(__name__)

_SAMPLE_WIDTH = 320
_SAMPLE_HEIGHT = 180
_FRAME_SIZE = _SAMPLE_WIDTH * _SAMPLE_HEIGHT  # grayscale, 1 byte per pixel


def _resolve_workers(workers: int | None) -> int:
    """Resolve worker count: explicit value or auto-detect."""
    if workers is not None:
        return workers
    return min(os.cpu_count() or 4, 32)


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
    codec: str | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    refine_progress_callback: Callable[[int, int], None] | None = None,
    audio_hits: Sequence[BgmHit] | None = None,
    stats: DetectionStats | None = None,
    chunk_progress_callback: Callable[[int, int, float], None] | None = None,
) -> list[MatchBoundary]:
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
        refine_progress_callback: Optional callback invoked during
            Pass 2 refinement and scorebar filtering with
            ``(completed_steps, total_steps)``.
        audio_hits: Optional Fanfare peaks from audio scan (#288).  When
            provided and scorebar filtering is active, blackouts
            classified as ``"in_match"`` but near a Fanfare hit are
            promoted to ``"match_boundary"``.

    Returns list of dicts with 'start' and 'end' keys (seconds).
    """
    if duration_hint is None or duration_hint <= 0:
        raise VideoProcessingError(
            "Cannot determine video duration. Provide duration_hint via probe."
        )

    # Pass 1: scan for blackout frames
    pass1_start = time.monotonic()
    resolved_mode = "CPU"
    if use_gpu:
        from allaganeye.video.gpu_detector import scan_gpu

        try:
            results = scan_gpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                progress_callback,
                codec=codec,
                chunk_progress_callback=chunk_progress_callback,
            )
            resolved_mode = "GPU"
        except VideoProcessingError:
            # GPU failed -- fall back to CPU
            results = _scan_cpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                workers,
                progress_callback,
            )
            resolved_mode = "CPU (GPU fallback)"
    else:
        results = _scan_cpu(
            video_path,
            duration_hint,
            sample_interval,
            blackout_threshold,
            workers,
            progress_callback,
        )
    pass1_elapsed = time.monotonic() - pass1_start

    if stats is not None:
        stats["mode"] = resolved_mode
        stats["pass1_samples"] = len(results)
        stats["pass1_blackout_frames"] = sum(
            1 for b in results.values() if b < blackout_threshold
        )
        stats["pass1_elapsed_s"] = pass1_elapsed

    # A4 (#361): Pass 1 blackout judgment uses upper hysteresis margin so
    # borderline frames (e.g. brightness 15.13 when threshold is 15.0) are
    # treated as blackout.  Pass 2 precise measurement later rejects false
    # positives introduced by the wider net.
    pass1_blackout_threshold = blackout_threshold + _BLACKOUT_THRESHOLD_UPPER_MARGIN
    blackout_times = sorted(
        t for t, b in results.items() if b < pass1_blackout_threshold
    )

    # Group into regions and expand with transition frames (#71)
    blackout_regions = _group_blackout_regions(blackout_times, sample_interval)
    blackout_regions = _expand_regions_with_transitions(
        blackout_regions, results, sample_interval, _TRANSITION_THRESHOLD
    )

    # A3 (#361): add +-_BORDERLINE_REFINE_RADIUS pseudo-regions around Pass 1
    # borderline frames so Pass 2's 0.25s probing covers short blackouts
    # (<=2.5s) that Pass 1 missed due to sample_interval alignment.
    if _ENABLE_BORDERLINE_REFINEMENT:
        borderline_regions = _borderline_pseudo_regions(
            results, blackout_threshold, duration_hint
        )
        if borderline_regions:
            blackout_regions = _merge_regions(
                blackout_regions + borderline_regions, sample_interval
            )

    # Progress tracking for Pass 2 + scorebar filtering.
    # Pass 2 publishes the actual probe count via its progress_callback;
    # scorebar bumps the total later when refined_regions is known.
    refine_total = 0
    refine_completed = 0

    def _refine_step() -> None:
        nonlocal refine_completed
        refine_completed += 1
        if refine_progress_callback is not None:
            refine_progress_callback(refine_completed, refine_total)

    def _on_refine_probe(completed: int, total: int) -> None:
        nonlocal refine_completed, refine_total
        refine_total = total
        refine_completed = completed
        if refine_progress_callback is not None:
            refine_progress_callback(refine_completed, refine_total)

    # 2nd pass: refine blackout regions at fine interval (#77).
    # progress_callback fires per probe so the Refining bar advances during
    # the long ThreadPoolExecutor wait (#366).
    pass2_start = time.monotonic()
    refined_regions = _refine_blackout_regions(
        video_path,
        blackout_regions,
        blackout_threshold,
        duration_hint,
        workers,
        progress_callback=_on_refine_probe,
    )
    pass2_elapsed = time.monotonic() - pass2_start
    if stats is not None:
        stats["pass2_regions"] = len(refined_regions)
        stats["pass2_elapsed_s"] = pass2_elapsed

    # Scorebar-based filtering: remove in-match and non-FL blackouts (#111)
    region_classifications: list[str] | None = None
    if src_resolution is not None:
        from allaganeye.video.scorebar import filter_blackouts_with_scorebar

        # Update total now that we know how many regions scorebar will process
        refine_total = refine_completed + len(refined_regions)

        height = _scaled_height(src_resolution[0], src_resolution[1])
        refined_regions, region_classifications = filter_blackouts_with_scorebar(
            video_path,
            refined_regions,
            duration_hint,
            height,
            workers,
            audio_hits=audio_hits,
            stats=stats,
            progress_callback=lambda c, t: _refine_step(),
        )

    effective_min = min(min_blackout_duration, _REFINED_MIN_BLACKOUT)
    return _filter_and_extract_segments(
        refined_regions,
        duration_hint,
        min_match_duration,
        effective_min,
        classifications=region_classifications,
    )


def _decode_chunk_cpu(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
) -> dict[float, float]:
    """Decode a chunk using CPU-only ffmpeg with continuous decode.

    Mirrors the GPU ``_decode_chunk()`` approach but without hardware
    acceleration: one long-lived ffmpeg process decodes the entire chunk
    via the ``fps`` filter, eliminating per-frame ``-ss`` non-determinism.

    Returns a dict mapping each timestamp in *chunk_timestamps* to its
    mean brightness.  On failure, returns all timestamps mapped to 255.0
    (safe non-blackout).
    """
    if not chunk_timestamps:
        return {}

    chunk_duration = chunk_end - chunk_start
    fps_value = 1.0 / sample_interval

    cmd = [
        find_ffmpeg(),
        "-threads",
        "1",
        "-ss",
        str(chunk_start),
        "-t",
        str(chunk_duration),
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps_value},scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=max(300, int(chunk_duration * 2)),
        )
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired:
        logger.warning("CPU chunk decode timed out [%.1f-%.1f]", chunk_start, chunk_end)
        return {t: 255.0 for t in chunk_timestamps}

    if proc.returncode != 0:
        logger.warning(
            "CPU chunk decode failed [%.1f-%.1f]: %s",
            chunk_start,
            chunk_end,
            proc.stderr.decode(errors="replace")[-200:],
        )
        return {t: 255.0 for t in chunk_timestamps}

    # Parse raw frames and map to pre-computed timestamps
    data = proc.stdout
    results: dict[float, float] = {}
    frame_idx = 0
    offset = 0

    while offset + _FRAME_SIZE <= len(data) and frame_idx < len(chunk_timestamps):
        frame = np.frombuffer(data[offset : offset + _FRAME_SIZE], dtype=np.uint8)
        results[chunk_timestamps[frame_idx]] = float(frame.mean())
        offset += _FRAME_SIZE
        frame_idx += 1

    # Fill missing timestamps with safe non-blackout value
    for t in chunk_timestamps:
        if t not in results:
            results[t] = 255.0

    return results


def _scan_cpu(
    video_path: Path,
    duration_hint: float,
    sample_interval: float,
    blackout_threshold: float,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> dict[float, float]:
    """CPU mode: chunked continuous decode, one ffmpeg process per chunk.

    Splits the video timeline into chunks and decodes each chunk with
    a long-lived ffmpeg process using the ``fps`` filter.  This replaces
    per-frame ``-ss`` probing, reducing ffmpeg seek non-determinism to
    one seek per chunk instead of one per frame.  (#214)
    """
    timestamps = _generate_timestamps(duration_hint, sample_interval)
    if not timestamps:
        return {}

    total_samples = len(timestamps)
    num_chunks = min(os.cpu_count() or 4, 32)
    chunk_duration = duration_hint / num_chunks

    # Distribute pre-computed timestamps to chunks (with overlap)
    chunks: list[tuple[float, float, list[float]]] = []
    for i in range(num_chunks):
        c_start = i * chunk_duration
        c_end = min((i + 1) * chunk_duration + sample_interval, duration_hint)
        c_timestamps = [t for t in timestamps if c_start <= t < c_end]
        if c_timestamps:
            chunks.append((c_start, c_end, c_timestamps))

    results: dict[float, float] = {}
    blackout_count = 0
    completed = 0

    with ThreadPoolExecutor(
        max_workers=min(num_chunks, _resolve_workers(workers))
    ) as pool:
        futures = {
            pool.submit(
                _decode_chunk_cpu,
                video_path,
                c_ts,
                c_start,
                c_end,
                sample_interval,
            ): (c_start, c_ts)
            for c_start, c_end, c_ts in chunks
        }
        for future in as_completed(futures):
            chunk_results = future.result()
            for t, brightness in chunk_results.items():
                if t not in results:  # first-writer-wins for overlap
                    results[t] = brightness
                    completed += 1
                    if brightness < blackout_threshold:
                        blackout_count += 1
                    if progress_callback is not None:
                        progress_callback(completed, total_samples, blackout_count)

    # Safety: ensure all timestamps have a result
    for t in timestamps:
        if t not in results:
            results[t] = 255.0

    if not any(b < blackout_threshold for b in results.values()) and len(results) > 0:
        # All chunks may have failed silently
        logger.debug("No blackouts detected in %d frames", len(results))

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

_SCOREBAR_MIN_SECONDARY_STD = 12.0
"""Minimum cross-section std for the 2nd-highest channel.

FL scorebar 3GC colors produce high std in all 3 RGB channels (26-48).
Loading screen gradients typically affect only 1 channel (e.g. R std 31.7
while G, B std < 5).  Requiring 2+ channels above this threshold
rejects single-channel gradient false positives.  (#201)
12.0 sits between queue max (~8.8) and FL min (~26) with margin.
"""

_SCOREBAR_EDGE_THRESHOLD = 8.0
"""Minimum per-channel horizontal edge magnitude in scorebar ROI.

FL scorebar band boundaries produce sharp pixel transitions where
adjacent sections meet (typical max edge 20-60).  Loading screens
have smooth gradients with max edge < 5.  Computed per RGB channel
to detect chrominance-only boundaries (same luminance, different hue).
8.0 provides safe margin between gradient max (~5) and FL min (~20).
"""


# ---------------------------------------------------------------------------
# V2 Scorebar Detection: GC-Emblem 3-point AND (#307)
# ---------------------------------------------------------------------------

_SCOREBAR_V2_PROBE_WIDTH = 1920
"""Probe width for V2 scorebar detection.

GC emblem positions are defined at 1920x1080.  At lower resolutions the
emblem regions are too small (3-6 px at 320x180) for meaningful feature
extraction.
"""

_SCOREBAR_V2_PROBE_HEIGHT = 1080
"""Probe height for V2 scorebar detection (16:9 at 1920 width)."""

# GC emblem detection positions at 1920x1080 (absolute pixel coordinates).
# Each tuple: (name, x1, y1, x2, y2).
# Validated on 5 recordings (0408/0209/0116/0118/0119), N=156+ non-match
# frames with zero FP.
_EMBLEM_POSITIONS: list[tuple[str, int, int, int, int]] = [
    ("left", 600, 2, 665, 40),
    ("center", 828, 22, 862, 42),
    ("right", 1263, 2, 1318, 40),
]

_EMBLEM_SAT_THRESHOLD = 70.0
"""Minimum mean HSV saturation (of bright pixels) at each emblem position.

GC emblems show high saturation (typically 100-220 in-match).  Lobby
backgrounds at emblem positions show median saturation of 66-79, with
occasional peaks up to 179 at individual positions -- but never all 3
positions simultaneously exceeding the threshold.
Validated: 5 recordings, 156+ non-match frames, zero 3-position FP.
"""

_EMBLEM_EDGE_THRESHOLD = 40.0
"""Minimum Sobel edge density at each emblem position.

GC emblem icons have complex internal structure producing high edge
density (typically 60-200 in-match).  Lobby backgrounds at emblem
positions show median edge density of 25-40.  Even individual positions
exceeding the threshold (max 225) do not cause FP due to the 3-point
AND condition.
Validated: 5 recordings, 156+ non-match frames, zero 3-position FP.
"""

# Method selector: "v2" (GC-emblem 3-point AND) or "v1" (channel-std).
_SCOREBAR_METHOD: str = "v2"


def _probe_frame_rgb_hires(video_path: Path, timestamp: float) -> bytes | None:
    """Probe a single frame at 1920x1080 for V2 scorebar detection.

    Similar to ``_probe_frame_rgb`` but uses fixed 1920x1080 resolution
    instead of the low-resolution 320x180.  Used only during the scorebar
    classification phase, not for pass-1/pass-2 blackout detection.
    """
    width = _SCOREBAR_V2_PROBE_WIDTH
    height = _SCOREBAR_V2_PROBE_HEIGHT
    rgb_size = width * height * 3
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
        f"scale={width}:{height},format=rgb24",
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


def _has_scorebar_v2(raw_rgb: bytes | None) -> bool | None:
    """Determine if FL scorebar is present using GC-emblem 3-point AND.

    Checks 3 fixed positions in the scorebar where GC emblems appear
    (left/center/right).  At each position, computes HSV saturation and
    Sobel edge density.  Returns True only if ALL 3 positions exceed
    both thresholds (AND condition).

    This exploits the structural invariant that FL scorebar always has
    3 GC emblems at fixed positions, while lobby backgrounds never have
    high-saturation + high-edge-density content at all 3 positions
    simultaneously.

    Requires 1920x1080 input (see ``_probe_frame_rgb_hires``).

    Returns True if scorebar detected, False if not, or None if probe
    failed (raw_rgb is None).

    Validated on 5 recordings (0408/0209/0116/0118/0119):
    - 156+ non-match frames: zero FP
    - In-match TPR: 98.7% (FN only on UI-hidden transition frames)
    """
    if raw_rgb is None:
        return None

    try:
        import cv2
    except ImportError:
        logger.warning(
            "opencv-python-headless not installed; "
            "falling back to V1 scorebar detection"
        )
        return None

    width = _SCOREBAR_V2_PROBE_WIDTH
    height = _SCOREBAR_V2_PROBE_HEIGHT
    frame = np.frombuffer(raw_rgb, dtype=np.uint8).reshape(height, width, 3)

    for name, x1, y1, x2, y2 in _EMBLEM_POSITIONS:
        region = frame[y1:y2, x1:x2, :]
        bgr = cv2.cvtColor(region, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        # Saturation of bright pixels (exclude very dark pixels)
        val = hsv[:, :, 2].astype(np.float32)
        sat = hsv[:, :, 1].astype(np.float32)
        bright_mask = val > 30
        if bright_mask.sum() > 5:
            mean_sat = float(sat[bright_mask].mean())
        else:
            mean_sat = 0.0

        # Edge density (Sobel magnitude)
        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        edge_density = float(np.sqrt(sobel_x**2 + sobel_y**2).mean())

        if mean_sat <= _EMBLEM_SAT_THRESHOLD or edge_density <= _EMBLEM_EDGE_THRESHOLD:
            logger.debug(
                "scorebar_v2: %s sat=%.1f edge=%.1f -> fail (th: sat>%.0f edge>%.0f)",
                name,
                mean_sat,
                edge_density,
                _EMBLEM_SAT_THRESHOLD,
                _EMBLEM_EDGE_THRESHOLD,
            )
            return False

    logger.debug("scorebar_v2: all 3 positions passed -> True")
    return True


def _has_scorebar(raw_rgb: bytes | None, height: int) -> bool | None:
    """Determine if FL scorebar is present in the frame.

    Returns True if scorebar detected, False if not, or None if probe
    failed (raw_rgb is None).

    Uses a 4-condition AND gate (#121, #201, #200):
    - 20 < roi_brightness < 140 (FL match typical range)
    - max cross-section channel std > 15.0 (3GC color separation)
    - 2nd-highest channel std > 12.0 (multi-channel variation, A1)
    - max per-channel horizontal edge > 8.0 (sharp band boundaries, A2)
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
            "scorebar: brightness=%.1f (out of 20-140 range) -> False",
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
    if max_channel_std <= _SCOREBAR_CHANNEL_STD_THRESHOLD:
        logger.debug(
            "scorebar: brightness=%.1f ch_std=[R=%.1f G=%.1f B=%.1f] "
            "max=%.1f <= %.1f -> False",
            roi_brightness,
            *channel_stds,
            max_channel_std,
            _SCOREBAR_CHANNEL_STD_THRESHOLD,
        )
        return False

    # A1: Require at least 2 channels with high cross-section std.
    # FL scorebar 3GC colors produce high std in all channels (26-48).
    # Loading screen gradients affect only 1 channel.  (#201)
    sorted_stds = sorted(channel_stds)
    secondary_std = sorted_stds[-2]
    if secondary_std <= _SCOREBAR_MIN_SECONDARY_STD:
        logger.debug(
            "scorebar: brightness=%.1f ch_std=[R=%.1f G=%.1f B=%.1f] "
            "secondary=%.1f <= %.1f -> False (A1)",
            roi_brightness,
            *channel_stds,
            secondary_std,
            _SCOREBAR_MIN_SECONDARY_STD,
        )
        return False

    # A2: Require sharp horizontal edges in ROI (band boundaries).
    # FL scorebar has distinct color bands with sharp transitions (edge 20-60).
    # Loading screens have smooth gradients (edge < 5).
    # Computed per RGB channel to detect chrominance-only boundaries.
    roi_int = roi.astype(np.int16)
    h_edges = np.abs(roi_int[:, 1:, :] - roi_int[:, :-1, :])
    max_edge = float(h_edges.max())
    if max_edge <= _SCOREBAR_EDGE_THRESHOLD:
        logger.debug(
            "scorebar: brightness=%.1f ch_std max=%.1f "
            "max_edge=%.1f <= %.1f -> False (A2)",
            roi_brightness,
            max_channel_std,
            max_edge,
            _SCOREBAR_EDGE_THRESHOLD,
        )
        return False

    logger.debug(
        "scorebar: brightness=%.1f ch_std=[R=%.1f G=%.1f B=%.1f] "
        "secondary=%.1f max_edge=%.1f -> True",
        roi_brightness,
        *channel_stds,
        secondary_std,
        max_edge,
    )

    return True


_TRANSITION_THRESHOLD = 55.0
"""Brightness threshold for transition regions adjacent to blackouts.

Game frames are typically 60-120, while lobby/waiting screens are ~51.
Frames below this threshold that are adjacent to a blackout region are
included in the expanded region, allowing short blackouts followed by
lobby screens to be detected as match boundaries.
"""

_BLACKOUT_THRESHOLD_UPPER_MARGIN = 2.0
"""Upper hysteresis margin for Pass 1 blackout judgment (#361).

Pass 1 judges a frame as blackout when ``brightness < blackout_threshold +
_BLACKOUT_THRESHOLD_UPPER_MARGIN``.  Catches frames that sit just above
the strict threshold due to decoder-path variance (chunked fps filter vs
single-frame decode returning different brightnesses for the same
timestamp).  False positives are rejected by Pass 2 precise 0.25s
measurement and scorebar classification.

Set to 0.0 to disable A4 hysteresis (pre-#361 behavior).
"""

_ENABLE_BORDERLINE_REFINEMENT = True
"""If True, Pass 2 refines +-_BORDERLINE_REFINE_RADIUS around Pass 1
borderline frames (#361).

Borderline = brightness in ``[blackout_threshold, blackout_threshold * 2)``.
These are near-miss frames that may surround short blackouts (<=2.5s)
missed by Pass 1 sample_interval.  Adding +-3s windows to Pass 2's
refinement set lets 0.25s probing catch the real blackout even if
Pass 1 never saw a frame below threshold.

Set to False to restore pre-#361 behavior.
"""

_BORDERLINE_REFINE_RADIUS = 3.0
"""Seconds on each side of borderline timestamps added to Pass 2 refinement (#361).

+-3s covers the worst case of a 2.5s blackout centered between two
Pass 1 samples spaced 3s apart.  Pass 2's own +-_REFINE_WINDOW (5s)
further extends the probe window, so effective coverage is +-8s.
"""

_REFINE_INTERVAL = 0.25
"""Fine interval for 2nd-pass re-probing of blackout candidates."""

_REFINE_WINDOW = 5.0
"""Seconds to probe before and after each blackout region in pass 2."""

_REFINED_MIN_BLACKOUT = 1.5
"""Min blackout duration when using refined (0.25s) measurements.

At interval=0.25s, a 2.0s blackout measures ~1.5-1.75s (>= 1.5 -> detected)
while a 1.5s respawn measures ~1.0-1.25s (< 1.5 -> filtered).
"""

_BLACKOUT_PADDING = 3.0
"""Seconds to offset cut points into blackout regions.

With ``-c copy``, FFmpeg can only cut at keyframes (~2s apart for OBS).
By placing cut points inside blackout regions, keyframe drift never
clips actual match footage.
"""


def _borderline_pseudo_regions(
    results: dict[float, float],
    blackout_threshold: float,
    total_duration: float,
) -> list[tuple[float, float]]:
    """Build pseudo-regions around Pass 1 borderline frames (A3, #361).

    A borderline frame sits in ``[blackout_threshold, blackout_threshold * 2)``
    -- close to blackout but not dark enough to pass the strict Pass 1 cut.
    Each borderline timestamp produces a +-``_BORDERLINE_REFINE_RADIUS``
    window so Pass 2 precise sampling probes around it.
    """
    radius = _BORDERLINE_REFINE_RADIUS
    upper = blackout_threshold * 2
    return [
        (max(0.0, t - radius), min(total_duration, t + radius))
        for t, b in results.items()
        if blackout_threshold <= b < upper
    ]


def _merge_regions(
    regions: list[tuple[float, float]],
    sample_interval: float,
) -> list[tuple[float, float]]:
    """Sort and merge overlapping or adjacent (start, end) regions."""
    if not regions:
        return []
    tolerance = sample_interval * 2
    sorted_regions = sorted(regions)
    merged: list[tuple[float, float]] = [sorted_regions[0]]
    for start, end in sorted_regions[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= tolerance:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


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
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[tuple[float, float]]:
    """Re-probe blackout regions at fine interval for precise duration.

    For each region, probes +-_REFINE_WINDOW seconds at _REFINE_INTERVAL
    to get an accurate measurement of the blackout duration.  Returns
    updated regions with refined start/end times.

    *progress_callback* fires once before probing with ``(0, total_probes)``
    to publish the total, then once per completed probe with the running
    ``(completed, total)``.  This lets callers drive a progress bar during
    the long ThreadPoolExecutor wait (#366).
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
    total_probes = len(sorted_probes)

    if progress_callback is not None:
        progress_callback(0, total_probes)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_single_frame, video_path, t): t for t in sorted_probes
        }
        completed = 0
        for future in as_completed(futures):
            t = futures[future]
            try:
                results[t] = future.result()
            except VideoProcessingError:
                results[t] = 255.0
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total_probes)

    # Re-extract blackout regions from fine-grained data
    fine_blackout_times = sorted(
        t for t, b in results.items() if b < blackout_threshold
    )
    return _group_blackout_regions(fine_blackout_times, _REFINE_INTERVAL)


_BOUNDARY_CLASSES = {"match_boundary", "in_match"}


def _infer_segment_type(left_cls: str, right_cls: str) -> str:
    """Infer segment type from adjacent blackout classifications."""
    if left_cls in _BOUNDARY_CLASSES and right_cls in _BOUNDARY_CLASSES:
        return "fl_match"
    return "unknown"


def _filter_and_extract_segments(
    blackout_regions: list[tuple[float, float]],
    total_duration: float,
    min_match_duration: float,
    min_blackout_duration: float = 3.0,
    classifications: list[str] | None = None,
) -> list[MatchBoundary]:
    """Filter blackout regions by duration and extract match segments.

    Removes regions shorter than *min_blackout_duration*, then extracts
    gaps between remaining regions as match candidates.  Cut points are
    offset into the blackout regions by ``_BLACKOUT_PADDING`` so that
    keyframe-level imprecision in ``-c copy`` mode never clips match
    footage.

    When *classifications* is provided, each segment receives a ``"type"``
    field inferred from adjacent blackout classifications.
    """
    if not blackout_regions:
        if total_duration >= min_match_duration:
            return [{"start": 0.0, "end": total_duration, "type": "unknown"}]
        return []

    # Filter out short blackout regions (e.g. respawn blackouts 1-2s)
    if classifications is not None:
        paired = [
            (r, c)
            for r, c in zip(blackout_regions, classifications, strict=True)
            if r[1] - r[0] >= min_blackout_duration
        ]
        if paired:
            blackout_regions, filtered_cls = [
                list(x) for x in zip(*paired, strict=True)
            ]
        else:
            blackout_regions = []
            filtered_cls = []
    else:
        blackout_regions = [
            (s, e) for s, e in blackout_regions if e - s >= min_blackout_duration
        ]
        filtered_cls = None

    if not blackout_regions:
        if total_duration >= min_match_duration:
            return [{"start": 0.0, "end": total_duration, "type": "unknown"}]
        return []

    # Extract segments between blackout regions
    segments: list[MatchBoundary] = []

    # Before first blackout
    if blackout_regions[0][0] > 0:
        seg_start = 0.0
        seg_end = _padded_end(blackout_regions[0])
        seg_end = min(seg_end, total_duration)
        if seg_end - seg_start >= min_match_duration:
            segments.append(
                {
                    "start": seg_start,
                    "end": seg_end,
                    "type": "unknown",
                }
            )

    # Between blackout regions
    for i in range(len(blackout_regions) - 1):
        seg_start = _padded_start(blackout_regions[i])
        seg_start = max(seg_start, 0.0)
        seg_end = _padded_end(blackout_regions[i + 1])
        seg_end = min(seg_end, total_duration)
        if seg_end - seg_start >= min_match_duration:
            seg_type = (
                _infer_segment_type(filtered_cls[i], filtered_cls[i + 1])
                if filtered_cls is not None
                else "unknown"
            )
            segments.append(
                {
                    "start": seg_start,
                    "end": seg_end,
                    "type": seg_type,
                }
            )

    # After last blackout
    seg_start = _padded_start(blackout_regions[-1])
    seg_start = max(seg_start, 0.0)
    if total_duration - seg_start >= min_match_duration:
        segments.append(
            {
                "start": seg_start,
                "end": total_duration,
                "type": "unknown",
            }
        )

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
