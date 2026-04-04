"""Split command: orchestrates video probing, detection, and splitting."""

import json
from pathlib import Path

import typer

from allaganeye.config import SplitConfig
from allaganeye.exceptions import DetectionError
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

    # Step 2: Detect match boundaries
    if verbose:
        typer.echo(
            f"Detecting match boundaries "
            f"(interval={config.sample_interval}s, threshold={config.blackout_threshold})"
        )
    boundaries = detect_match_boundaries(
        video_path,
        sample_interval=config.sample_interval,
        blackout_threshold=config.blackout_threshold,
        min_match_duration=config.min_match_duration,
    )

    if not boundaries:
        raise DetectionError(
            "No match boundaries detected. "
            "Try adjusting --blackout-threshold or --min-match-duration."
        )

    typer.echo(f"Detected {len(boundaries)} match(es)")
    for i, b in enumerate(boundaries, 1):
        duration = b["end"] - b["start"]
        if verbose:
            typer.echo(f"  Match {i}: {b['start']:.1f}s - {b['end']:.1f}s ({duration:.0f}s)")

    # Step 3: Split (unless dry-run)
    if config.dry_run:
        typer.echo("Dry run: skipping split")
        return

    config.output_dir.mkdir(parents=True, exist_ok=True)

    output_files = split_video(video_path, boundaries, config.output_dir)

    # Write metadata
    result = {
        "source": str(video_path),
        "source_duration": metadata["duration"],
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
                "duration": b["end"] - b["start"],
                "output_file": str(f),
            }
            for i, (b, f) in enumerate(zip(boundaries, output_files, strict=True))
        ],
    }
    metadata_path = config.output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    typer.echo(f"Output: {config.output_dir}")
    for f in output_files:
        typer.echo(f"  {f.name}")
    typer.echo(f"Metadata: {metadata_path}")
