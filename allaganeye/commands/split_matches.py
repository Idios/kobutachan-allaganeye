"""Split command: orchestrates video probing, detection, and splitting."""

import json
from pathlib import Path

import typer

from allaganeye.config import SplitConfig
from allaganeye.exceptions import AllaganEyeError, DetectionError
from allaganeye.video.detector import BrightnessStats, detect_match_boundaries
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

    # Step 2: Detect match boundaries
    collect_stats = verbose and config.dry_run
    if verbose:
        typer.echo(
            f"Detecting match boundaries "
            f"(interval={config.sample_interval}s, threshold={config.blackout_threshold})"
        )

    brightness_stats: BrightnessStats | None = None
    if collect_stats:
        result_tuple = detect_match_boundaries(
            video_path,
            sample_interval=config.sample_interval,
            blackout_threshold=config.blackout_threshold,
            min_match_duration=config.min_match_duration,
            collect_brightness=True,
        )
        assert isinstance(result_tuple, tuple)
        boundaries, brightness_stats = result_tuple
    else:
        result_detect = detect_match_boundaries(
            video_path,
            sample_interval=config.sample_interval,
            blackout_threshold=config.blackout_threshold,
            min_match_duration=config.min_match_duration,
        )
        assert isinstance(result_detect, list)
        boundaries = result_detect

    if not boundaries:
        raise DetectionError(
            "No match boundaries detected. "
            "Try adjusting --blackout-threshold or --min-match-duration."
        )

    typer.echo(f"Detected {len(boundaries)} match(es)")
    for i, b in enumerate(boundaries, 1):
        duration = b["end"] - b["start"]
        if verbose:
            typer.echo(
                f"  Match {i}: {b['start']:.1f}s - {b['end']:.1f}s ({duration:.0f}s)"
            )

    # Step 3: Split (unless dry-run)
    if config.dry_run:
        if brightness_stats is not None:
            _print_brightness_stats(brightness_stats, config.blackout_threshold)
        typer.echo("Dry run: skipping split")
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
        "source_duration": metadata["duration"],
        "matches": [
            {
                "index": i + 1,
                "start_time": b["start"],
                "end_time": b["end"],
                "duration": b["end"] - b["start"],
                "output_file": str(f),
            }
            for i, (b, f) in enumerate(zip(boundaries, output_files, strict=True))
        ],
    }
    metadata_path = config.output_dir / "metadata.json"
    try:
        metadata_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as e:
        raise AllaganEyeError(f"Cannot write metadata to {metadata_path}: {e}") from e

    typer.echo(f"Output: {config.output_dir}")
    for f in output_files:
        typer.echo(f"  {f.name}")
    typer.echo(f"Metadata: {metadata_path}")


def _print_brightness_stats(stats: BrightnessStats, threshold: float) -> None:
    """Print brightness statistics for threshold tuning."""
    typer.echo("Brightness statistics:")
    typer.echo(
        f"  Samples: {len(stats.samples)}, "
        f"Min: {stats.min_brightness:.1f}, "
        f"Max: {stats.max_brightness:.1f}, "
        f"Mean: {stats.mean_brightness:.1f}"
    )
    near = stats.near_threshold(threshold)
    typer.echo(f"  Near threshold ({threshold:.1f} +/- 10): {len(near)} frame(s)")
    for t, b in near[:10]:
        typer.echo(f"    {t:.1f}s: brightness={b:.1f}")
    if len(near) > 10:
        typer.echo(f"    ... and {len(near) - 10} more")
