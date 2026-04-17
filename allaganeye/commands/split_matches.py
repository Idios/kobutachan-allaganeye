"""Split command: orchestrates video probing, detection, and splitting."""

import json
import logging
from pathlib import Path
from typing import TypedDict

import typer

from allaganeye.audio.matcher import BgmHit
from allaganeye.config import SplitConfig
from allaganeye.exceptions import AllaganEyeError, DetectionError, VideoProcessingError
from allaganeye.video.detector import MatchBoundary, detect_match_boundaries
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

    # Step 1: Probe video metadata
    if show:
        typer.echo(f"Probing: {video_path.name}")
    metadata = probe_video(video_path)
    if verbose and show:
        typer.echo(
            f"  Duration: {metadata['duration']:.1f}s, "
            f"Resolution: {metadata['width']}x{metadata['height']}, "
            f"FPS: {metadata['fps']:.2f}"
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
                return
            return _split_and_write_metadata(
                video_path, boundaries, gaps, metadata, config, quiet=quiet
            )

    # Step 2: Detect match boundaries
    if verbose and show:
        if effective_interval != config.sample_interval:
            typer.echo(
                f"  Auto-adjusted sample interval: "
                f"{config.sample_interval}s -> {effective_interval}s "
                f"(video is {_format_duration(metadata['duration'])})"
            )

    audio_hits = _run_audio_scan(video_path, config, show=show, verbose=verbose)

    boundaries = _run_detection(
        video_path,
        metadata,
        effective_interval,
        config,
        audio_hits=audio_hits,
        quiet=quiet,
    )

    if not boundaries:
        raise DetectionError(
            "No match boundaries detected. "
            "Try adjusting --blackout-threshold or --min-match-duration."
        )

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
        return

    _split_and_write_metadata(
        video_path, boundaries, gaps, metadata, config, quiet=quiet
    )


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
        typer.echo(
            f"  Match {i}: {_format_timestamp(b['start']):>7s} - "
            f"{_format_timestamp(b['end']):>7s}  ({_format_duration(dur)})"
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


def _run_audio_scan(
    video_path: Path,
    config: SplitConfig,
    *,
    show: bool,
    verbose: bool,
) -> list[BgmHit] | None:
    """Scan the video for Fanfare peaks, returning hits or None.

    Returns ``None`` when audio promotion is disabled (``--no-audio``) or
    when the scan fails for a recoverable reason (missing audio track,
    ffmpeg error).  Callers then proceed with scorebar-only filtering.
    """
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


def _run_detection(
    video_path: Path,
    metadata: ProbeResult,
    effective_interval: float,
    config: SplitConfig,
    *,
    audio_hits: list[BgmHit] | None = None,
    quiet: bool = False,
) -> list[MatchBoundary]:
    """Run detection with progress bars for each phase (#328, #329, #331)."""
    detect_kwargs = {
        "duration_hint": metadata["duration"],
        "sample_interval": effective_interval,
        "blackout_threshold": config.blackout_threshold,
        "min_match_duration": config.min_match_duration,
        "min_blackout_duration": config.min_blackout_duration,
        "use_gpu": config.use_gpu,
        "workers": config.workers,
        "src_resolution": (metadata["width"], metadata["height"]),
        "codec": metadata.get("codec"),
        "audio_hits": audio_hits,
    }

    if not quiet:
        total_duration = metadata["duration"]
        estimated_samples = max(1, int(total_duration / effective_interval))

        # Phase 1: Detecting (Pass 1 scan)
        with _eta_progressbar(estimated_samples, "Detecting") as progress:
            last_pos = [0]

            def on_progress(completed: int, total: int, blackout_count: int) -> None:
                advance = completed - last_pos[0]
                if advance > 0:
                    progress.update(advance)
                last_pos[0] = completed

            # Phase 2: Refining (Pass 2 + scorebar), shown inline
            refine_bar_ctx: list = []

            def on_refine(completed: int, total: int) -> None:
                if not refine_bar_ctx:
                    return
                bar = refine_bar_ctx[0]
                advance = completed - bar["last"]
                if advance > 0:
                    bar["progress"].update(advance)
                bar["last"] = completed

            return _run_detection_with_refine_bar(
                video_path,
                detect_kwargs,
                on_progress,
                on_refine,
                refine_bar_ctx,
            )

    return detect_match_boundaries(video_path, **detect_kwargs)


def _run_detection_with_refine_bar(
    video_path: Path,
    detect_kwargs: dict,
    on_progress,
    on_refine,
    refine_bar_ctx: list,
) -> list[MatchBoundary]:
    """Run detection with separate Detecting and Refining progress bars.

    This helper exists to manage the lifecycle of two sequential progress
    bars.  The Detecting bar closes when Pass 1 completes, then the
    Refining bar opens for Pass 2 + scorebar filtering.

    The refine_progress_callback in detect_match_boundaries fires during
    Pass 2 and scorebar classification.  We intercept the first call to
    determine total steps, then drive a second progress bar.
    """
    first_call = [True]
    refine_total = [0]

    def refine_callback(completed: int, total: int) -> None:
        if first_call[0]:
            refine_total[0] = total
            first_call[0] = False
        on_refine(completed, total)

    # Start detection -- the Detecting bar is managed by the caller's
    # context manager.  We pass refine_callback which will accumulate
    # calls; we'll create the Refining bar after detection completes
    # (since we can't nest two typer.progressbar contexts easily).
    #
    # Actually, we need the refine bar to be LIVE during detection.
    # Solution: use a dummy bar that we initialize on first refine callback.
    def lazy_refine_callback(completed: int, total: int) -> None:
        if not refine_bar_ctx:
            # First call -- open the refine bar
            # We can't use typer.progressbar as a context manager here
            # (we're inside detect_match_boundaries), so we use click directly
            import click

            bar = click.progressbar(
                length=total,
                label="Refining ",
                bar_template="%(label)s %(bar)s %(info)s",
                show_eta=True,
                show_percent=True,
            )
            bar.__enter__()
            refine_bar_ctx.append({"progress": bar, "last": 0, "total": total})
        ctx = refine_bar_ctx[0]
        advance = completed - ctx["last"]
        if advance > 0:
            ctx["progress"].update(advance)
        ctx["last"] = completed

    result = detect_match_boundaries(
        video_path,
        **detect_kwargs,
        refine_progress_callback=lazy_refine_callback,
    )

    # Close the refine bar if it was opened
    if refine_bar_ctx:
        refine_bar_ctx[0]["progress"].__exit__(None, None, None)

    return result


def _eta_progressbar(length: int, label: str):  # type: ignore[no-untyped-def]
    """Create a progress bar with explicit ETA label (#329).

    Returns a context manager (click ProgressBar) with a bar_template
    that clearly labels the time display as ETA.
    """
    import click

    return click.progressbar(
        length=length,
        label=label + "  ",
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
                "output_file": str(f),
            }
            for i, (b, f) in enumerate(zip(boundaries, output_files, strict=True))
        ],
        "gaps": [
            {
                "start_display": _format_timestamp(g["start"]),
                "end_display": _format_timestamp(g["end"]),
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


def _format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_duration(seconds: float) -> str:
    """Format duration as e.g. '14m02s' or '1h05m'."""
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


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
