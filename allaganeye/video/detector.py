"""Match boundary detection using parallel ffmpeg frame probing."""

import logging
import math
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path
from typing import IO, TypedDict

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
    scorebar_elapsed_s: float
    audio_promotions: int
    # Refined-region count entering _filter_and_extract_segments (#388).
    # Paired with filter_drops so verbose can report
    # ``<candidates> -> <final matches>`` with breakdown.
    filter_candidates: int
    filter_drops: dict[str, int]  # keys: below_min_match_duration, other
    # Count of segments returned with type=="unknown" (#433). Used by the
    # verbose ``+ N unknown match`` line so the user can reconcile
    # Filter "kept" with the larger Detected count when a recording
    # starts / ends mid-match.
    filter_unknown: int


logger = logging.getLogger(__name__)

_SAMPLE_WIDTH = 320
_SAMPLE_HEIGHT = 180
_FRAME_SIZE = _SAMPLE_WIDTH * _SAMPLE_HEIGHT  # grayscale, 1 byte per pixel

# Dual seek (#576 Option 1): input seek lead-in margin (seconds).
# Input -ss jumps to the keyframe BEFORE (chunk_start - SEEK_LEAD_SECONDS)
# so ffmpeg only decodes the small GOP pre-roll, not from t=0.
# OBS AV1 keyframe interval is typically 2s; 5s gives 2.5x slack.
SEEK_LEAD_SECONDS = 5.0


def _resolve_fps_rational(
    fps_num: int | None,
    fps_den: int | None,
    source_fps: float | None,
) -> tuple[int, int]:
    """Resolve (num, den) from rational-first / float-fallback inputs (#576 S2.3).

    Priority:
    1. ``fps_num`` + ``fps_den`` both given -> use as-is
    2. ``source_fps`` (float) only -> ``Fraction(...).limit_denominator(10000)``
    3. all None -> raise VideoProcessingError (caller should not call here
       without source_fps; legacy path is selected via env var separately)
    """
    # probe.py returns (0, 0) on parse failure; we deliberately fall through
    # to source_fps (float) for that case via the > 0 checks below.
    if fps_num is not None and fps_den is not None and fps_num > 0 and fps_den > 0:
        return fps_num, fps_den
    if source_fps and source_fps > 0:
        frac = Fraction(source_fps).limit_denominator(10000)
        return frac.numerator, frac.denominator
    raise VideoProcessingError(
        "source_fps not provided to detector (need fps_num/fps_den or source_fps)."
    )


