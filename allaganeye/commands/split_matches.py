"""Split command: orchestrates video probing, detection, and splitting."""

import json
import logging
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

import typer

from allaganeye.audio.matcher import BgmHit
from allaganeye.config import SplitConfig
from allaganeye.exceptions import AllaganEyeError, DetectionError, VideoProcessingError
from allaganeye.video.detector import (
    DetectionStats,
    MatchBoundary,
    detect_match_boundaries,
)
from allaganeye.video.probe import ProbeResult, probe_video
from allaganeye.video.splitter import split_video


class Gap(TypedDict):
    """A significant gap between detected matches."""

    start: float
    end: float
    duration: float


logger = logging.getLogger(__name__)

_CACHE_VERSION = 2


def run_split(
    video_path: Path,
    config: SplitConfig,
    *,
    verbose: bool = False,
    quiet: bool = False,
) -> None:
    """Run the split pipeline: probe -> detect -> split.

    Output levels:
    - Default: probe status, progress bar, match list, output files
    - ``verbose``: adds metadata details, gap info, interval adjustment
    - ``quiet``: suppresses all output except output file list
    """
    show = not quiet

    total_start = time.monotonic()
    detected_at = _iso_utc_now()

    if verbose and show:
        _print_environment_header(config.output_dir)

    # Step 1: Probe video metadata
    if show:
        typer.echo(f"Probing: {video_path.name}")
    metadata = probe_video(video_path)
    if verbose and show:
        typer.echo(
            f"  Duration: {metadata['duration']:.1f}s, "
            f"Resolution: {metadata['width']}x{metadata['height']}, "
            f"FPS: {metadata['fps']:.2f}, "
            f"Codec: {metadata.get('codec', 'unknown')}"
        )

    # Dry-run notice (#331): show early so user knows what mode they're in
    if show and config.dry_run:
        typer.echo("[dry-run] Detect only. Video will not be split.")

    # Auto-adjust sample_interval for long videos (C strategy from #68)
    effective_interval = _auto_sample_interval(
        metadata["duration"], config.sample_interval
    )

    # Check detection cache
    cache_path = config.output_dir / ".detection_cache.json"
    if not config.no_cache:
        cached = _load_cache(cache_path, video_path, effective_interval, config)
        if cached is not None:
            boundaries = cached
            if show:
                _display_results(boundaries, metadata, video_path, verbose, cached=True)
            gaps = _find_gaps(boundaries, metadata["duration"], min_gap=300.0)
            if show and verbose and gaps:
                _display_gaps(gaps)
            if config.dry_run:
                typer.echo("\nDry run: skipping split")
                _emit_total_time(total_start, verbose, show)
                return
            _check_disk_space(
                video_path, boundaries, metadata["duration"], config, show=show
            )
            _split_and_write_metadata(
                video_path,
                boundaries,
                gaps,
                metadata,
                config,
                effective_interval=effective_interval,
                detected_at=detected_at,
                quiet=quiet,
            )
            _emit_total_time(total_start, verbose, show)
            return

    # Resolve GPU/CPU mode: auto-select based on codec when not explicit (#334)
    use_gpu = _resolve_gpu_mode(config.use_gpu, metadata.get("codec"), show, verbose)

    # Step 2: Detect match boundaries
    if verbose and show:
        if effective_interval != config.sample_interval:
            typer.echo(
                f"  Auto-adjusted sample interval: "
                f"{config.sample_interval}s -> {effective_interval}s "
                f"(video is {_format_duration(metadata['duration'])})"
            )

    audio_hits = _run_audio_scan(video_path, config, show=show, verbose=verbose)

    if show and verbose:
        typer.echo(
            f"Detecting match boundaries "
            f"(interval={effective_interval}s, "
            f"threshold={config.blackout_threshold}, "
            f"workers={_workers_summary_str(config.workers)}, "
            f"min_match={config.min_match_duration}s, "
            f"min_blackout={config.min_blackout_duration}s, "
            f"audio={_audio_status_str(config.no_audio)})"
        )

    detect_stats: DetectionStats | None = {} if verbose else None

    boundaries = _run_detection(
        video_path,
        metadata,
        effective_interval,
        config,
        audio_hits=audio_hits,
        quiet=quiet,
        stats=detect_stats,
        use_gpu=use_gpu,
    )

    if not boundaries:
        det_context: dict[str, object] = {
            "audio_hits": len(audio_hits) if audio_hits is not None else "disabled",
        }
        if detect_stats:
            det_context.update(
                {f"stats.{k}": v for k, v in detect_stats.items()}  # type: ignore[misc]
            )
        raise DetectionError(
            "No match boundaries detected. "
            "Try adjusting --blackout-threshold or --min-match-duration.",
            context=det_context,
        )

    # Display pipeline statistics (verbose only)
    if verbose and show and detect_stats is not None:
        _print_detection_stats(detect_stats)

    # Display detection results
    if show:
        _display_results(boundaries, metadata, video_path, verbose)

    # Show significant gaps (verbose only)
    gaps = _find_gaps(boundaries, metadata["duration"], min_gap=300.0)
    if verbose and show and gaps:
        _display_gaps(gaps)

    # Save detection cache
    _save_cache(
        cache_path, video_path, metadata, effective_interval, config, boundaries
    )

    # Step 3: Split (unless dry-run)
    if config.dry_run:
        typer.echo("\nDry run: skipping split")
        _emit_total_time(total_start, verbose, show)
        return

    _check_disk_space(video_path, boundaries, metadata["duration"], config, show=show)
    _split_and_write_metadata(
        video_path,
        boundaries,
        gaps,
        metadata,
        config,
        effective_interval=effective_interval,
        detected_at=detected_at,
        quiet=quiet,
    )
    _emit_total_time(total_start, verbose, show)


