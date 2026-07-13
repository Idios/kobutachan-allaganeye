"""Match boundary detection using parallel ffmpeg frame probing."""

import contextlib
import logging
import math
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path
from typing import IO, NotRequired, TypedDict

import numpy as np

from allaganeye.audio.matcher import BgmHit
from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.video.capture_region import (
    CaptureRegion,
    FULL_FRAME,
    RegionTimeline,
    ScorebarLocalization,
    region_mean,
)


class MatchBoundary(TypedDict):
    """A detected match segment with start/end times and type."""

    start: float
    end: float
    type: str
    # #805 段階2: set True on a post-match trailing segment (lobby/city after
    # the final match). The segment is retained non-destructively and excluded
    # from default split (MP4) output downstream; absent/False = normal match.
    post_match: NotRequired[bool]


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
    filter_drops: dict[
        str, int
    ]  # keys: below_min_match_duration, other, post_match_trailing (optional, #797)
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


def _frame_brightness(frame: np.ndarray, region: CaptureRegion = FULL_FRAME) -> float:
    """CPU scan の 1-D grayscale buffer (320*180,) の平均輝度。

    FULL_FRAME のときは 1-D のまま ``float(frame.mean())`` (現行と bit-exact、
    reshape による丸め経路変化なし)。band region のときのみ
    ``(_SAMPLE_HEIGHT, _SAMPLE_WIDTH)`` に reshape して ``region_mean`` で crop する。
    """
    if region.is_full_frame():
        return float(frame.mean())
    frame2d = frame.reshape(_SAMPLE_HEIGHT, _SAMPLE_WIDTH)
    return region_mean(frame2d, region)


