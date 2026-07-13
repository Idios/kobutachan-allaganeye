"""Presence-based match detection (scorebar present/absent as the signal).

Phase 1 of the presence-detection engine (spec
docs/superpowers/specs/2026-05-29-presence-based-detection-engine-design.md).
This module is ADDITIVE and NOT wired into the production detection path;
it exists for the offline validation harness only.  The brightness-based
``detector.detect_match_boundaries`` remains the production detector until
the Phase 4 cutover (two-signal rearchitecture spec
docs/superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md
section 8; supersedes the older "Phase 3 cutover" numbering).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.capture_region import localize_from_rgb_bytes
from allaganeye.video.detector import (
    _SCOREBAR_V2_PROBE_HEIGHT,
    _SCOREBAR_V2_PROBE_WIDTH,
    _probe_frame_rgb_hires,
)
from allaganeye.video.probe_state import PresenceSample, PresenceState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PresenceMatch:
    """A detected FL match segment in seconds (presence-based)."""

    start: float
    end: float


def segment_presence(
    samples: Sequence[PresenceSample],
    *,
    t_gap: float,
    t_min_match: float,
) -> list[PresenceMatch]:
    """Collapse present/absent samples into match segments.

    Two-directional debounce:
    - absent gaps shorter than ``t_gap`` between two present runs are
      absorbed (treated as in-match: covers mid-match scorebar loss such
      as death blackout / full-screen UI).
    - present runs shorter than ``t_min_match`` are discarded (transient
      false positives).

    UNKNOWN samples do not contribute to a present run (same behaviour as
    ABSENT: breaks the current run).  The explicit ``state is
    PresenceState.PRESENT`` comparison makes the folding visible to grep.

    ``samples`` must be sorted by ``time`` ascending.  Returns matches with
    start/end at the first/last present sample time of each surviving run
    (boundary refinement to sub-stride precision happens separately in
    :func:`detect_matches_by_presence`).
    """
    # 1. Build present runs as mutable [start, end] pairs.
    present_runs: list[list[float]] = []
    current: list[float] | None = None
    for s in samples:
        if s.state is PresenceState.PRESENT:
            if current is None:
                current = [s.time, s.time]
            else:
                current[1] = s.time
        else:
            if current is not None:
                present_runs.append(current)
                current = None
    if current is not None:
        present_runs.append(current)

    # 2. Merge runs whose inter-run gap is shorter than t_gap.
    merged: list[list[float]] = []
    for run in present_runs:
        if merged and run[0] - merged[-1][1] < t_gap:
            merged[-1][1] = run[1]
        else:
            merged.append(list(run))

    # 3. Drop runs shorter than t_min_match; emit matches.
    return [
        PresenceMatch(start=r[0], end=r[1])
        for r in merged
        if r[1] - r[0] >= t_min_match
    ]


def refine_boundary(
    t_true: float,
    t_false: float,
    present_at: Callable[[float], bool],
    *,
    tol: float,
) -> float:
    """Binary-search the present<->absent transition between two times.

    Precondition: ``present_at(t_true)`` is True and ``present_at(t_false)``
    is False.  ``t_true`` and ``t_false`` may be in either order (forward =
    match end, backward = match start).  Returns the midpoint of the final
    bracket, accurate to within ``tol`` seconds.
    """
    lo_true = t_true
    hi_false = t_false
    while abs(lo_true - hi_false) > tol:
        mid = (lo_true + hi_false) / 2.0
        if present_at(mid):
            lo_true = mid
        else:
            hi_false = mid
    return (lo_true + hi_false) / 2.0


def _probe_present_sample_raising(video_path: Path, timestamp: float) -> PresenceSample:
    """scan_presence default sampler variant: raises VideoProcessingError on decode error.

    raw None (decode 失敗) -> UNKNOWN (debug log) / decode 成功 + localizer miss ->
    ABSENT / hit -> PRESENT。VideoProcessingError は raise のまま caller に渡す。
    これにより scan_presence の per-probe except が first_exc を捕捉でき、系統故障
    (ffmpeg 不在等) の代表原因を fail-loud まで保全する (codex finding sec.5.2)。
    外部契約は localize_present_at (例外を漏らさない) を使うこと。
    """
    raw = _probe_frame_rgb_hires(
        video_path, timestamp
    )  # may raise VideoProcessingError
    if raw is None:
        logger.debug("presence probe decode failed at t=%.3fs -> UNKNOWN", timestamp)
        return PresenceSample(
            time=timestamp, state=PresenceState.UNKNOWN, confidence=0.0
        )
    loc = localize_from_rgb_bytes(
        raw, height=_SCOREBAR_V2_PROBE_HEIGHT, width=_SCOREBAR_V2_PROBE_WIDTH
    )
    if loc is None:
        return PresenceSample(
            time=timestamp, state=PresenceState.ABSENT, confidence=0.0
        )
    return PresenceSample(
        time=timestamp, state=PresenceState.PRESENT, confidence=loc.confidence
    )


def localize_present_at(video_path: Path, timestamp: float) -> PresenceSample:
    """Probe one hi-res frame and report scorebar presence (tri-state, #824).

    raw None (decode 失敗) -> UNKNOWN (debug log) / decode 成功 + localizer miss
    -> ABSENT / hit -> PRESENT。decode 例外は caller に漏らさない (#824 sec.5.2)。
    VideoProcessingError も raw None と同様 UNKNOWN に写像する。
    Thin delegation to _probe_present_sample_raising with exception-catch wrapper.
    """
    try:
        return _probe_present_sample_raising(video_path, timestamp)
    except VideoProcessingError:
        logger.debug(
            "presence probe VideoProcessingError at t=%.3fs -> UNKNOWN", timestamp
        )
        return PresenceSample(
            time=timestamp, state=PresenceState.UNKNOWN, confidence=0.0
        )


def _grid_timestamps(duration: float, stride: float) -> list[float]:
    """Inclusive 0..duration grid at ``stride`` spacing (duration endpoint kept)."""
    if stride <= 0:
        raise ValueError("stride must be > 0")
    n = int(duration // stride)
    times = [round(i * stride, 6) for i in range(n + 1)]
    if not times or times[-1] < duration:
        times.append(round(duration, 6))
    return times


def scan_presence(
    video_path: Path,
    duration: float,
    *,
    stride: float,
    workers: int,
    sample_fn: Callable[[float], PresenceSample] | None = None,
    times: Sequence[float] | None = None,
) -> list[PresenceSample]:
    """Sample scorebar presence across the whole video on a uniform grid.

    ``sample_fn`` maps a timestamp to a :class:`PresenceSample`; it defaults
    to :func:`_probe_present_sample_raising` bound to ``video_path`` (the
    production path -- the raising variant, so the per-probe except below
    captures the representative cause for the all-UNKNOWN fail-loud.
    External callers keep the no-leak :func:`localize_present_at`).  Tests
    inject a synthetic ``sample_fn`` to stay fast.  Results are returned
    sorted by time ascending.

    When ``times`` is provided the probes are performed at exactly those
    timestamps in the given order rather than on the uniform stride grid.
    ``duration`` and ``stride`` are not used for timestamp generation when
    ``times`` is set (pass any placeholder values; ``duration`` is ignored,
    ``stride`` is kept as a required kwarg for API stability).  Existing
    callers that do not pass ``times`` are unaffected.

    Per-probe exceptions are mapped to UNKNOWN samples (per-probe isolation,
    #824 sec.5.2).  If ALL samples are UNKNOWN a VideoProcessingError is raised
    (fail-loud: systemic probe failure).  If some are UNKNOWN a single warning
    is emitted with the count and time range.
    """
    fn = (
        sample_fn
        if sample_fn is not None
        else (lambda t: _probe_present_sample_raising(video_path, t))
    )

    if times is not None:
        times_list = list(times)
    else:
        times_list = _grid_timestamps(duration, stride)
    results: dict[float, PresenceSample] = {}
    first_exc: VideoProcessingError | None = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, t): t for t in times_list}
        for fut in futures:
            t = futures[fut]
            try:
                results[t] = fut.result()
            except VideoProcessingError as exc:
                # 単発 probe の例外も UNKNOWN に写像 (per-probe 隔離、#824 sec.5.2)
                results[t] = PresenceSample(
                    time=t, state=PresenceState.UNKNOWN, confidence=0.0
                )
                if first_exc is None:
                    first_exc = exc
    unknown = [t for t in times_list if results[t].state is PresenceState.UNKNOWN]
    if unknown:
        if len(unknown) == len(times_list):
            # Determine representative cause: prefer the caught exception message;
            # fall back to marker string when the default sampler returned UNKNOWN
            # (_probe_present_sample_raising maps raw None -> UNKNOWN without
            # raising; only decode exceptions raise into the except above).
            if first_exc is not None:
                cause: str | VideoProcessingError = first_exc
            else:
                cause = "decode returned no frame"
            raise VideoProcessingError(
                f"all {len(times_list)} presence probes UNKNOWN "
                f"(systemic probe failure): {cause}"
            ) from (first_exc if first_exc is not None else None)
        logger.warning(
            "%d/%d presence probes UNKNOWN (probe failure); "
            "treated as non-present in segmentation (time range %.1f-%.1fs)",
            len(unknown),
            len(times_list),
            min(unknown),
            max(unknown),
        )
    return [results[t] for t in times_list]


def detect_matches_by_presence(
    video_path: Path,
    duration: float,
    *,
    stride: float,
    t_gap: float,
    t_min_match: float,
    tol: float,
    workers: int,
) -> list[PresenceMatch]:
    """Top-level presence detector: scan -> segment -> refine boundaries.

    1. ``scan_presence`` samples the whole video on a ``stride`` grid.
    2. ``segment_presence`` debounces and yields coarse matches (boundaries
       at sample times).
    3. each coarse boundary is refined within a one-stride bracket using
       ``refine_boundary``.  Matches touching the video edges (t<=0 or
       t>=duration within one stride) keep the edge unrefined.
    """
    samples = scan_presence(video_path, duration, stride=stride, workers=workers)
    coarse = segment_presence(samples, t_gap=t_gap, t_min_match=t_min_match)

    def present_at(t: float) -> bool:
        sample = localize_present_at(video_path, t)
        if sample.state is PresenceState.UNKNOWN:
            logger.warning(
                "presence probe UNKNOWN during boundary refine at t=%.3fs; "
                "treating as absent",
                t,
            )
            return False
        return sample.state is PresenceState.PRESENT

    refined: list[PresenceMatch] = []
    for m in coarse:
        if m.start - stride < 0.0:
            start = 0.0
        else:
            start = refine_boundary(m.start, m.start - stride, present_at, tol=tol)
        if m.end + stride > duration:
            end = duration
        else:
            end = refine_boundary(m.end, m.end + stride, present_at, tol=tol)
        refined.append(PresenceMatch(start=start, end=end))
    return refined