def _display_results(
    boundaries: list[MatchBoundary],
    metadata: ProbeResult,
    video_path: Path,
    verbose: bool,
    *,
    cached: bool = False,
) -> None:
    """Display detection results."""
    source_duration = metadata["duration"]
    suffix = " (cached)" if cached else ""
    typer.echo(
        f"Detected {len(boundaries)} match(es) in {video_path.name} "
        f"({_format_timestamp(source_duration)}){suffix}"
    )
    typer.echo()
    for i, b in enumerate(boundaries, 1):
        dur = b["end"] - b["start"]
        # Mark uncertain segments ("unknown" = recording started/ended
        # mid-match) so users can tell them apart from full "fl_match" runs
        # without opening metadata.json (#382). fl_match stays unmarked to
        # avoid noise in the common case.
        type_marker = "  [unknown]" if b.get("type") == "unknown" else ""
        typer.echo(
            f"  Match {i}: {_format_timestamp(b['start']):>7s} - "
            f"{_format_timestamp(b['end']):>7s}  ({_format_duration(dur)})"
            f"{type_marker}"
        )


def _display_gaps(gaps: list[Gap]) -> None:
    """Display significant gaps between matches."""
    typer.echo()
    for gap in gaps:
        typer.echo(
            f"  Gap: {_format_timestamp(gap['start'])} - "
            f"{_format_timestamp(gap['end'])} "
            f"({_format_duration(gap['duration'])})"
        )


def _workers_summary_str(workers: int | None) -> str:
    """Format workers count for verbose summary, resolving ``auto`` (#389).

    When ``config.workers is None`` the CLI delegates to
    ``_resolve_workers`` which picks ``min(cpu_count, 24)``.  Users with
    performance issues need to see the *resolved* number to diagnose
    under-parallelised runs, not just the ``auto`` placeholder.
    """
    if workers is not None:
        return str(workers)

    from allaganeye.video.detector import _resolve_workers

    resolved = _resolve_workers(None)
    return f"auto ({resolved})"


def _audio_status_str(no_audio: bool) -> str:
    """Return audio-scan status string for verbose summary (#384).

    Must stay in sync with ``_run_audio_scan``: if the audio module is
    frozen, the scan is skipped regardless of ``--no-audio``, and the
    verbose summary must reflect that instead of reading ``config.no_audio``
    blindly.
    """
    from allaganeye.audio import AUDIO_FROZEN

    if AUDIO_FROZEN:
        return "frozen"
    return "off" if no_audio else "on"


