"""Split command: orchestrates video probing, detection, and splitting."""

import json
from pathlib import Path

import typer

from allaganeye.config import SplitConfig
from allaganeye.exceptions import AllaganEyeError, DetectionError
from allaganeye.video.detector import detect_match_boundaries
from allaganeye.video.probe import probe_video
from allaganeye.video.splitter import split_video


def run_split(video_path: Path, config: SplitConfig, *, verbose: bool = False) -> None:
    """Run the split pipeline: probe → detect → split."""
    # Step 1: Probe video metadata
    if verbose:
        typer.echo(f"Probing: {video_path}")
    metadata = probe_video(video_path)
    if verbose:
        typer.echo(
            f"  Duration: {metadata['duration']:.1f}s, "
            f"Resolution: {metadata['width']}x{metadata['height']}, "
            f"FPS: {metadata['fps']:.2f}"
        )

    # Auto-adjust sample_interval for long videos (C strategy from #68)
    effective_interval = _auto_sample_interval(
        metadata["duration"], config.sample_interval
    )

    # Step 2: Detect match boundaries
    if verbose:
        if effective_interval != config.sample_interval:
            typer.echo(
                f"  Auto-adjusted sample interval: "
                f"{config.sample_interval}s → {effective_interval}s "
                f"(video is {_format_duration(metadata['duration'])})"
            )
        typer.echo(
            f"Detecting match boundaries "
            f"(interval={effective_interval}s, threshold={config.blackout_threshold})"
        )

        total_duration = metadata["duration"]
        fps = metadata["fps"]
        estimated_frames = int(fps * total_duration)

        with typer.progressbar(length=estimated_frames, label="Detecting") as progress:
            last_pos = [0]

            def on_progress(frame_idx: int, total: int, blackout_count: int) -> None:
                advance = frame_idx - last_pos[0]
                if advance > 0:
                    progress.update(advance)
                last_pos[0] = frame_idx

            boundaries = detect_match_boundaries(
                video_path,
                duration_hint=metadata["duration"],
                sample_interval=effective_interval,
                blackout_threshold=config.blackout_threshold,
                min_match_duration=config.min_match_duration,
                min_blackout_duration=config.min_blackout_duration,
                use_gpu=config.use_gpu,
                progress_callback=on_progress,
            )
    else:
        boundaries = detect_match_boundaries(
            video_path,
            duration_hint=metadata["duration"],
            sample_interval=effective_interval,
            blackout_threshold=config.blackout_threshold,
            min_match_duration=config.min_match_duration,
            min_blackout_duration=config.min_blackout_duration,
            use_gpu=config.use_gpu,
        )

    if not boundaries:
        raise DetectionError(
            "No match boundaries detected. "
            "Try adjusting --blackout-threshold or --min-match-duration."
        )

    # Display detection results with human-readable timestamps
    source_duration = metadata["duration"]
    typer.echo(
        f"Detected {len(boundaries)} match(es) in {video_path.name} "
        f"({_format_timestamp(source_duration)})"
    )
    typer.echo()

    for i, b in enumerate(boundaries, 1):
        dur = b["end"] - b["start"]
        typer.echo(
            f"  Match {i}: {_format_timestamp(b['start']):>7s} - "
            f"{_format_timestamp(b['end']):>7s}  ({_format_duration(dur)})"
        )

    # Show significant gaps (>= 5 minutes)
    gaps = _find_gaps(boundaries, source_duration, min_gap=300.0)
    if gaps:
        typer.echo()
        for gap in gaps:
            typer.echo(
                f"  Gap: {_format_timestamp(gap['start'])} - "
                f"{_format_timestamp(gap['end'])} "
                f"({_format_duration(gap['duration'])})"
            )

    # Step 3: Split (unless dry-run)
    if config.dry_run:
        typer.echo("\nDry run: skipping split")
        return

    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise AllaganEyeError(
            f"Cannot create output directory {config.output_dir}: {e}"
        ) from e

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
    Thresholds chosen so total probes stay under ~3600 (≈ 5 min at 24 workers).
    """
    if configured_interval != 1.0:
        return configured_interval
    if duration > 7200:  # > 2h
        return 3.0
    if duration > 3600:  # > 1h
        return 2.0
    return configured_interval


def _find_gaps(
    boundaries: list[dict], total_duration: float, *, min_gap: float = 300.0
) -> list[dict]:
    """Find significant gaps between detected matches."""
    gaps: list[dict] = []
    for i in range(len(boundaries) - 1):
        gap_start = boundaries[i]["end"]
        gap_end = boundaries[i + 1]["start"]
        gap_dur = gap_end - gap_start
        if gap_dur >= min_gap:
            gaps.append({"start": gap_start, "end": gap_end, "duration": gap_dur})
    return gaps