def _sample_chunk_frames(
    stream: IO[bytes] | None,
    chunk_start: float,
    chunk_timestamps: list[float],
    fps_num: int,
    fps_den: int,
    expected_frames: int,
    is_tail_chunk: bool,
    region: CaptureRegion = FULL_FRAME,
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
            brightness = _frame_brightness(frame, region)
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


class _WatchdogState:
    """Shared flag telling the caller whether the deadline watchdog fired (#842).

    ``fired`` is set in the timer thread just before the kill, then read by the
    decode caller so a stalled-then-killed chunk is handled as a decode failure
    (graceful fallback) rather than a hard error.
    """

    __slots__ = ("fired",)

    def __init__(self) -> None:
        self.fired = False


@contextlib.contextmanager
def _proc_deadline_watchdog(proc: subprocess.Popen[bytes], deadline_s: float):
    """Force-kill ``proc`` if it outlives ``deadline_s`` (#842 P2-3).

    The v2 streaming decode reads ``proc.stdout`` via ``_sample_chunk_frames``
    with a blocking ``stream.read`` that never returns while ffmpeg stalls
    (no output, no EOF), so the post-read ``proc.wait(timeout=)`` is never
    reached.  This watchdog kills the process at the deadline; the blocked read
    then sees EOF.  Yields a ``_WatchdogState`` whose ``fired`` flag lets the
    caller route a watchdog-killed (and therefore truncated) decode into its
    decode-failed fallback (CPU: 255.0 / GPU: raise -> CPU fallback) instead of
    propagating the resulting frame-count ``VideoProcessingError`` as a hard
    detection failure (#842 codex).  On a healthy decode the timer is cancelled
    before firing -> no behaviour change (bit-exact).
    """
    state = _WatchdogState()

    def _on_deadline() -> None:
        state.fired = True
        proc.kill()

    timer = threading.Timer(deadline_s, _on_deadline)
    timer.daemon = True
    timer.start()
    try:
        yield state
    finally:
        timer.cancel()


def _resolve_workers(workers: int | None) -> int:
    """Resolve worker count: explicit value or auto-detect."""
    if workers is not None:
        return workers
    return min(os.cpu_count() or 4, 32)


def _resolve_detect_region(
    video_path: Path, duration_hint: float
) -> tuple[CaptureRegion, str | None]:
    """Stage 0: scorebar 帯 anchor を解決する。失敗時は FULL_FRAME (OBS 安全縮退)。

    OBS (全画面 game) では localize がインセット帯を見つけられず consensus が
    成立しないため FULL_FRAME に縮退し、検出は現行と bit-exact になる。VTuber は
    帯 ROI が解決される。anchor の例外は決して検出を壊さない (FULL_FRAME に握り潰す)。

    Returns:
        (region, fallback_reason)。fallback_reason は #810 の縮退 provenance:
        "anchor_error" (例外縮退) / "consensus_miss" (consensus 不成立) /
        None (解決成功)。metadata.json capture_regions.fallback_reason へ記録される。
    """
    from allaganeye.video.capture_region import (
        ScorebarLocalization,
        _BAND_CONSENSUS_MIN_HITS,
        detect_scorebar_band_region,
        localize_from_rgb_bytes,
    )
    from allaganeye.video.probe_state import PresenceState

    unknown_count = 0
    valid_votes = 0  # closure returns that are ScorebarLocalization instances
    total_probes = 0
    unknown_times: list[float] = []

    def _localize_at(t: float):
        nonlocal unknown_count, valid_votes, total_probes
        total_probes += 1
        raw = _probe_frame_rgb_hires(video_path, t)
        if raw is None:
            unknown_count += 1
            unknown_times.append(t)
            logger.debug("anchor probe decode failed at t=%.3fs -> UNKNOWN", t)
            return PresenceState.UNKNOWN
        result = localize_from_rgb_bytes(
            raw,
            height=_SCOREBAR_V2_PROBE_HEIGHT,
            width=_SCOREBAR_V2_PROBE_WIDTH,
        )
        if isinstance(result, ScorebarLocalization):
            valid_votes += 1
        return result

    # Local helper to emit the UNKNOWN-probe warning (dedupes exception + success paths).
    def _warn_unknowns() -> None:
        if unknown_count > 0:
            logger.warning(
                "anchor probes: %d/%d UNKNOWN (probe failure; time range %.1f-%.1fs)",
                unknown_count,
                total_probes,
                min(unknown_times),
                max(unknown_times),
            )

    try:
        region = detect_scorebar_band_region(
            duration=duration_hint,
            probe_w=_SCOREBAR_V2_PROBE_WIDTH,
            probe_h=_SCOREBAR_V2_PROBE_HEIGHT,
            localize_fn=_localize_at,
        )
    except Exception:
        # Anchor failure must never break detect: degrade to FULL_FRAME so the
        # OBS / error path stays bit-exact with the pre-region behavior.
        # R4: 縮退自体は意図的設計だが、silent にせず痕跡を残す (診断性のみ)。
        logger.warning(
            "scorebar band anchor failed; degrading to FULL_FRAME", exc_info=True
        )
        _warn_unknowns()
        return FULL_FRAME, "anchor_error"
    _warn_unknowns()
    if region.is_full_frame():
        # consensus-miss (非例外縮退) も silent にしない (R5): --vtuber 明示 run
        # が FULL_FRAME (汚染 path) で続行することを痕跡に残す。
        logger.warning(
            "band anchor found no scorebar-band consensus "
            "(valid votes %d/%d, min_hits %d); "
            "continuing with FULL_FRAME (--vtuber)",
            valid_votes,
            total_probes,
            _BAND_CONSENSUS_MIN_HITS,
        )
        return region, "consensus_miss"
    logger.debug("band anchor resolved: %s", region)
    return region, None


_MASKED_REGION_SAMPLES = 48
"""Sparse frames sampled across the video for mask-free region detection.

Must span multiple blackouts so game pixels register a dark ``min``; 48 over a
multi-hour FL recording covers many match boundaries (spec section 5).
"""

_MASKED_REGION_DARK = 32
"""Darkest-brightness frames sampled for masked region detection when a Pass-1
brightness hint is available.  These land on the masked blackouts (game region
dark) so ``detect_mask_free_region`` can see game pixels reach a dark min."""

_MASKED_REGION_EVEN = 32
"""Evenly-spaced frames sampled alongside ``_MASKED_REGION_DARK`` (gameplay:
game region bright) so each game pixel is bright in some frame AND dark in
another (#753: even-only sampling missed brief blackouts on shorter recordings)."""


def _resolve_masked_region(
    video_path: Path,
    duration_hint: float,
    workers: int | None,
    *,
    brightness_hint: dict[float, float] | None = None,
) -> CaptureRegion:
    """Detect the mask-free game rectangle for masked recordings (#753).

    Samples grayscale frames and runs ``detect_mask_free_region``.  When a
    ``brightness_hint`` (the standard full-frame Pass-1 ``{timestamp: brightness}``
    map) is provided, samples the ``_MASKED_REGION_DARK`` darkest timestamps (the
    masked blackouts, where the game region goes dark) plus ``_MASKED_REGION_EVEN``
    evenly-spaced timestamps (gameplay, where it is bright) -- both are required
    so each game pixel is bright in some frame AND dark in another.  Without a
    hint, falls back to ``_MASKED_REGION_SAMPLES`` even samples.  Any failure
    (decode, opencv, empty) degrades to FULL_FRAME so the caller can treat
    FULL_FRAME as "no mask region found".  Never raises.
    """
    from allaganeye.video.capture_region import detect_mask_free_region

    try:
        if brightness_hint:
            dark_ts = sorted(brightness_hint, key=lambda t: brightness_hint[t])[
                :_MASKED_REGION_DARK
            ]
            even_ts = [
                duration_hint * (i + 1) / (_MASKED_REGION_EVEN + 1)
                for i in range(_MASKED_REGION_EVEN)
            ]
            times = sorted(set(dark_ts) | set(even_ts))
        else:
            n = _MASKED_REGION_SAMPLES
            times = [duration_hint * (i + 1) / (n + 1) for i in range(n)]
        max_workers = max(1, min(len(times), workers or os.cpu_count() or 4))
        frames: list[np.ndarray] = []
        failed_times: list[float] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(
                pool.map(lambda t: _probe_frame_gray2d(video_path, t), times)
            )
        for t, frame in zip(times, results, strict=True):
            if frame is not None:
                frames.append(frame)
            else:
                failed_times.append(t)
        dropped = len(failed_times)
        if dropped > 0:
            logger.warning(
                "masked region probes: %d/%d failed (decode); "
                "time range %.1f-%.1fs; continuing with valid frames",
                dropped,
                len(times),
                min(failed_times),
                max(failed_times),
            )
        if len(frames) < 2:
            return FULL_FRAME
        return detect_mask_free_region(frames)
    except Exception:
        logger.warning(
            "masked region detection failed; degrading to FULL_FRAME", exc_info=True
        )
        return FULL_FRAME


_ANCHOR_NUM_SAMPLES = 24
"""Number of frames sampled for scorebar anchor consensus (#822).

Spec section 1.1: 24 sparse probes across a multi-hour FL recording cover many
in-match segments so the true scorebar band (conf ~1.00) accumulates enough hits
(>= _ANCHOR_MIN_HITS) while FP samples (conf <= 0.67) are pre-filtered out.
"""

_ANCHOR_MIN_HITS = 5
"""Minimum cluster hits required for scorebar anchor consensus (#822).

Stricter than the vtuber band-region min_hits (2) because anchor consensus feeds
masked classification (per-frame localize_from_rgb_bytes_at_anchor) and a wrong
anchor would corrupt all per-frame decisions for the entire video.
"""

_ANCHOR_MIN_CONF = 0.7
"""Confidence threshold for anchor pre-filter (#822).

Empirical basis (spec section 1.1): true scorebar hits have conf ~1.00;
FP hits (lobby HUD fragments, lower-HUD segments) reach at most conf ~0.67.
A cut at 0.70 admits all true hits and rejects all observed FPs.
Hits below this threshold are treated as miss (not counted toward min_hits);
they do not enter the cluster voting.
"""


def _resolve_scorebar_anchor(
    video_path: Path, duration_hint: float
) -> ScorebarLocalization | None:
    """Resolve a per-video scorebar anchor via multi-frame consensus (#822).

    Probes _ANCHOR_NUM_SAMPLES evenly-spaced frames with _probe_frame_rgb_hires
    and localize_from_rgb_bytes (position-independent).  Hits with
    confidence < _ANCHOR_MIN_CONF are pre-filtered (treated as miss; they do not
    enter cluster voting) to suppress FP bands.  Raw None probes are mapped to
    PresenceState.UNKNOWN (excluded from consensus, not counted as miss).

    Returns None for two distinct reasons:
    - Consensus miss (fewer than _ANCHOR_MIN_HITS confident hits in the dominant
      cluster): the caller (_detect_masked_fallback / Task B4) emits the
      consensus-miss warning and degrades to position-independent localize.
    - Exception: caught here, logged as warning with "falls back to
      position-independent", returns None silently for the caller.

    UNKNOWN-probe partial-failure warning is emitted by this function when
    unknown_count > 0 (same contract as _resolve_detect_region, #824 section 5.3).
    The consensus-miss warning is the caller's responsibility (not emitted here).
    """
    from allaganeye.video.capture_region import (
        consensus_scorebar_localization,
        localize_from_rgb_bytes,
    )
    from allaganeye.video.probe_state import PresenceState

    unknown_count = 0
    total_probes = 0
    unknown_times: list[float] = []

    def _localize_at(t: float):
        nonlocal unknown_count, total_probes
        total_probes += 1
        raw = _probe_frame_rgb_hires(video_path, t)
        if raw is None:
            unknown_count += 1
            unknown_times.append(t)
            logger.debug("anchor probe decode failed at t=%.3fs -> UNKNOWN", t)
            return PresenceState.UNKNOWN
        loc = localize_from_rgb_bytes(
            raw,
            height=_SCOREBAR_V2_PROBE_HEIGHT,
            width=_SCOREBAR_V2_PROBE_WIDTH,
        )
        if loc is not None and loc.confidence < _ANCHOR_MIN_CONF:
            return None  # conf pre-filter: treat as miss, not counted in consensus
        return loc

    # Local helper to emit the UNKNOWN-probe warning (dedupes exception + success paths).
    def _warn_unknowns() -> None:
        if unknown_count > 0:
            logger.warning(
                "anchor probes: %d/%d UNKNOWN (probe failure; time range %.1f-%.1fs)",
                unknown_count,
                total_probes,
                min(unknown_times),
                max(unknown_times),
            )

    try:
        result = consensus_scorebar_localization(
            duration=duration_hint,
            localize_fn=_localize_at,
            num_samples=_ANCHOR_NUM_SAMPLES,
            min_hits=_ANCHOR_MIN_HITS,
        )
    except Exception:
        logger.warning(
            "scorebar anchor resolution failed; masked classification falls back to"
            " position-independent localize",
            exc_info=True,
        )
        _warn_unknowns()
        return None

    _warn_unknowns()
    return result


def detect_match_boundaries(
    video_path: Path,
    *,
    duration_hint: float | None = None,
    sample_interval: float = 1.0,
    blackout_threshold: float = 15.0,
    min_match_duration: float = 300.0,
    min_blackout_duration: float = 3.0,
    use_gpu: bool = False,
    vtuber: bool = False,
    masked: bool = False,
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
    # #821: masked fallback の結果が採用されたとき (明示 --masked / 0-blackout
    # auto-trigger とも) に一度だけ呼ばれる。request flag と resolved path を
    # 分離して記録するための通知 seam (brightness_callback と同型)。
    masked_fallback_callback: Callable[[], None] | None = None,
    # #810: 最終的に有効だった capture region (RegionTimeline) で、Pass 1 の
    # path 確定直後 (masked fallback 採用判定の確定点) に最大 1 回呼ばれる。
    # masked fallback 採用時は mask-free rect、それ以外は Stage 0 の解決結果
    # (band or FULL_FRAME + fallback_reason)。発火後に後段 (Pass 2 / scorebar
    # filtering) が例外を出す run もあるため、callback は値の捕捉のみに使い、
    # 永続化は本関数の成功 return 後に caller (commands 層) が行う
    # (brightness_callback と同型の contract、round-3 R3-3)。
    region_callback: Callable[[RegionTimeline], None] | None = None,
    # #576: rational fps propagation (preferred over float source_fps).
    # Either pair (num+den) takes precedence; float source_fps is the
    # backward-compatible fallback (Fraction.limit_denominator path).
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
    # #805: opt out of the post-match trailing flag (#797). When True the
    # trailing no-scorebar segment is left unflagged (#805 opt-out).
    keep_trailing: bool = False,
) -> list[MatchBoundary]:
    """Detect match boundaries by finding blackout frames.

    Args:
        duration_hint: Video duration in seconds from ffprobe.  Required
            to generate the list of sample timestamps.
        use_gpu: If True, use chunked parallel GPU decode instead of
            per-frame -ss probes.  Falls back to CPU on failure.
        masked: If True (or when standard full-frame Pass 1 finds no
            blackout), re-detect on a mask-free region with position-
            independent classification (#753 masked-OBS).  OBS bit-exact.
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
        keep_trailing: If True, skip the #797 post-match trailing flagging so a
            trailing no-scorebar segment is left unflagged (#805 opt-out).

    Returns list of dicts with 'start' and 'end' keys (seconds).
    """
    if duration_hint is None or duration_hint <= 0:
        raise VideoProcessingError(
            "Cannot determine video duration. Provide duration_hint via probe."
        )

    # Stage 0 (#753 / B4-rev): resolve a scorebar-band anchor before any scan.
    # Stage 0 band anchor runs only when VTuber is explicit (spec section 3.6).
    # OBS (vtuber=False) stays FULL_FRAME -> current bit-exact. localize also
    # succeeds on OBS, so auto-detection is not possible -> the flag gates it.
    detect_region, region_fallback_reason = (
        _resolve_detect_region(video_path, duration_hint)
        if vtuber
        else (FULL_FRAME, None)
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
                region=detect_region,
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
                region=detect_region,
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
            region=detect_region,
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

    # Masked fallback (#753 masked-OBS): when standard full-frame Pass 1 finds no
    # blackout (bright chat-mask overlays hold the average above threshold), OR
    # --masked forces it, re-detect on a mask-free region with position-
    # independent classification.  Gated by `not vtuber and (masked or not
    # blackout_times)`: OBS baselines always have >=1 blackout so `not
    # blackout_times` is False -> the standard path below runs unchanged
    # (bit-exact; spec section 3 / R1).  VTuber uses its own path.
    if not vtuber and (masked or not blackout_times):
        masked_result = _detect_masked_fallback(
            video_path,
            duration_hint=duration_hint,
            sample_interval=sample_interval,
            blackout_threshold=blackout_threshold,
            min_match_duration=min_match_duration,
            min_blackout_duration=min_blackout_duration,
            use_gpu=use_gpu,
            workers=workers,
            src_resolution=src_resolution,
            codec=codec,
            gpu_vendor=gpu_vendor,
            source_fps_num=source_fps_num,
            source_fps_den=source_fps_den,
            source_fps=source_fps,
            audio_hits=audio_hits,
            stats=stats,
            brightness_results=results,
        )
        if masked_result is not None:
            masked_segments, masked_region = masked_result
            if masked_fallback_callback is not None:
                masked_fallback_callback()
            if region_callback is not None:
                # masked path の縮退 (mask 不発見) はここに到達しない (None 返却で
                # 標準 path 続行) ため fallback_reason は常に None。
                region_callback(RegionTimeline(coarse=masked_region))
            return masked_segments

    # #810: この時点で標準 / vtuber path 確定 (masked fallback 不採用)。
    # Pass 1 で実際に使った detect_region + Stage 0 縮退 provenance を通知する。
    if region_callback is not None:
        region_callback(
            RegionTimeline(coarse=detect_region, fallback_reason=region_fallback_reason)
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
        region=detect_region,
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
            band_region=detect_region,
            localize=vtuber,
            audio_hits=audio_hits,
            stats=stats,
            progress_callback=scorebar_progress_callback,
        )
        scorebar_elapsed = time.monotonic() - scorebar_start
        if stats is not None:
            stats["scorebar_elapsed_s"] = scorebar_elapsed

    effective_min = min(min_blackout_duration, _REFINED_MIN_BLACKOUT)
    segments = _filter_and_extract_segments(
        refined_regions,
        duration_hint,
        min_match_duration,
        effective_min,
        classifications=region_classifications,
        stats=stats,
    )
    # #797 / #805: flag a trailing post-match run when its early candidate-match
    # window shows no scorebar at any strided probe point. Skipped for VTuber
    # (vtuber=True): _flag_post_match_trailing probes v2 (absolute coords) which
    # FNs on an inset scorebar and would mis-flag a real VTuber final match
    # (spec section 8.1 P2-d / Codex #1). VTuber trailing is handled in Phase 3.
    if src_resolution is not None and not vtuber and not keep_trailing:
        segments = _flag_post_match_trailing(
            segments,
            video_path,
            duration_hint,
            stats,
            min_match_duration=min_match_duration,
        )
    return segments


def _detect_masked_fallback(
    video_path: Path,
    *,
    duration_hint: float,
    sample_interval: float,
    blackout_threshold: float,
    min_match_duration: float,
    min_blackout_duration: float,
    use_gpu: bool,
    workers: int | None,
    src_resolution: tuple[int, int] | None,
    codec: str | None,
    gpu_vendor: str | None,
    source_fps_num: int | None,
    source_fps_den: int | None,
    source_fps: float | None,
    audio_hits: Sequence[BgmHit] | None,
    stats: DetectionStats | None,
    brightness_results: dict[float, float] | None = None,
) -> tuple[list[MatchBoundary], CaptureRegion] | None:
    """Masked-OBS detection: region-aware Pass 1/2 + localize classification.

    Returns ``(segments, region)``, or ``None`` when no mask-free region is found
    (caller falls through to the standard single-segment result).
    Deliberately duplicates the
    standard Pass1/Pass2/classify sequence (calling the same factored helpers)
    rather than sharing a core, so the standard OBS path is structurally
    unchanged (bit-exact mandate; spec section 3 / R1).  Uses ``band_region=
    FULL_FRAME`` + ``localize=True`` (full-frame position-independent scorebar;
    v2 absolute coords FN on ultrawide, spec section 5).  No trailing flagging:
    ``_flag_post_match_trailing`` probes v2 absolute coords which FN on
    ultrawide (same rationale as the VTuber gate in detect_match_boundaries).
    """
    region = _resolve_masked_region(
        video_path, duration_hint, workers, brightness_hint=brightness_results
    )
    if region.is_full_frame():
        return None  # no mask region found -> defer to the standard result

    if use_gpu:
        from allaganeye.video.gpu_detector import scan_gpu

        try:
            results = scan_gpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                None,
                codec=codec,
                vendor=gpu_vendor,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
                region=region,
            )
        except VideoProcessingError:
            results = _scan_cpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                workers,
                None,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
                region=region,
            )
    else:
        results = _scan_cpu(
            video_path,
            duration_hint,
            sample_interval,
            blackout_threshold,
            workers,
            None,
            source_fps_num=source_fps_num,
            source_fps_den=source_fps_den,
            source_fps=source_fps,
            region=region,
        )

    pass1_blackout_threshold = blackout_threshold + _BLACKOUT_THRESHOLD_UPPER_MARGIN
    blackout_times = sorted(
        t for t, b in results.items() if b < pass1_blackout_threshold
    )
    blackout_regions = _group_blackout_regions(blackout_times, sample_interval)
    blackout_regions = _expand_regions_with_transitions(
        blackout_regions, results, sample_interval, _TRANSITION_THRESHOLD
    )
    if _ENABLE_BORDERLINE_REFINEMENT:
        borderline_regions = _borderline_pseudo_regions(
            results, blackout_threshold, duration_hint
        )
        if borderline_regions:
            blackout_regions = _merge_regions(
                blackout_regions + borderline_regions, sample_interval
            )

    refined_regions = _refine_blackout_regions(
        video_path,
        blackout_regions,
        blackout_threshold,
        duration_hint,
        workers,
        region=region,
    )

    classifications: list[str] | None = None
    if src_resolution is not None:
        # B4 (#822): resolve per-video scorebar anchor for at-anchor classification.
        # Placed inside this guard so anchor consensus probes only run when
        # classification is active (src_resolution provided).
        anchor = _resolve_scorebar_anchor(video_path, duration_hint)
        if anchor is None:
            logger.warning(
                "scorebar anchor unresolved; masked classification falls back to"
                " position-independent localize"
            )

        from allaganeye.video.scorebar import filter_blackouts_with_scorebar

        height = _scaled_height(src_resolution[0], src_resolution[1])
        refined_regions, classifications = filter_blackouts_with_scorebar(
            video_path,
            refined_regions,
            duration_hint,
            height,
            workers,
            band_region=FULL_FRAME,
            localize=True,
            anchor=anchor,
            audio_hits=audio_hits,
            stats=stats,
        )

    effective_min = min(min_blackout_duration, _REFINED_MIN_BLACKOUT)
    segments = _filter_and_extract_segments(
        refined_regions,
        duration_hint,
        min_match_duration,
        effective_min,
        classifications=classifications,
        stats=stats,
    )
    return segments, region


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
    region: CaptureRegion = FULL_FRAME,
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
            region,
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
        region,
    )