def _run_audio_scan(
    video_path: Path,
    config: SplitConfig,
    *,
    show: bool,
    verbose: bool,
) -> list[BgmHit] | None:
    """Scan the video for Fanfare peaks, returning hits or None.

    Returns ``None`` when audio promotion is disabled (``--no-audio``),
    when the audio module is frozen (``AUDIO_FROZEN``), or when the scan
    fails for a recoverable reason (missing audio track, ffmpeg error).
    Callers then proceed with scorebar-only filtering.
    """
    from allaganeye.audio import AUDIO_FROZEN

    if AUDIO_FROZEN:
        logger.debug("Audio module frozen (#327) -- skipping Fanfare scan")
        return None

    if config.no_audio:
        return None

    from allaganeye.audio.scan import scan_fanfare_hits

    if show:
        typer.echo("Scanning audio for Fanfare peaks")
    try:
        hits = scan_fanfare_hits(video_path)
    except VideoProcessingError as e:
        if show:
            typer.echo(f"  audio scan skipped: {e}")
        logger.warning("Audio scan failed for %s: %s", video_path, e)
        return None

    if show and verbose:
        typer.echo(f"  {len(hits)} Fanfare peak(s) detected")
    return hits


# Codecs where GPU decode is typically faster than CPU parallel probing.
_GPU_PREFERRED_CODECS = {"h264", "hevc"}


def _resolve_gpu_mode(
    use_gpu: bool | None,
    codec: str | None,
    show: bool,
    verbose: bool,
) -> bool:
    """Resolve GPU/CPU mode from explicit flag or codec auto-detection (#334).

    When *use_gpu* is ``None`` (no ``--gpu``/``--no-gpu`` given), selects
    GPU for H.264/HEVC (mature GPU decode support) and CPU for everything
    else (AV1, VP9, etc.).  Returns a concrete ``bool``.
    """
    if use_gpu is not None:
        return use_gpu

    selected = (codec or "").lower() in _GPU_PREFERRED_CODECS
    if show and verbose:
        mode = "GPU" if selected else "CPU"
        typer.echo(f"  Auto-selected {mode} mode (codec: {codec or 'unknown'})")
    return selected


