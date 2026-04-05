"""Debug-brightness command: probe frame brightness and output CSV."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import typer

from allaganeye.video.detector import (
    _SAMPLE_HEIGHT,
    _SAMPLE_WIDTH,
    _generate_timestamps,
    _probe_frame_rgb,
    _probe_single_frame,
)
from allaganeye.video.probe import probe_video

# Scorebar ROI in 320x180 scaled frame (top-center region)
_SCOREBAR_ROI = (80, 0, 240, 15)  # (x1, y1, x2, y2)


def run_debug_brightness(
    video_path: Path,
    *,
    start: float = 0.0,
    end: float | None = None,
    interval: float = 1.0,
    workers: int | None = None,
    roi_mode: str | None = None,
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

    from allaganeye.video.detector import _resolve_workers

    max_workers = _resolve_workers(workers)

    if roi_mode == "scorebar":
        _run_scorebar_mode(video_path, timestamps, max_workers)
    else:
        _run_brightness_mode(video_path, timestamps, max_workers)


def _run_brightness_mode(
    video_path: Path, timestamps: list[float], max_workers: int
) -> None:
    """Original brightness-only CSV output."""
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


def _run_scorebar_mode(
    video_path: Path, timestamps: list[float], max_workers: int
) -> None:
    """RGB probe with scorebar ROI analysis CSV output."""
    results: dict[float, bytes | None] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_probe_frame_rgb, video_path, t): t for t in timestamps}
        for future in as_completed(futures):
            t = futures[future]
            results[t] = future.result()

    x1, y1, x2, y2 = _SCOREBAR_ROI
    typer.echo("timestamp,brightness,roi_r_mean,roi_g_mean,roi_b_mean,roi_brightness")
    for t in sorted(results):
        raw = results[t]
        if raw is None:
            typer.echo(f"{t:.1f},255.0,0.0,0.0,0.0,0.0")
            continue

        frame = np.frombuffer(raw, dtype=np.uint8).reshape(
            _SAMPLE_HEIGHT, _SAMPLE_WIDTH, 3
        )
        brightness = float(frame.mean())
        roi = frame[y1:y2, x1:x2, :]
        roi_r = float(roi[:, :, 0].mean())
        roi_g = float(roi[:, :, 1].mean())
        roi_b = float(roi[:, :, 2].mean())
        roi_brightness = float(roi.mean())
        typer.echo(
            f"{t:.1f},{brightness:.1f},"
            f"{roi_r:.1f},{roi_g:.1f},{roi_b:.1f},{roi_brightness:.1f}"
        )