def _decode_chunk_cpu_legacy(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    region: CaptureRegion = FULL_FRAME,
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
        results[chunk_timestamps[frame_idx]] = _frame_brightness(frame, region)
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
    region: CaptureRegion = FULL_FRAME,
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
            deadline = max(300, int(chunk_duration * 2))
            watchdog: _WatchdogState | None = None
            try:
                with _proc_deadline_watchdog(proc, deadline) as watchdog:
                    results = _sample_chunk_frames(
                        stream=proc.stdout,
                        chunk_start=chunk_start,
                        chunk_timestamps=chunk_timestamps,
                        fps_num=fps_num,
                        fps_den=fps_den,
                        expected_frames=expected_frames,
                        is_tail_chunk=is_tail_chunk,
                        region=region,
                    )
                    # Defense-in-depth: watchdog covers stream.read stall;
                    # this wait covers proc-exit lag after the stream closes.
                    proc.wait(timeout=deadline)
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
                if watchdog is not None and watchdog.fired:
                    # ffmpeg stalled and the watchdog killed it; the truncated
                    # read tripped the dynamic frame-count guard. Treat as a
                    # decode failure (graceful 255.0 fallback) rather than
                    # failing the whole detect (#842 codex).
                    logger.warning(
                        "CPU chunk v2 decode watchdog fired [%.1f-%.1f]; "
                        "treating as decode failure",
                        chunk_start,
                        chunk_end,
                    )
                    return {t: 255.0 for t in chunk_timestamps}
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
    region: CaptureRegion = FULL_FRAME,
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
                region=region,
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
    if interval <= 0:
        raise ValueError(f"interval must be positive, got {interval}")
    timestamps: list[float] = []
    t = 0.0
    while t < duration:
        timestamps.append(t)
        t += interval
    return timestamps


def _decode_gray_raw(video_path: Path, timestamp: float) -> bytes | None:
    """Decode exactly one 320x180 grayscale frame to raw bytes via ffmpeg -ss.

    Shared by :func:`_probe_single_frame` (brightness) and
    :func:`_probe_frame_gray2d` (2D array).  Returns the first ``_FRAME_SIZE``
    bytes, or ``None`` on timeout / ffmpeg error / short read.  Raises
    ``VideoProcessingError`` only when ffmpeg is missing.
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
        return None
    if result.returncode != 0:
        return None
    if len(result.stdout) < _FRAME_SIZE:
        return None
    return result.stdout[:_FRAME_SIZE]


def _probe_single_frame(
    video_path: Path,
    timestamp: float,
    region: CaptureRegion = FULL_FRAME,
) -> float:
    """Probe a single frame's mean brightness using ffmpeg -ss seek.

    Returns the mean brightness (0-255).  Returns 255.0 on probe failure
    (treated as non-blackout to avoid false positives).  Brightness is computed
    via :func:`_frame_brightness`, so *region* defaults to ``FULL_FRAME`` (the
    1-D ``float(frame.mean())`` path is byte-identical to the pre-region
    behavior; a band region reshapes the raw buffer and crops).
    """
    raw = _decode_gray_raw(video_path, timestamp)
    if raw is None:
        return 255.0
    frame = np.frombuffer(raw, dtype=np.uint8)
    return _frame_brightness(frame, region)


def _probe_frame_gray2d(video_path: Path, timestamp: float) -> np.ndarray | None:
    """Probe one 320x180 grayscale frame as a 2D ``(H, W)`` uint8 array.

    Returns ``None`` on probe failure.  Used by :func:`_resolve_masked_region`
    for static-overlay mask-free region detection (#753 masked-OBS).
    """
    raw = _decode_gray_raw(video_path, timestamp)
    if raw is None:
        return None
    return np.frombuffer(raw, dtype=np.uint8).reshape(_SAMPLE_HEIGHT, _SAMPLE_WIDTH)


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

_SCOREBAR_SCAN_MAX_WIDTH_PX = 1440
"""Maximum detected span (pixels) to accept as scorebar.

1080p OBS scorebar tops out at ~1090 px and 4K Game DVR at ~620 px
(#522).  Post-match content (Limsa exterior, colorful interiors) can
produce a near-full-width saturated band (observed ~1912 px on
obs-20260116 at t=6800/6850), which is not a scorebar.  1440 px (75% of
the 1920 px probe width) clears the real ~1090 px maximum with margin
while rejecting the ~1912 px false positive (#803).
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


def _saturated_column_runs(band: np.ndarray, cv2_module) -> list[tuple[int, int]]:
    """Gap-merged saturated column runs of a (Hb, W, 3) RGB band.

    Shared V2 scorebar geometry core: per-pixel HSV sat/val mask -> per-column
    saturated fraction >= ``_SCOREBAR_SCAN_COL_RATIO`` -> contiguous runs bridged
    across gaps <= ``_SCOREBAR_SCAN_MAX_GAP_PX``.  Returns merged ``(x_left,
    x_right)`` inclusive runs ascending, BEFORE any width-gate / center-straddle
    selection, so ``_find_scorebar_horizontal_range`` and
    ``capture_region._scorebar_saturated_runs`` apply their own post-selection
    on identical input (single source of truth, #842 P2-6).
    """
    bgr = cv2_module.cvtColor(band, cv2_module.COLOR_RGB2BGR)
    hsv = cv2_module.cvtColor(bgr, cv2_module.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    pixel_mask = (sat > _SCOREBAR_SCAN_SAT_THRESHOLD) & (
        val > _SCOREBAR_SCAN_VAL_THRESHOLD
    )
    col_saturated = pixel_mask.mean(axis=0) >= _SCOREBAR_SCAN_COL_RATIO

    width = band.shape[1]
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
        return []

    merged: list[tuple[int, int]] = [raw_runs[0]]
    for start, end in raw_runs[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end - 1 <= _SCOREBAR_SCAN_MAX_GAP_PX:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged


def _emblem_metrics(region: np.ndarray, cv2_module) -> tuple[float, float]:
    """(mean_sat_of_bright_pixels, sobel_edge_density) for one emblem region.

    Shared core of the 3-point emblem AND (#842 P2-6).  ``region`` must be a
    non-empty (h, w, 3) RGB uint8 array.  Bright pixels = HSV value > 30; mean
    saturation over them (0.0 if <= 5 bright pixels).  Edge density = mean Sobel
    magnitude (CV_64F, ksize=3) of the grayscale region.
    """
    bgr = cv2_module.cvtColor(region, cv2_module.COLOR_RGB2BGR)
    hsv = cv2_module.cvtColor(bgr, cv2_module.COLOR_BGR2HSV)
    gray = cv2_module.cvtColor(bgr, cv2_module.COLOR_BGR2GRAY)
    val = hsv[:, :, 2].astype(np.float32)
    sat = hsv[:, :, 1].astype(np.float32)
    bright_mask = val > 30
    if bright_mask.sum() > 5:
        mean_sat = float(sat[bright_mask].mean())
    else:
        mean_sat = 0.0
    sobel_x = cv2_module.Sobel(gray, cv2_module.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2_module.Sobel(gray, cv2_module.CV_64F, 0, 1, ksize=3)
    edge_density = float(np.sqrt(sobel_x**2 + sobel_y**2).mean())
    return mean_sat, edge_density


def _find_scorebar_horizontal_range(raw_rgb: bytes) -> tuple[int, int] | None:
    """Detect horizontal extent [x_left, x_right] of the FL scorebar.

    Scans rows y=``_SCOREBAR_SCAN_Y_START``..``_SCOREBAR_SCAN_Y_END`` of a
    1920x1080 RGB frame, counts columns where at least
    ``_SCOREBAR_SCAN_COL_RATIO`` of rows have HSV saturation
    > ``_SCOREBAR_SCAN_SAT_THRESHOLD`` AND value
    > ``_SCOREBAR_SCAN_VAL_THRESHOLD``.  Contiguous runs of saturated columns
    (bridging gaps up to ``_SCOREBAR_SCAN_MAX_GAP_PX``) are built, and the run
    **straddling screen center** (x = ``_SCOREBAR_V2_PROBE_WIDTH // 2``) becomes
    the scorebar candidate -- the FL scorebar is horizontally centered, and
    keying on the *longest* run instead would let a longer off-center / over-
    wide band mask a valid centered scorebar (#803, Codex PR pre-flight Step 5).

    Returns ``(x_left, x_right)`` with both endpoints inclusive when the
    center-straddling run's width is within
    ``_SCOREBAR_SCAN_MIN_WIDTH_PX``..``_SCOREBAR_SCAN_MAX_WIDTH_PX``.
    Returns ``None`` when:

    - cv2 is not installed (matches V2 "None -> V1 fallback" contract),
    - no saturated run is found (lobby / loading / all-dark frame),
    - no run straddles screen center (only edge-confined bands, e.g. a
      right-side chat panel or left-side widget) (#803),
    - the center run is narrower than the minimum width, or
    - the center run is wider than ``_SCOREBAR_SCAN_MAX_WIDTH_PX`` (#803).
    """
    try:
        import cv2
    except ImportError:
        return None

    width = _SCOREBAR_V2_PROBE_WIDTH
    height = _SCOREBAR_V2_PROBE_HEIGHT
    frame = np.frombuffer(raw_rgb, dtype=np.uint8).reshape(height, width, 3)

    top = frame[_SCOREBAR_SCAN_Y_START:_SCOREBAR_SCAN_Y_END, :, :]
    merged = _saturated_column_runs(top, cv2)
    if not merged:
        return None

    # The FL scorebar is horizontally centered, so the candidate is the run
    # straddling screen center -- NOT merely the longest run.  Selecting the
    # longest first lets a longer off-center / over-wide band (UI widget,
    # colorful post-match interior) mask a valid centered HUD-scaled scorebar
    # and reject the whole frame, false-negativing the 4K / Game DVR layouts
    # the rescue path exists to support (Codex PR pre-flight Step 5, #803).
    # Runs are disjoint, so at most one contains center; pick it, then width-gate.
    center_x = _SCOREBAR_V2_PROBE_WIDTH // 2
    center_run = next((run for run in merged if run[0] <= center_x <= run[1]), None)
    # No run straddles screen center -> only edge-confined bands (e.g. a
    # right-side chat panel at 1410..1919 or a left-side widget at 8..544) ->
    # not a scorebar (#803).
    if center_run is None:
        return None
    span_width = center_run[1] - center_run[0] + 1
    if span_width < _SCOREBAR_SCAN_MIN_WIDTH_PX:
        return None
    # Reject implausibly wide spans (#803): a real FL scorebar tops out at
    # ~1090 px (1080p OBS).  A near-full-width band (e.g. ~1912 px from a
    # colorful post-match interior) is not a scorebar.
    if span_width > _SCOREBAR_SCAN_MAX_WIDTH_PX:
        return None

    return center_run


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
        mean_sat, edge_density = _emblem_metrics(region, cv2_module)
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

_BORDERLINE_SPAN_CAP_FRACTION = 1.5
"""borderline pseudo-region (#576 A5) 合計長の上限 (total_duration 比、#842 P2-4)。

健全な OBS 録画でも brightness 15-55 の borderline frame は多く、実測 (2026-06-24)
で raw_span は duration の 13-50% に達する (5 baseline 実測、最大 obs-20260118: 50.1%)。一方 brightness
15-55 の待機画面が支配的な pathological 録画では raw_frac が ~200% に達し Pass 2
probe が非有界に増える。cap = この値 x total_duration。1.5 は実測最大 50% の 3x
margin で、未検証の長尺/暗め録画も clip せず pathological のみ捕捉する。超過分は
drop + warning、本体 blackout 抽出 (``< blackout_threshold``) は不変。
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

_TRAILING_PROBE_STRIDE = 60.0
"""Seconds between scorebar probes when scanning a trailing segment's early
candidate-match window (#797).

A real match in a mixed trailing sits at the start, right after the opening
blackout, and its HUD stays visible for the whole match (>= several minutes).
Sampling every ``_TRAILING_PROBE_STRIDE`` seconds across the early window
(``start`` .. ``start + min_match_duration``) tolerates a delayed HUD after
long loading -- which a single fixed early offset could miss
(Codex adversarial-review, 2026-05-23) -- while keeping post-match
false-positive exposure low.  Used by ``_flag_post_match_trailing``.
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
    """Build pseudo-regions around Pass 1 borderline frames (A3, #361 + #576 A5).

    A borderline frame sits in ``[blackout_threshold, _TRANSITION_THRESHOLD)``
    -- the full "darker than typical game frames" range, not just super-dark.
    Each borderline timestamp produces a +-``_BORDERLINE_REFINE_RADIUS``
    window so Pass 2 precise sampling probes around it.

    #576 A5 extension: the upper bound was originally
    ``blackout_threshold * 2 = 30`` (catches frames just brighter than blackout
    threshold).  After dual seek (commit a864834) eliminated fps filter PTS
    drift, the legacy "accidental" sub-sample-interval blackout detection
    via drift-induced borderline triggers no longer fires.  Extending the
    upper bound to ``_TRANSITION_THRESHOLD = 55`` (the full transition zone)
    restores coverage of sub-sample-interval blackouts that the new accurate
    sampling otherwise misses (e.g., obs-20260116 t=2175.7-2177.3 boundary
    where sample at t=2178 = brightness 42.6 was previously skipped).
    Pass 2 still uses strict ``< blackout_threshold`` extraction, so the
    only cost is extra Pass 2 probes (no false-positive risk).
    """
    radius = _BORDERLINE_REFINE_RADIUS
    upper = _TRANSITION_THRESHOLD
    regions = [
        (max(0.0, t - radius), min(total_duration, t + radius))
        for t, b in results.items()
        if blackout_threshold <= b < upper
    ]
    # #842 P2-4: total-length cap (fraction of duration). Prevents Pass 2 probe
    # blow-up on recordings where borderline (15-55) wait screens dominate.
    # Accumulate in start order, drop the overflow. Healthy recordings
    # (raw_frac <= 50% measured) never hit the cap -> bit-exact.
    cap_span = _BORDERLINE_SPAN_CAP_FRACTION * total_duration
    regions.sort()
    capped: list[tuple[float, float]] = []
    running = 0.0
    for start, end in regions:
        span = end - start
        if running + span > cap_span:
            logger.warning(
                "borderline pseudo-region 合計長が cap (%.0fs = %.1fx duration) を"
                "超過: %d 領域中 %d を drop (待機画面が支配的な録画の Pass 2 probe "
                "を有界化)。",
                cap_span,
                _BORDERLINE_SPAN_CAP_FRACTION,
                len(regions),
                len(regions) - len(capped),
            )
            break
        capped.append((start, end))
        running += span
    return capped


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
    region: CaptureRegion = FULL_FRAME,
) -> list[tuple[float, float]]:
    """Re-probe blackout regions at fine interval for precise duration.

    For each region, probes +-_REFINE_WINDOW seconds at _REFINE_INTERVAL
    to get an accurate measurement of the blackout duration.  Returns
    updated regions with refined start/end times.

    *progress_callback* fires once before probing with ``(0, total_probes)``
    to publish the total, then once per completed probe with the running
    ``(completed, total)``.  This lets callers drive a progress bar during
    the long ThreadPoolExecutor wait (#366).

    *region* is forwarded to :func:`_probe_single_frame` for per-frame
    brightness.  It defaults to ``FULL_FRAME`` so the OBS Pass 2 path stays
    bit-exact with the pre-region behavior (#753 / Task B2).
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
            pool.submit(_probe_single_frame, video_path, t, region): t
            for t in sorted_probes
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


def _flag_post_match_trailing(
    segments: list[MatchBoundary],
    video_path: Path,
    total_duration: float,
    stats: DetectionStats | None,
    *,
    min_match_duration: float = 300.0,
) -> list[MatchBoundary]:
    """Flag a trailing post-match run via early-window scorebar probes (#797 / #805).

    The final segment, when it runs to end-of-video (``end`` within 1.0s of
    ``total_duration``) with ``type == "unknown"`` (no closing blackout), may
    be post-match content (lobby / city) rather than a match.  It is only
    considered for flagging when it is not the sole segment
    (``len(segments) >= 2``); a lone whole-video unknown -- the fail-open
    fallback when no blackout survives -- has no match to trail and is always
    left untouched, so "no boundaries found" never collapses to zero matches.
    Other shapes rely on the scorebar probes below (a tail showing in-match HUD
    is left as a normal match), so a single real match followed by a post-match
    tail is flagged correctly even though both segments are typed ``unknown``.

    A real match in a *mixed* trailing -- formed when the match-end blackout is
    missed or dropped (e.g. a warp misclassified as ``non_fl`` in scorebar.py)
    so a real match and the post-match tail merge into one segment -- always
    sits at the start, right after the opening blackout.  Scan that early
    candidate-match window (``start`` .. ``start + min_match_duration``,
    clamped to the segment) at ``_TRAILING_PROBE_STRIDE`` intervals **plus the
    window end**, so no stride gap (including the final one) is left unprobed:

    - any probe a scorebar hit (``True``) -> match footage present -> keep
      untouched (normal match)
    - any probe failure / opencv unavailable (``None``) -> keep untouched
      (safe side)
    - every probe a definite miss (``False``) -> post-match -> set
      ``post_match=True`` on the final segment and **retain** it

    #805 段階2: the all-miss disposition is now **non-destructive** -- the
    segment is flagged (``post_match=True``) and kept in ``segments`` rather
    than deleted (``segments[:-1]``).  Downstream the default split flow
    excludes ``post_match`` boundaries from MP4 output while preserving them in
    metadata.json, so a scorebar false-negative can no longer silently delete a
    real match (one match lost, no error -- the failure class this replaces).

    Scanning a strided window (rather than a single fixed early offset) means a
    delayed HUD after long loading cannot hide a real match: a fixed
    ``start + 12s`` probe could land in the loading screen while the midpoint
    and late probes land in a longer post-match tail, mis-flagging a real match
    (Codex adversarial-review, 2026-05-23).
    """
    if not segments:
        return segments
    last = segments[-1]
    if last["type"] != "unknown" or abs(last["end"] - total_duration) >= 1.0:
        return segments
    # Only the lone whole-video unknown fallback -- a single segment spanning
    # the recording, emitted when no blackout survives -- has no match to
    # trail; keep it so "no boundaries found" never collapses to zero matches.
    # Any multi-segment shape still goes through the scorebar probes below,
    # which keep a segment that shows in-match HUD, so a real single match
    # followed by a no-scorebar post-match tail is still flagged.  (Do not also
    # gate on ``segments[-2]`` type: ``_filter_and_extract_segments`` hardcodes
    # the before-first / after-last segments as ``unknown``, so that would
    # wrongly keep single-match tails -- Codex round-5/6 adversarial-review.)
    if len(segments) < 2:
        return segments
    start = last["start"]
    end = last["end"]
    window_end = min(start + min_match_duration, end)
    # Probe the early candidate-match window at a fixed stride, and always
    # include a probe at the window end so the final stride gap is never left
    # unprobed (Codex round-4): a HUD that first appears late in the window
    # (long loading) must still be caught.  The end probe is backed off to
    # ``end - 1.0`` so a ``window_end == end`` case (trailing length ==
    # min_match_duration) does not probe past the last frame -- an EOF read
    # returns None and would (via keep-on-None) suppress a legitimate drop.
    probe_points: list[float] = []
    timestamp = start + _TRAILING_PROBE_STRIDE
    while timestamp < window_end:
        probe_points.append(timestamp)
        timestamp += _TRAILING_PROBE_STRIDE
    probe_points.append(min(window_end, end - 1.0))
    probed = False
    for probe_at in probe_points:
        if probe_at <= start:
            continue
        probed = True
        if _has_scorebar_v2(_probe_frame_rgb_hires(video_path, probe_at)) is not False:
            # Scorebar hit (True) or probe failure (None) -> keep (safe side).
            return segments
    if not probed:
        # No valid probe point inside the segment -> no evidence -> keep.
        return segments
    # Every probe across the candidate match window was a definite miss ->
    # post-match trailing -> flag (non-destructive, #805 段階2).
    if stats is not None:
        drops = stats.setdefault("filter_drops", {})
        drops["post_match_trailing"] = drops.get("post_match_trailing", 0) + 1
        # #805 段階2: the segment now STAYS in ``segments`` (flagged, not
        # dropped), so it is still legitimately counted as unknown -- there is
        # nothing to decrement from ``filter_unknown``.
    # #805 段階2: retain the trailing segment with the non-destructive
    # post_match flag (default split output excludes it) instead of
    # dropping it, so a scorebar false-negative can never silently delete
    # a real match.
    segments[-1]["post_match"] = True
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