def _run_detection(
    video_path: Path,
    metadata: ProbeResult,
    effective_interval: float,
    config: SplitConfig,
    *,
    audio_hits: list[BgmHit] | None = None,
    quiet: bool = False,
    stats: DetectionStats | None = None,
    use_gpu: bool = False,
) -> list[MatchBoundary]:
    """Run detection with progress bars for each phase (#328, #329, #331)."""
    detect_kwargs = {
        "duration_hint": metadata["duration"],
        "sample_interval": effective_interval,
        "blackout_threshold": config.blackout_threshold,
        "min_match_duration": config.min_match_duration,
        "min_blackout_duration": config.min_blackout_duration,
        "use_gpu": use_gpu,
        "workers": config.workers,
        "src_resolution": (metadata["width"], metadata["height"]),
        "codec": metadata.get("codec"),
        "audio_hits": audio_hits,
        "stats": stats,
    }

    if not quiet:
        total_duration = metadata["duration"]
        estimated_samples = max(1, int(total_duration / effective_interval))

        # Three-bar progress design (#368 / #393):
        #
        # - Detecting (Pass 1 scan, known length = estimated_samples)
        # - Refining (Pass 2 probes, total published via first callback)
        # - Scorebar (classification, total published via first callback)
        #
        # Each bar is opened with a manual ``__enter__`` and closed with
        # ``__exit__`` *before* the next bar opens so click's ``\r`` rewrite
        # can never overwrite an active bar (that caused Detecting to
        # vanish, #368) and the Pass 2 -> Scorebar transition no longer
        # mixes units (100% -> 99% rollover, #393).  ``try/finally`` guards
        # against exceptions leaving a bar dangling on the TTY.
        detecting_bar = _eta_progressbar(estimated_samples, "Detecting")
        detecting_bar.__enter__()
        detecting_state = {"last_pos": 0, "closed": False}
        refine_state: dict = {"bar": None, "last": 0}
        scorebar_state: dict = {"bar": None, "last": 0}

        def _close_detecting_if_open() -> None:
            """Emit newline after Pass 1 so the next bar starts cleanly."""
            if not detecting_state["closed"]:
                detecting_bar.__exit__(None, None, None)
                detecting_state["closed"] = True

        def _close_refine_if_open() -> None:
            if refine_state["bar"] is not None:
                refine_state["bar"].__exit__(None, None, None)
                refine_state["bar"] = None

        def _close_scorebar_if_open() -> None:
            if scorebar_state["bar"] is not None:
                scorebar_state["bar"].__exit__(None, None, None)
                scorebar_state["bar"] = None

        def on_progress(completed: int, total: int, blackout_count: int) -> None:
            advance = completed - detecting_state["last_pos"]
            if advance > 0:
                detecting_bar.update(advance)
            detecting_state["last_pos"] = completed

        def on_chunk(done: int, total: int, eta_seconds: float) -> None:
            # Update label so users see movement between chunk completions
            # on GPU mode (otherwise the bar stays at 0% then jumps, #333).
            if eta_seconds > 0:
                detecting_bar.label = (
                    f"Detecting [chunk {done}/{total}, "
                    f"ETA ~{_format_eta(eta_seconds)}]".ljust(_PROGRESS_LABEL_WIDTH)
                )
            else:
                detecting_bar.label = f"Detecting [chunk {done}/{total}]".ljust(
                    _PROGRESS_LABEL_WIDTH
                )

        def on_refine(completed: int, total: int) -> None:
            # First Pass 2 callback: close Detecting (emits newline) and
            # open the Refining bar on a fresh line.
            if refine_state["bar"] is None:
                _close_detecting_if_open()
                refine_state["bar"] = _eta_progressbar(total, "Refining")
                refine_state["bar"].__enter__()
                refine_state["last"] = 0
            advance = completed - refine_state["last"]
            if advance > 0:
                refine_state["bar"].update(advance)
            refine_state["last"] = completed

        def on_scorebar(completed: int, total: int) -> None:
            # First scorebar callback: close Refining (or Detecting if
            # Pass 2 had no regions) and open the Scorebar bar fresh.
            if scorebar_state["bar"] is None:
                _close_refine_if_open()
                _close_detecting_if_open()
                scorebar_state["bar"] = _eta_progressbar(total, "Scorebar")
                scorebar_state["bar"].__enter__()
                scorebar_state["last"] = 0
            advance = completed - scorebar_state["last"]
            if advance > 0:
                scorebar_state["bar"].update(advance)
            scorebar_state["last"] = completed

        try:
            result = detect_match_boundaries(
                video_path,
                **detect_kwargs,
                progress_callback=on_progress,
                refine_progress_callback=on_refine,
                scorebar_progress_callback=on_scorebar,
                chunk_progress_callback=on_chunk,
            )
        finally:
            # Close in reverse open-order; if detection raised we still
            # tidy the TTY.
            _close_scorebar_if_open()
            _close_refine_if_open()
            _close_detecting_if_open()

        return result

    return detect_match_boundaries(video_path, **detect_kwargs)


_DISK_SPACE_SAFETY_MARGIN = 1.1
"""Safety margin multiplier for estimated output size (10% overhead)."""

_DISK_SPACE_WARNING_RATIO = 0.8
"""Warn when estimated output exceeds this fraction of free space."""


def _estimate_output_size(
    video_path: Path,
    boundaries: list[MatchBoundary],
    source_duration: float,
) -> int:
    """Estimate total output size in bytes.

    Assumes -c copy produces the same bitrate as input.  Returns
    estimated bytes including a 10% safety margin.
    """
    try:
        source_size = video_path.stat().st_size
    except OSError:
        return 0
    if source_duration <= 0:
        return 0

    total_match_duration = sum(b["end"] - b["start"] for b in boundaries)
    ratio = total_match_duration / source_duration
    return int(source_size * ratio * _DISK_SPACE_SAFETY_MARGIN)