def _sample_chunk_frames(
    stream: IO[bytes] | None,
    chunk_start: float,
    chunk_timestamps: list[float],
    fps_num: int,
    fps_den: int,
    expected_frames: int,
    is_tail_chunk: bool,
) -> dict[float, float]:
    """Sample frames from a pre-filtered stream (#576 select-filter path).

    With ffmpeg-level ``select='not(mod(n,N))'`` filter, the stream emits
    exactly one frame per ``chunk_timestamps`` entry (in order).  Emitted
    frame K is mapped directly to ``chunk_timestamps[K]``.  The rational-fps
    ``round((t-chunk_start) * fps_num / fps_den)`` math is handled at the
    ffmpeg layer; Python just assigns frames by position.

    Args:
        stream: A binary file-like object (``IO[bytes]``) yielding raw
            grayscale frames (320x180 = ``_FRAME_SIZE`` bytes per frame)
            from a ``subprocess.Popen`` with ``select`` filter +
            ``-fps_mode passthrough``.  Must not be ``None``.
        chunk_start: Wall-clock start time of the chunk (seconds).
            Kept in signature for API stability; not used for index math.
        chunk_timestamps: Pre-computed global grid timestamps for this chunk
            (sorted ascending).  Each becomes a key in the returned dict.
            Emitted frame K -> chunk_timestamps[K].
        fps_num / fps_den: Source video frame rate as rational.  Used only
            for the slack computation in the dynamic VFR check.
        expected_frames: ``len(chunk_timestamps)`` -- the number of frames
            the ffmpeg ``select`` filter is expected to emit.
        is_tail_chunk: True when this chunk ends at (or within 1.0s of)
            the video duration.  Tail chunks may emit fewer frames than
            expected; the VFR check downgrades to WARN-only for them.

    Returns:
        ``{timestamp: brightness}`` mapping for every entry in
        ``chunk_timestamps``.  Targets whose emitted frame was not received
        get 255.0 (safe non-blackout fallback, #214 contract preserved).

    Raises:
        VideoProcessingError: when the chunk is non-tail and the emitted
        frame count deviates from ``expected_frames`` by more than
        ``max(expected_frames * 0.01, ceil(source_fps * 0.1))`` frames
        (dynamic VFR / decoder anomaly detection).
    """
    if stream is None:
        raise VideoProcessingError("ffmpeg stdout not available")

    source_fps = fps_num / fps_den

    results: dict[float, float] = {}
    emit_count = 0

    # Memory budget: one _FRAME_SIZE bytes chunk at a time.
    # Emitted frame K -> chunk_timestamps[K] (positional mapping).
    while True:
        raw = stream.read(_FRAME_SIZE)
        if len(raw) < _FRAME_SIZE:
            break
        if emit_count < len(chunk_timestamps):
            frame = np.frombuffer(raw, dtype=np.uint8)
            brightness = float(frame.mean())
            results[chunk_timestamps[emit_count]] = brightness
        emit_count += 1

    # Targets whose frames were not emitted: 255.0 fallback (#214)
    for t in chunk_timestamps:
        if t not in results:
            results[t] = 255.0  # safe non-blackout fallback (#214)

    slack = max(int(expected_frames * 0.01), math.ceil(source_fps * 0.1))
    diff = abs(emit_count - expected_frames)
    if diff > slack:
        msg = (
            f"Dynamic VFR detection: chunk emitted {emit_count} frames, "
            f"expected {expected_frames} (slack=+-{slack}). "
            f"Input may be VFR or decoder anomaly."
        )
        if is_tail_chunk:
            logger.warning(
                "%s tail chunk -- decoder truncation allowed, continuing.",
                msg,
            )
        else:
            raise VideoProcessingError(msg)

    return results


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
    scorebar_progress_callback: Callable[[int, int], None] | None = None,
    audio_hits: Sequence[BgmHit] | None = None,
    stats: DetectionStats | None = None,
    chunk_progress_callback: Callable[[int, int, float], None] | None = None,
    chunk_dispatch_callback: Callable[[int], None] | None = None,
    gpu_vendor: str | None = None,
    brightness_callback: Callable[[dict[float, float]], None] | None = None,
    # #576: rational fps propagation (preferred over float source_fps).
    # Either pair (num+den) takes precedence; float source_fps is the
    # backward-compatible fallback (Fraction.limit_denominator path).
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
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
        refine_progress_callback: Optional callback invoked during Pass 2
            refinement with ``(completed_probes, total_probes)``.  Scoped
            to Pass 2 only; scorebar filtering progress goes through
            ``scorebar_progress_callback`` so unit-mixed rollover (#393)
            is impossible by construction.
        scorebar_progress_callback: Optional callback invoked during
            scorebar classification with ``(completed_regions, total_regions)``.
            Opens/closes independently from Pass 2 so the two phases can
            render as separate progress bars (#393).
        audio_hits: Optional Fanfare peaks from audio scan (#288).  When
            provided and scorebar filtering is active, blackouts
            classified as ``"in_match"`` but near a Fanfare hit are
            promoted to ``"match_boundary"``.
        brightness_callback: Optional callback invoked once after Pass 1
            completes with the full ``{timestamp_s: brightness}`` mapping.
            Used by the GUI (#569) to render the complete-screen
            brightness timeline without a second sampling pass.  The
            mapping covers every timestamp between 0 and ``duration_hint``
            at ``sample_interval`` spacing; non-blackout fallbacks (255.0)
            are included so consumers can plot continuous data.

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
                chunk_dispatch_callback=chunk_dispatch_callback,
                vendor=gpu_vendor,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
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
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
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
            source_fps_num=source_fps_num,
            source_fps_den=source_fps_den,
            source_fps=source_fps,
        )
    pass1_elapsed = time.monotonic() - pass1_start

    # #569 -- hand the GUI the full brightness map before any further
    # filtering / refinement so the complete-screen timeline can be
    # rendered straight from metadata.json without re-running ffmpeg.
    if brightness_callback is not None:
        brightness_callback(results)

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

    # 2nd pass: refine blackout regions at fine interval (#77).
    # progress_callback fires per probe so the Refining bar advances during
    # the long ThreadPoolExecutor wait (#366).  This callback reports
    # Pass 2 progress in **probe units** only; scorebar filtering
    # progress flows through scorebar_progress_callback (#393) so the
    # caller can render them as separate bars without unit-mixed
    # 100% -> 99% rollover.
    pass2_start = time.monotonic()
    refined_regions = _refine_blackout_regions(
        video_path,
        blackout_regions,
        blackout_threshold,
        duration_hint,
        workers,
        progress_callback=refine_progress_callback,
    )
    pass2_elapsed = time.monotonic() - pass2_start
    if stats is not None:
        stats["pass2_regions"] = len(refined_regions)
        stats["pass2_elapsed_s"] = pass2_elapsed

    # Scorebar-based filtering: remove in-match and non-FL blackouts (#111)
    region_classifications: list[str] | None = None
    if src_resolution is not None:
        from allaganeye.video.scorebar import filter_blackouts_with_scorebar

        height = _scaled_height(src_resolution[0], src_resolution[1])
        scorebar_start = time.monotonic()
        refined_regions, region_classifications = filter_blackouts_with_scorebar(
            video_path,
            refined_regions,
            duration_hint,
            height,
            workers,
            audio_hits=audio_hits,
            stats=stats,
            progress_callback=scorebar_progress_callback,
        )
        scorebar_elapsed = time.monotonic() - scorebar_start
        if stats is not None:
            stats["scorebar_elapsed_s"] = scorebar_elapsed

    effective_min = min(min_blackout_duration, _REFINED_MIN_BLACKOUT)
    return _filter_and_extract_segments(
        refined_regions,
        duration_hint,
        min_match_duration,
        effective_min,
        classifications=region_classifications,
        stats=stats,
    )


def _decode_chunk_cpu(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    *,
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
    is_tail_chunk: bool = False,
) -> dict[float, float]:
    """Decode a chunk in CPU mode.

    Dispatches to the legacy fps-filter path when env var
    ``ALLAGANEYE_DETECT_FPS_FILTER=1`` is set or when rational fps cannot
    be resolved.  Otherwise uses the new output-seek + Python N-th
    sampling path (#576).
    """
    if not chunk_timestamps:
        return {}

    use_legacy = _use_legacy_fps_filter() or (
        source_fps_num is None and source_fps_den is None and source_fps is None
    )
    if use_legacy:
        return _decode_chunk_cpu_legacy(
            video_path,
            chunk_timestamps,
            chunk_start,
            chunk_end,
            sample_interval,
        )

    fps_num, fps_den = _resolve_fps_rational(
        source_fps_num,
        source_fps_den,
        source_fps,
    )
    return _decode_chunk_cpu_v2(
        video_path,
        chunk_timestamps,
        chunk_start,
        chunk_end,
        sample_interval,
        fps_num,
        fps_den,
        is_tail_chunk,
    )


def _decode_chunk_cpu_legacy(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
) -> dict[float, float]:
    """Legacy fps-filter chunk decode (pre-#576). Kept for env var rollback.

    Scheduled for removal in v0.3.x patch release.
    """
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


def _decode_chunk_cpu_v2(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    fps_num: int,
    fps_den: int,
    is_tail_chunk: bool,
) -> dict[float, float]:
    """New path: dual seek + select filter + -fps_mode passthrough (#576 Option 1).

    Dual seek layout::

        -ss <input_seek> -i <video> -ss <output_seek> -t <chunk_duration>

    Input ``-ss`` BEFORE ``-i``: fast container index jump to keyframe near
    ``chunk_start - SEEK_LEAD_SECONDS`` (~10ms, no decode).  Output ``-ss``
    AFTER ``-i``: accurate frame-level trim of the small GOP pre-roll
    (typically SEEK_LEAD_SECONDS worth of frames).  The filter graph then
    receives frames starting at ``chunk_start``; the ``select`` filter's
    ``n`` counter resets at filter graph input, so frame 0 corresponds to
    ``chunk_start``.

    This replaces the previous pure output-seek design where ffmpeg decoded
    from t=0 for every chunk, causing O(N^2/2) total decode for N=32 chunks
    (~16.5x full-video decodes -> 67 min on RTX 5090 for a 2h recording).
    With dual seek, the per-chunk pre-roll is bounded by SEEK_LEAD_SECONDS
    (5s x 32 = 160s of duplicate decode vs 16.5x full-video).

    The ``select='not(mod(n,N))'`` filter drops frames at the ffmpeg layer
    (frame-index based, NOT PTS-based -- deterministic across versions)
    before they reach the pipe, reducing pipe IO from ~28 GB to ~178 MB
    per 2h video at 60fps + sample_interval=3.0s.

    N = round(sample_interval * fps_num / fps_den).  For 60fps +
    sample_interval=3.0, N=180 -> ffmpeg emits frame 0, 180, 360, ...
    Python maps emitted frame K to chunk_timestamps[K] (positional).
    """
    chunk_duration = chunk_end - chunk_start
    # #576: frame-index step for ffmpeg select filter.
    # N selects every Nth decoded frame (deterministic, unlike PTS-based
    # fps filter).  For 60fps + sample_interval=3.0, N=180.
    #
    # Float arithmetic is acceptable here: sample_interval is a float
    # CLI option, fps_num/fps_den are positive ints from probe.py.  The
    # round() collapses to int and the worst-case relative error
    # (~1/min(fps_num,fps_den) <= 1/24 over realistic sample_intervals)
    # is dwarfed by the >=1.4s blackout duration the detector cares
    # about.  Spec S2.2 NTSC drift note covers the same trade-off.
    n_step = max(1, round(sample_interval * fps_num / fps_den))
    # expected_frames = number of selected frames = len(chunk_timestamps)
    expected_frames = len(chunk_timestamps)

    # Dual seek: input seek jumps to keyframe near chunk_start (fast),
    # output seek trims the GOP pre-roll so filter graph starts at chunk_start.
    input_seek: float = max(0.0, chunk_start - SEEK_LEAD_SECONDS)
    output_seek: float = (
        chunk_start - input_seek
    )  # = SEEK_LEAD_SECONDS unless chunk_start < SEEK_LEAD_SECONDS

    cmd = [
        find_ffmpeg(),
        "-threads",
        "1",
        "-ss",
        str(input_seek),  # input seek (BEFORE -i): fast container jump
        "-i",
        str(video_path),
        "-ss",
        str(output_seek),  # output seek (AFTER -i): accurate trim to chunk_start
        "-t",
        str(chunk_duration),
        "-fps_mode",
        "passthrough",
        "-vf",
        f"select='not(mod(n\\,{n_step}))',scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]

    stderr_text = ""
    stderr_buf = tempfile.TemporaryFile(mode="w+b")
    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_buf,
        ) as proc:
            try:
                results = _sample_chunk_frames(
                    stream=proc.stdout,
                    chunk_start=chunk_start,
                    chunk_timestamps=chunk_timestamps,
                    fps_num=fps_num,
                    fps_den=fps_den,
                    expected_frames=expected_frames,
                    is_tail_chunk=is_tail_chunk,
                )
                proc.wait(timeout=max(300, int(chunk_duration * 2)))
                # Read stderr from temp file (no pipe backpressure issue)
                stderr_buf.seek(0)
                stderr_text = stderr_buf.read().decode(errors="replace")
            except VideoProcessingError:
                proc.kill()
                # still try to capture stderr for error context
                try:
                    stderr_buf.seek(0)
                    stderr_text = stderr_buf.read().decode(errors="replace")
                except Exception:
                    logger.debug("Failed to read stderr from temp file", exc_info=True)
                raise
            except subprocess.TimeoutExpired:
                proc.kill()
                logger.warning(
                    "CPU chunk v2 decode timed out [%.1f-%.1f]",
                    chunk_start,
                    chunk_end,
                )
                return {t: 255.0 for t in chunk_timestamps}
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    finally:
        stderr_buf.close()

    if proc.returncode != 0:
        logger.warning(
            "CPU chunk v2 decode failed [%.1f-%.1f]: %s",
            chunk_start,
            chunk_end,
            stderr_text[-200:],
        )
        return {t: 255.0 for t in chunk_timestamps}

    return results


def _scan_cpu(
    video_path: Path,
    duration_hint: float,
    sample_interval: float,
    blackout_threshold: float,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    *,
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
) -> dict[float, float]:
    """CPU mode: chunked decode (output seek + Python N-th sampling, #576).

    When ``source_fps_num``/``source_fps_den`` (or float ``source_fps``) is
    provided AND env var ``ALLAGANEYE_DETECT_FPS_FILTER`` is not set, uses
    the new output-seek path.  Otherwise falls back to the legacy
    fps-filter path.
    """
    timestamps = _generate_timestamps(duration_hint, sample_interval)
    if not timestamps:
        return {}

    total_samples = len(timestamps)
    num_chunks = min(os.cpu_count() or 4, 32)
    chunk_duration = duration_hint / num_chunks

    # Distribute pre-computed timestamps to chunks (with overlap)
    chunks: list[tuple[float, float, list[float], bool]] = []
    for i in range(num_chunks):
        c_start = i * chunk_duration
        c_end = min((i + 1) * chunk_duration + sample_interval, duration_hint)
        c_timestamps = [t for t in timestamps if c_start <= t < c_end]
        is_tail = c_end >= duration_hint - 1.0
        if c_timestamps:
            chunks.append((c_start, c_end, c_timestamps, is_tail))

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
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
                is_tail_chunk=is_tail,
            ): (c_start, c_ts)
            for c_start, c_end, c_ts, is_tail in chunks
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

# Legacy absolute coordinates above are kept for reference and for tests
# that exercise fixed-layout frame builders.  Production code uses
# ``_EMBLEM_RELATIVE_POSITIONS`` with ``_find_scorebar_horizontal_range``
# to follow HUD scale variations (1080p OBS vs 4K Game DVR) -- see #522.
#
# Ratios measured against dynamically-detected scorebar span on 13
# in-match frames across 3 OBS 1080p recordings (20260116/20260118/
# 20260119) on 2026-04-22.  half-width ratios equal current absolute
# half-widths (32.5 / 17 / 27.5 px) divided by median detected span
# (717 px).  See .scorebar_measure_emblem.py for the measurement script.
_EMBLEM_RELATIVE_POSITIONS: list[tuple[str, float, float, int, int]] = [
    # (name, x_rel_center, half_width_rel, y1, y2)
    ("left", 0.0455, 0.0453, 2, 40),
    ("center", 0.3427, 0.0237, 22, 42),
    ("right", 0.9638, 0.0384, 2, 40),
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


# ---------------------------------------------------------------------------
# Scorebar horizontal range detection (V2 dynamic positioning, #522)
# ---------------------------------------------------------------------------
# The scorebar's horizontal extent varies between recording setups:
# 1080p OBS captures draw it nearly full-width, while 4K Game DVR draws
# it narrower and more centered (HUD-scale / render-range / window-mode
# differences -- not a resolution-scaling artifact).  V2 emblem detection
# locates the scorebar dynamically and computes emblem positions as
# ratios of that range, replacing hardcoded absolute coordinates.

_SCOREBAR_SCAN_Y_START = 0
_SCOREBAR_SCAN_Y_END = 45
"""Vertical slice (pixel rows) to analyze for scorebar horizontal extent.

Covers y=0..45 in the 1920x1080 probe frame to include the colored band
without stepping into emblem glyphs below.  Both 1080p OBS and 4K Game
DVR captures place the FL scorebar within this row range.
"""

_SCOREBAR_SCAN_SAT_THRESHOLD = 80.0
"""Minimum per-pixel HSV saturation to qualify as a scorebar pixel.

FL scorebar red/blue/yellow bands show saturation typically >= 150.
Lobby backgrounds show median saturation 66-79.  80 sits in the gap.
"""

_SCOREBAR_SCAN_VAL_THRESHOLD = 60.0
"""Minimum per-pixel HSV value (brightness) to exclude dark frames."""

_SCOREBAR_SCAN_COL_RATIO = 0.30
"""Fraction of rows in scan ROI that must be saturated for a column.

Robust against anti-aliased band edges and thin sub-pixel details.
"""

_SCOREBAR_SCAN_MIN_WIDTH_PX = 500
"""Minimum detected span (pixels) to accept as scorebar.

1080p OBS scorebar spans ~712-1090 px.  4K Game DVR in-match span is
~613-620 px.  The floor of 500 safely clears both while rejecting 4K
Game DVR lobby UI artifacts (observed: ~409 px width at screen-top
minimap/content-name widget).  Confirmed during #522 validation.
"""

_SCOREBAR_SCAN_MAX_GAP_PX = 80
"""Maximum gap (pixels) to bridge when merging saturated runs.

Center of scorebar contains a timer / score-number gap of desaturated
columns; 80px covers it without merging across separate UI elements.
"""


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


def _find_scorebar_horizontal_range(raw_rgb: bytes) -> tuple[int, int] | None:
    """Detect horizontal extent [x_left, x_right] of the FL scorebar.

    Scans rows y=``_SCOREBAR_SCAN_Y_START``..``_SCOREBAR_SCAN_Y_END`` of a
    1920x1080 RGB frame, counts columns where at least
    ``_SCOREBAR_SCAN_COL_RATIO`` of rows have HSV saturation
    > ``_SCOREBAR_SCAN_SAT_THRESHOLD`` AND value
    > ``_SCOREBAR_SCAN_VAL_THRESHOLD``.  The longest contiguous run of
    saturated columns (bridging gaps up to ``_SCOREBAR_SCAN_MAX_GAP_PX``)
    becomes the scorebar span.

    Returns ``(x_left, x_right)`` with both endpoints inclusive when the
    detected span is at least ``_SCOREBAR_SCAN_MIN_WIDTH_PX`` wide.
    Returns ``None`` when:

    - cv2 is not installed (matches V2 "None -> V1 fallback" contract),
    - no saturated run is found (lobby / loading / all-dark frame), or
    - the longest run is narrower than the minimum width.
    """
    try:
        import cv2
    except ImportError:
        return None

    width = _SCOREBAR_V2_PROBE_WIDTH
    height = _SCOREBAR_V2_PROBE_HEIGHT
    frame = np.frombuffer(raw_rgb, dtype=np.uint8).reshape(height, width, 3)

    top = frame[_SCOREBAR_SCAN_Y_START:_SCOREBAR_SCAN_Y_END, :, :]
    bgr = cv2.cvtColor(top, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)

    pixel_mask = (sat > _SCOREBAR_SCAN_SAT_THRESHOLD) & (
        val > _SCOREBAR_SCAN_VAL_THRESHOLD
    )
    col_fraction = pixel_mask.mean(axis=0)
    col_saturated = col_fraction >= _SCOREBAR_SCAN_COL_RATIO

    raw_runs: list[tuple[int, int]] = []
    i = 0
    while i < width:
        if col_saturated[i]:
            j = i
            while j < width and col_saturated[j]:
                j += 1
            raw_runs.append((i, j - 1))
            i = j
        else:
            i += 1

    if not raw_runs:
        return None

    merged: list[tuple[int, int]] = [raw_runs[0]]
    for start, end in raw_runs[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end - 1 <= _SCOREBAR_SCAN_MAX_GAP_PX:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    longest = max(merged, key=lambda r: r[1] - r[0])
    span_width = longest[1] - longest[0] + 1
    if span_width < _SCOREBAR_SCAN_MIN_WIDTH_PX:
        return None

    return longest


def _emblem_and_check(
    frame: "np.ndarray",
    positions: list[tuple[str, int, int, int, int]],
    path_label: str,
    cv2_module,
) -> bool:
    """Evaluate 3-point emblem AND on the given positions.

    Returns True if ALL 3 emblems pass sat/edge thresholds, otherwise
    False.  Each position is ``(name, x1, y1, x2, y2)``.
    """
    for name, x1, y1, x2, y2 in positions:
        region = frame[y1:y2, x1:x2, :]
        bgr = cv2_module.cvtColor(region, cv2_module.COLOR_RGB2BGR)
        hsv = cv2_module.cvtColor(bgr, cv2_module.COLOR_BGR2HSV)
        gray = cv2_module.cvtColor(bgr, cv2_module.COLOR_BGR2GRAY)

        # Saturation of bright pixels (exclude very dark pixels)
        val = hsv[:, :, 2].astype(np.float32)
        sat = hsv[:, :, 1].astype(np.float32)
        bright_mask = val > 30
        if bright_mask.sum() > 5:
            mean_sat = float(sat[bright_mask].mean())
        else:
            mean_sat = 0.0

        # Edge density (Sobel magnitude)
        sobel_x = cv2_module.Sobel(gray, cv2_module.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2_module.Sobel(gray, cv2_module.CV_64F, 0, 1, ksize=3)
        edge_density = float(np.sqrt(sobel_x**2 + sobel_y**2).mean())

        if mean_sat <= _EMBLEM_SAT_THRESHOLD or edge_density <= _EMBLEM_EDGE_THRESHOLD:
            logger.debug(
                "scorebar_v2 (%s): %s x=%d..%d sat=%.1f edge=%.1f -> fail",
                path_label,
                name,
                x1,
                x2,
                mean_sat,
                edge_density,
            )
            return False
    logger.debug("scorebar_v2 (%s): all 3 positions passed -> True", path_label)
    return True


def _has_scorebar_v2(raw_rgb: bytes | None) -> bool | None:
    """Determine if FL scorebar is present using GC-emblem 3-point AND.

    Two-path evaluation with OR semantics:

    1. **Primary**: absolute coordinates (``_EMBLEM_POSITIONS``).
       This preserves the pre-#522 behavior validated on 5 recordings
       (0408/0209/0116/0118/0119) with 156+ non-match frames and zero
       FP.  Returns True immediately on AND pass (short-circuit).
    2. **Secondary**: dynamic scorebar horizontal range detection
       (``_find_scorebar_horizontal_range``) with emblem positions
       computed from ``_EMBLEM_RELATIVE_POSITIONS``.  This handles
       HUD-scale variations such as 4K Game DVR's narrow-centered
       scorebar (#522).  Evaluated only if Primary returned False.
       Returns True on AND pass.

    OR semantics ensures 1080p OBS validated set stays FP-free (Primary
    is authoritative), while 4K Game DVR recordings (where Primary fails
    due to scorebar layout offset) gain a rescue path via Secondary.

    At each position computes HSV saturation and Sobel edge density.
    Returns True only if all 3 positions in the same path exceed both
    thresholds (``_EMBLEM_SAT_THRESHOLD``, ``_EMBLEM_EDGE_THRESHOLD``).

    Requires 1920x1080 input (see ``_probe_frame_rgb_hires``).

    Returns ``True`` if scorebar detected by either path, ``False`` if
    both paths fail, or ``None`` if:

    - probe failed (``raw_rgb`` is None), or
    - opencv is not installed.

    The ``None`` contract lets ``_probe_scorebar_context`` fall back to
    V1 (channel-std) detection.

    Validated on 5 recordings (0408/0209/0116/0118/0119):
    - 156+ non-match frames: zero FP (Primary)
    - In-match TPR: 98.7% (FN only on UI-hidden transition frames)
    - 4K Game DVR regression fix: #522 (2026-04-22) -- Secondary
    - 20260219 long-recording regression fix: #522 two-path (2026-04-23)
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

    # Path 1: absolute coordinates (pre-#522 validated path).
    if _emblem_and_check(frame, list(_EMBLEM_POSITIONS), "absolute", cv2):
        return True

    # Path 2: dynamic span rescue for HUD-scaled recordings (4K Game DVR).
    span = _find_scorebar_horizontal_range(raw_rgb)
    if span is not None:
        x_left, x_right = span
        bar_width = x_right - x_left
        positions: list[tuple[str, int, int, int, int]] = [
            (
                name,
                int(x_left + cx_rel * bar_width - hw_rel * bar_width),
                y1,
                int(x_left + cx_rel * bar_width + hw_rel * bar_width),
                y2,
            )
            for name, cx_rel, hw_rel, y1, y2 in _EMBLEM_RELATIVE_POSITIONS
        ]
        if _emblem_and_check(
            frame, positions, f"dynamic span={x_left}..{x_right}", cv2
        ):
            return True

    return False


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

# ---------------------------------------------------------------------------
# Legacy fps-filter rollback switch (#576)
# ---------------------------------------------------------------------------
# Transitional escape hatch: when ALLAGANEYE_DETECT_FPS_FILTER=1 the
# detector reverts to the pre-#576 chunked fps=N filter path.  Default
# (= False) is the new output-seek + N-th sampling path.  Scheduled for
# removal in v0.3.x patch release (see CHANGELOG / docstring).


def _use_legacy_fps_filter() -> bool:
    """Return True when the legacy fps-filter path is forced via env var (#576).

    **Transitional / scheduled for removal in v0.3.x.**

    Setting ``ALLAGANEYE_DETECT_FPS_FILTER=1`` reverts the detector to
    the pre-#576 chunked ``fps=N`` filter path.  Originally provided as
    both an emergency escape hatch for ffmpeg version regressions AND
    a perf escape (output seek had ~10x regression).  Codex perf rescue
    Option 1 (dual seek, commit a864834) restored perf to legacy levels
    (~6m18s for obs-20260118 on RTX 5090 vs legacy ~7 min), so the perf
    angle is no longer relevant.  CI / production should NEVER set this
    var (CHANGELOG "Deprecated").

    Removal plan:

    - v0.3.0: env var supported (this function exists, returns env value)
    - v0.3.x: env var removed (this function deleted, only new path
      exists, _decode_chunk_cpu_legacy / _decode_chunk_legacy purged)

    See ``docs/superpowers/specs/2026-05-18-v030-l3-detect-fps-filter-retirement-design.md``
    S6 for rollback design and ``CHANGELOG.md`` for the deprecation
    timeline.
    """
    return os.environ.get("ALLAGANEYE_DETECT_FPS_FILTER") == "1"


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
    stats: DetectionStats | None = None,
) -> list[MatchBoundary]:
    """Filter blackout regions by duration and extract match segments.

    Removes regions shorter than *min_blackout_duration*, then extracts
    gaps between remaining regions as match candidates.  Cut points are
    offset into the blackout regions by ``_BLACKOUT_PADDING`` so that
    keyframe-level imprecision in ``-c copy`` mode never clips match
    footage.

    When *classifications* is provided, each segment receives a ``"type"``
    field inferred from adjacent blackout classifications.

    When *stats* is provided, the candidate count entering this function
    and the per-reason drop counts are recorded under
    ``stats["filter_candidates"]`` and ``stats["filter_drops"]`` (#388).
    ``filter_drops`` keys: ``"below_min_match_duration"`` (segment length
    short of the threshold) and ``"other"`` (whole-video candidate also
    below the threshold when no valid blackout remains).  scorebar-based
    drops (``in_match`` / ``non_fl``) stay in the dedicated
    ``scorebar_*`` fields -- this counter is strictly for the duration-
    based filters that happen inside this function.
    """
    # Candidate count reported as "the number of refined regions fed in";
    # scorebar filtering has already shrunk this above.  Pass 2 numbers
    # still live in ``pass2_regions``.
    if stats is not None:
        stats["filter_candidates"] = len(blackout_regions)
        # Reuse an existing dict if the caller pre-populated it (future
        # multi-stage increments), otherwise start fresh.
        drops = stats.get("filter_drops") or {}
        drops.setdefault("below_min_match_duration", 0)
        drops.setdefault("other", 0)
        stats["filter_drops"] = drops

    def _record_drop(key: str) -> None:
        if stats is not None:
            stats["filter_drops"][key] = stats["filter_drops"].get(key, 0) + 1

    def _finalize(segments: list[MatchBoundary]) -> list[MatchBoundary]:
        # Track unknown-typed segments so the verbose Filter section can
        # explain the ``Detected = kept + unknown`` discrepancy (#433).
        if stats is not None:
            stats["filter_unknown"] = sum(1 for s in segments if s["type"] == "unknown")
        return segments

    if not blackout_regions:
        if total_duration >= min_match_duration:
            return _finalize([{"start": 0.0, "end": total_duration, "type": "unknown"}])
        # Whole video was shorter than min_match_duration -- count the
        # implicit whole-video candidate as dropped.
        _record_drop("other")
        return _finalize([])

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
            return _finalize([{"start": 0.0, "end": total_duration, "type": "unknown"}])
        _record_drop("other")
        return _finalize([])

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
        else:
            _record_drop("below_min_match_duration")

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
        else:
            _record_drop("below_min_match_duration")

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
    else:
        _record_drop("below_min_match_duration")

    return _finalize(segments)


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
