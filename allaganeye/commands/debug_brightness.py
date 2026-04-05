"""Debug-brightness command: probe frame brightness and output CSV."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import typer

from allaganeye.video.detector import _generate_timestamps, _probe_single_frame
from allaganeye.video.probe import probe_video


def run_debug_brightness(
    video_path: Path,
    *,
    start: float = 0.0,
    end: float | None = None,
    interval: float = 1.0,
) -> None:
    """Probe brightness at regular intervals and print CSV to stdout."""
    metadata = probe_video(video_path)
    duration: float = metadata["duration"]

    if end is None:
        end = duration
    else:
        end = min(end, duration)

    if start >= end:
        typer.echo("Error: --start must be less than --end", err=True)
        raise typer.Exit(code=1)

    timestamps = _generate_timestamps(end - start, interval)
    timestamps = [start + t for t in timestamps]

    if not timestamps:
        typer.echo("No timestamps to probe.", err=True)
        raise typer.Exit(code=1)

    max_workers = min(os.cpu_count() or 4, 24)
    results: dict[float, float] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_single_frame, video_path, t): t for t in timestamps
        }
        for future in as_completed(futures):
            t = futures[future]
            results[t] = future.result()

    typer.echo("timestamp,brightness")
    for t in sorted(results):
        typer.echo(f"{t:.1f},{results[t]:.1f}")