def _format_bytes(n: int) -> str:
    """Format bytes as human-readable string (e.g. '45.2 GB')."""
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    return f"{n / 1024:.1f} KB"


def _check_disk_space(
    video_path: Path,
    boundaries: list[MatchBoundary],
    source_duration: float,
    config: SplitConfig,
    *,
    show: bool = True,
) -> None:
    """Check if output disk has enough space for the split output (#338).

    Raises AllaganEyeError if free space is insufficient.  Shows a warning
    if free space is tight but sufficient.  Skipped when output dir cannot
    be resolved (e.g. network path).
    """
    estimated = _estimate_output_size(video_path, boundaries, source_duration)
    if estimated <= 0:
        return

    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(config.output_dir)
    except OSError:
        logger.debug("Cannot check disk space for %s", config.output_dir)
        return

    free = usage.free

    if estimated > free:
        # Quote the path if it contains spaces
        video_str = str(video_path)
        if " " in video_str:
            video_str = f'"{video_str}"'
        raise AllaganEyeError(
            f"Not enough disk space for split output.\n"
            f"  Estimated output: {_format_bytes(estimated)}\n"
            f"  Free space: {_format_bytes(free)} ({config.output_dir.resolve().drive or config.output_dir})\n"
            f"\n"
            f"Detection results are cached. Free up space and re-run:\n"
            f"  allaganeye split {video_str}"
        )

    if estimated > free * _DISK_SPACE_WARNING_RATIO and show:
        typer.echo(
            f"Warning: free space is tight "
            f"(estimated: {_format_bytes(estimated)}, "
            f"free: {_format_bytes(free)})",
            err=True,
        )


_PROGRESS_LABEL_WIDTH = 11
"""Column width for progress bar labels (Detecting/Refining/Splitting)."""


def _eta_progressbar(length: int, label: str):  # type: ignore[no-untyped-def]
    """Create a progress bar with explicit ETA label (#329).

    Labels are left-justified to ``_PROGRESS_LABEL_WIDTH`` so that
    Detecting / Refining / Splitting bars align vertically.
    """
    import click

    return click.progressbar(
        length=length,
        label=label.ljust(_PROGRESS_LABEL_WIDTH),
        bar_template="%(label)s%(bar)s %(info)s",
        show_eta=True,
        show_percent=True,
    )


def _split_and_write_metadata(
    video_path: Path,
    boundaries: list[MatchBoundary],
    gaps: list[Gap],
    metadata: ProbeResult,
    config: SplitConfig,
    *,
    effective_interval: float,
    detected_at: str,
    quiet: bool = False,
) -> None:
    """Split video and write metadata.json."""
    show = not quiet
    source_duration = metadata["duration"]

    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise AllaganEyeError(
            f"Cannot create output directory {config.output_dir}: {e}"
        ) from e

    # Split with progress bar (#331)
    if show:
        total = len(boundaries)
        with _eta_progressbar(total, "Splitting") as progress:

            def on_split_progress(completed: int, total: int) -> None:
                progress.update(1)

            output_files = split_video(
                video_path,
                boundaries,
                config.output_dir,
                progress_callback=on_split_progress,
            )
    else:
        output_files = split_video(video_path, boundaries, config.output_dir)

    # Write metadata
    result = {
        "source": str(video_path),
        "source_duration": source_duration,
        "source_duration_display": _format_timestamp(source_duration),
        "note": (
            "Split times are approximate due to keyframe-aligned copy mode. "
            "Actual start/end may differ by up to the source keyframe interval "
            "(typically 2s for OBS recordings)."
        ),
        "detected_at": detected_at,
        "detection_params": {
            "sample_interval": effective_interval,
            "blackout_threshold": config.blackout_threshold,
            "min_match_duration": config.min_match_duration,
            "min_blackout_duration": config.min_blackout_duration,
            "no_audio": config.no_audio,
            "use_gpu": config.use_gpu,
            "workers": config.workers,
        },
        "matches": [
            {
                "index": i + 1,
                "start_time": b["start"],
                "end_time": b["end"],
                "start_display": _format_timestamp(b["start"]),
                "end_display": _format_timestamp(b["end"]),
                "duration": b["end"] - b["start"],
                "duration_display": _format_duration(b["end"] - b["start"]),
                "type": b.get("type", "unknown"),
                "output_file": f.as_posix(),
            }
            for i, (b, f) in enumerate(zip(boundaries, output_files, strict=True))
        ],
        "gaps": [
            {
                "start_time": g["start"],
                "end_time": g["end"],
                "start_display": _format_timestamp(g["start"]),
                "end_display": _format_timestamp(g["end"]),
                "duration": g["duration"],
                "duration_display": _format_duration(g["duration"]),
            }
            for g in gaps
        ],
    }
    metadata_path = config.output_dir / "metadata.json"
    try:
        metadata_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as e:
        raise AllaganEyeError(f"Cannot write metadata to {metadata_path}: {e}") from e

    typer.echo(f"\nOutput: {config.output_dir}")
    for f in output_files:
        typer.echo(f"  {f.name}")
    typer.echo(f"Metadata: {metadata_path}")


