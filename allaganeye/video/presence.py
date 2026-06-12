"""Presence-based match detection (scorebar present/absent as the signal).

Phase 1 of the presence-detection engine (spec
docs/superpowers/specs/2026-05-29-presence-based-detection-engine-design.md).
This module is ADDITIVE and NOT wired into the production detection path;
it exists for the offline validation harness only.  The brightness-based
``detector.detect_match_boundaries`` remains the production detector until
the Phase 3 cutover.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class PresenceSample:
    """One time-grid sample: whether the scorebar is present at ``time``."""

    time: float
    present: bool
    confidence: float


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

    ``samples`` must be sorted by ``time`` ascending.  Returns matches with
    start/end at the first/last present sample time of each surviving run
    (boundary refinement to sub-stride precision happens separately in
    :func:`detect_matches_by_presence`).
    """
    # 1. Build present runs as mutable [start, end] pairs.
    present_runs: list[list[float]] = []
    current: list[float] | None = None
    for s in samples:
        if s.present:
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


def localize_present_at(video_path: Path, timestamp: float) -> PresenceSample:
    """Probe one hi-res frame and report scorebar presence at ``timestamp``.

    Bridges the production frame source (``_probe_frame_rgb_hires``, 1920x1080
    RGB24) and the P1 localizer (``localize_scorebar``).  Probe failure or
    a None localization both yield ``present=False`` (safe absent).
    """
    raw = _probe_frame_rgb_hires(video_path, timestamp)
    loc = localize_from_rgb_bytes(
        raw, height=_SCOREBAR_V2_PROBE_HEIGHT, width=_SCOREBAR_V2_PROBE_WIDTH
    )
    if loc is None:
        return PresenceSample(time=timestamp, present=False, confidence=0.0)
    return PresenceSample(time=timestamp, present=True, confidence=loc.confidence)


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
) -> list[PresenceSample]:
    """Sample scorebar presence across the whole video on a uniform grid.

    ``sample_fn`` maps a timestamp to a :class:`PresenceSample`; it defaults
    to :func:`localize_present_at` bound to ``video_path`` (the production
    path).  Tests inject a synthetic ``sample_fn`` to stay fast.  Results are
    returned sorted by time ascending.
    """

    def _default(t: float) -> PresenceSample:
        return localize_present_at(video_path, t)

    fn = sample_fn if sample_fn is not None else _default

    times = _grid_timestamps(duration, stride)
    results: dict[float, PresenceSample] = {}
    failures: list[VideoProcessingError] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, t): t for t in times}
        for fut in futures:
            t = futures[fut]
            try:
                results[t] = fut.result()
            except VideoProcessingError as e:
                # per-probe 縮退 (PR #823 R3): 同型 pool (_probe_scorebar_context /
                # _refine_blackout_regions) と同じく 1 probe の失敗で全 scan を
                # 落とさず safe absent にする。
                results[t] = PresenceSample(time=t, present=False, confidence=0.0)
                failures.append(e)
    if failures and len(failures) == len(times):
        # 全 probe 失敗は系統故障 (ffmpeg 不在等)。silent な全 absent にせず
        # fail-loud で上流に伝える。
        raise failures[0]
    return [results[t] for t in times]


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
        return localize_present_at(video_path, t).present

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