def _print_environment_header(
    output_dir: Path | None = None,
) -> None:
    """Print environment info header for -v mode (#336 Phase 1 + #377 Phase 2).

    Phase 1 line: allaganeye / ffmpeg / Python / OS (unchanged).
    Phase 2 lines: CPU, GPU, memory, and disk (where the output will be
    written) -- each best-effort, each gracefully degrades to
    ``"(unavailable)"`` without aborting the split.
    """
    import platform

    from allaganeye import __version__
    from allaganeye.system_info import (
        get_cpu_info,
        get_disk_info,
        get_gpu_info,
        get_memory_info,
    )

    ffmpeg_version = _probe_ffmpeg_version()
    typer.echo(
        f"allaganeye {__version__} "
        f"(ffmpeg {ffmpeg_version}, "
        f"Python {platform.python_version()}, "
        f"{platform.system()} {platform.release()})"
    )
    typer.echo(f"  CPU: {get_cpu_info()}")
    typer.echo(f"  GPU: {get_gpu_info()}")
    typer.echo(f"  Memory: {get_memory_info()}")
    disk_target = output_dir if output_dir is not None else Path.cwd()
    typer.echo(f"  Disk: {get_disk_info(disk_target)}")


_FFMPEG_VERSION_RE = re.compile(r"^[nv]?(\d+\.\d+(?:\.\d+)?)")
"""Strip ``n`` / ``v`` / ``git-`` prefixes and build-metadata suffixes from
ffmpeg version strings, keeping only ``major.minor[.patch]`` (#383).

Handles common shapes:
  - ``8.1-full_build-www.gyan.dev``  -> ``8.1``
  - ``n7.1``                          -> ``7.1``
  - ``4.4.2-0ubuntu0.22.04.1``        -> ``4.4.2``
  - ``git-2023-01-01-abcdef``         -> no match, caller keeps raw
"""


def _probe_ffmpeg_version() -> str:
    """Return ffmpeg ``major.minor[.patch]`` version, or '(unknown)' on failure.

    Build-metadata and distributor suffixes (``-full_build-www.gyan.dev``,
    ``-0ubuntu0.22.04.1``, etc.) are stripped so the verbose header stays
    concise (#383).  If the prefix doesn't match the expected numeric
    pattern, the raw token is returned as a fallback.
    """
    import subprocess

    from allaganeye.ffmpeg_path import find_ffmpeg

    try:
        result = subprocess.run(
            [find_ffmpeg(), "-version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "(unknown)"

    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    # "ffmpeg version 8.1-essentials_build-www.gyan.dev Copyright ..."
    parts = first_line.split()
    if len(parts) >= 3 and parts[0] == "ffmpeg" and parts[1] == "version":
        raw = parts[2]
        match = _FFMPEG_VERSION_RE.match(raw)
        return match.group(1) if match else raw
    return "(unknown)"


def _print_detection_stats(stats: DetectionStats) -> None:
    """Emit pipeline statistics in verbose mode (issue #336 Phase 1)."""
    mode = stats.get("mode")
    if mode is not None:
        pass1_samples = stats.get("pass1_samples", 0)
        pass1_blackouts = stats.get("pass1_blackout_frames", 0)
        pass1_elapsed = stats.get("pass1_elapsed_s", 0.0)
        blackout_pct = 100.0 * pass1_blackouts / pass1_samples if pass1_samples else 0.0
        typer.echo(
            f"  Pass 1 ({mode}): {pass1_samples} samples, "
            f"{pass1_blackouts} blackout frames ({blackout_pct:.1f}%), "
            f"{_format_duration(pass1_elapsed)}"
        )

    if "pass2_regions" in stats:
        pass2_elapsed = stats.get("pass2_elapsed_s", 0.0)
        typer.echo(
            f"  Pass 2: {stats['pass2_regions']} regions refined, "
            f"{_format_duration(pass2_elapsed)}"
        )

    if any(
        k in stats
        for k in (
            "scorebar_match_boundary",
            "scorebar_in_match",
            "scorebar_non_fl",
            "scorebar_unknown",
        )
    ):
        parts = [
            f"{stats.get('scorebar_match_boundary', 0)} match_boundary",
            f"{stats.get('scorebar_in_match', 0)} in_match",
            f"{stats.get('scorebar_non_fl', 0)} non_fl",
        ]
        unknown = stats.get("scorebar_unknown", 0)
        if unknown:
            parts.append(f"{unknown} unknown")
        # Append elapsed time when available (#386) for symmetry with
        # Pass 1 / Pass 2.  Gate on presence so tests that don't populate
        # the key still render a clean "X match_boundary, ..." line.
        scorebar_elapsed = stats.get("scorebar_elapsed_s")
        if scorebar_elapsed is not None:
            parts.append(_format_duration(scorebar_elapsed))
        typer.echo(f"  Scorebar: {', '.join(parts)}")

    promotions = stats.get("audio_promotions")
    if promotions is not None and promotions > 0:
        typer.echo(f"  Audio promotion: {promotions} in_match -> match_boundary")

    # Filter drop breakdown (#388): why candidates -> matches shrank.
    # scorebar in_match / non_fl counts stay on the Scorebar line above;
    # this section captures duration-based drops (below_min_match_duration
    # and residual "other") so users can tune --min-match-duration.
    candidates = stats.get("filter_candidates")
    drops = stats.get("filter_drops")
    # Skip the section entirely when there are no real candidates *and*
    # no drops: the match came from the whole-video fallback path, so
    # ``Filter: 0 candidates -> 0 matches`` would be misleading noise.
    if (
        candidates is not None
        and drops is not None
        and (candidates > 0 or sum(drops.values()) > 0)
    ):
        kept = candidates - sum(drops.values())
        typer.echo(f"  Filter: {candidates} candidates -> {kept} matches")
        # Emit only non-zero categories so the output stays terse on
        # healthy runs; zero-row lines would be noise.
        if drops.get("below_min_match_duration", 0) > 0:
            typer.echo(
                f"    {drops['below_min_match_duration']} dropped "
                f"(below min_match_duration)"
            )
        if drops.get("other", 0) > 0:
            typer.echo(f"    {drops['other']} dropped (other)")


def _format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_eta(seconds: float) -> str:
    """Format an ETA for in-label display (compact, e.g. '45s' or '3m20s').

    Designed for the GPU chunk progress label (#333).  Keeps width small
    so the progress bar does not overflow typical terminal widths.
    """
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    m, s = divmod(total, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _format_duration(seconds: float) -> str:
    """Format duration as e.g. '14m02s' or '1h05m'."""
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


def _emit_total_time(total_start: float, verbose: bool, show: bool) -> None:
    """Print ``Total: HH:MM:SS`` wall-clock for the split pipeline (#381).

    Emitted on every verbose-visible exit path (cache hit + split, cache hit
    + dry-run, cache miss + split, cache miss + dry-run) so users always see
    how long the run took regardless of which branch executed.
    """
    if verbose and show:
        typer.echo(f"Total: {_format_duration(time.monotonic() - total_start)}")


def _iso_utc_now() -> str:
    """UTC timestamp in ISO 8601 with 'Z' suffix, e.g. '2026-04-19T12:34:56Z'.

    Used for metadata.json `detected_at` (#370).  Second precision keeps the
    string human-readable without losing practical reproducibility.
    """
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _auto_sample_interval(duration: float, configured_interval: float) -> float:
    """Raise sample interval for long videos to reduce probe count.

    Only adjusts when the configured interval is the default (1.0).
    Thresholds chosen so total probes stay under ~3600 (~5 min at 24 workers).
    """
    if configured_interval != 1.0:
        return configured_interval
    if duration > 7200:  # > 2h
        return 3.0
    if duration > 3600:  # > 1h
        return 2.0
    return configured_interval


def _find_gaps(
    boundaries: list[MatchBoundary], total_duration: float, *, min_gap: float = 300.0
) -> list[Gap]:
    """Find significant gaps between detected matches."""
    gaps: list[Gap] = []
    for i in range(len(boundaries) - 1):
        gap_start = boundaries[i]["end"]
        gap_end = boundaries[i + 1]["start"]
        gap_dur = gap_end - gap_start
        if gap_dur >= min_gap:
            gaps.append({"start": gap_start, "end": gap_end, "duration": gap_dur})
    return gaps


def _save_cache(
    cache_path: Path,
    video_path: Path,
    probe_metadata: ProbeResult,
    effective_interval: float,
    config: SplitConfig,
    boundaries: list[MatchBoundary],
) -> None:
    """Save detection results to cache file."""
    resolved = video_path.resolve()
    try:
        stat = resolved.stat()
    except OSError:
        logger.debug("Cannot stat source file for cache: %s", resolved)
        return
    cache_data = {
        "cache_version": _CACHE_VERSION,
        "source": str(resolved),
        "source_size": stat.st_size,
        "source_mtime": stat.st_mtime,
        "probe": {
            "duration": probe_metadata["duration"],
            "width": probe_metadata["width"],
            "height": probe_metadata["height"],
            "fps": probe_metadata["fps"],
            "codec": probe_metadata.get("codec", ""),
        },
        "params": {
            "sample_interval": effective_interval,
            "blackout_threshold": config.blackout_threshold,
            "min_match_duration": config.min_match_duration,
            "min_blackout_duration": config.min_blackout_duration,
            "no_audio": config.no_audio,
        },
        "boundaries": boundaries,
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        logger.debug("Failed to write detection cache to %s", cache_path)


def _load_cache(
    cache_path: Path,
    video_path: Path,
    effective_interval: float,
    config: SplitConfig,
) -> list[MatchBoundary] | None:
    """Load and validate detection cache. Returns boundaries or None."""
    if not cache_path.is_file():
        return None

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("Detection cache unreadable: %s", cache_path)
        return None

    if data.get("cache_version") != _CACHE_VERSION:
        logger.debug("Cache version mismatch")
        return None

    resolved = video_path.resolve()
    if data.get("source") != str(resolved):
        logger.debug("Cache source path mismatch")
        return None

    try:
        stat = resolved.stat()
    except OSError:
        return None

    if data.get("source_size") != stat.st_size:
        logger.debug("Cache source size mismatch")
        return None

    if data.get("source_mtime") != stat.st_mtime:
        logger.debug("Cache source mtime mismatch")
        return None

    params = data.get("params", {})
    if (
        params.get("sample_interval") != effective_interval
        or params.get("blackout_threshold") != config.blackout_threshold
        or params.get("min_match_duration") != config.min_match_duration
        or params.get("min_blackout_duration") != config.min_blackout_duration
        or params.get("no_audio") != config.no_audio
    ):
        logger.debug("Cache parameter mismatch")
        return None

    boundaries = data.get("boundaries")
    if not isinstance(boundaries, list):
        logger.debug("Cache boundaries invalid")
        return None

    return boundaries
