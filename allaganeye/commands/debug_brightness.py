"""Debug-brightness command: probe frame brightness and output CSV."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path

import numpy as np
import typer

from allaganeye.video.detector import (
    _SAMPLE_WIDTH,
    _generate_timestamps,
    _probe_frame_rgb,
    _probe_single_frame,
)
from allaganeye.video.probe import probe_video

# Scorebar ROI as ratios of scaled frame dimensions
_SCOREBAR_ROI_X_START = 0.25  # 25% from left
_SCOREBAR_ROI_X_END = 0.75  # 75% from left
_SCOREBAR_ROI_Y_START = 0.0  # top edge
_SCOREBAR_ROI_Y_END = 0.08  # 8% from top


def _scaled_height(src_width: int, src_height: int) -> int:
    """Compute scaled height preserving aspect ratio, rounded to even."""
    h = round(_SAMPLE_WIDTH * src_height / src_width)
    h += h % 2  # round up to even (ffmpeg -2 requirement)
    return h


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

    if roi_mode in ("scorebar", "scorebar-detail"):
        scaled_h = _scaled_height(metadata["width"], metadata["height"])
        if roi_mode == "scorebar-detail":
            _run_scorebar_detail_mode(video_path, timestamps, max_workers, scaled_h)
        else:
            _run_scorebar_mode(video_path, timestamps, max_workers, scaled_h)
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
    video_path: Path, timestamps: list[float], max_workers: int, scaled_h: int
) -> None:
    """RGB probe with scorebar ROI analysis CSV output."""
    results: dict[float, bytes | None] = {}
    probe_fn = partial(_probe_frame_rgb, height=scaled_h)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(probe_fn, video_path, t): t for t in timestamps}
        for future in as_completed(futures):
            t = futures[future]
            results[t] = future.result()

    # Compute ROI pixel bounds from ratios
    x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
    x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
    y1 = int(scaled_h * _SCOREBAR_ROI_Y_START)
    y2 = int(scaled_h * _SCOREBAR_ROI_Y_END)

    typer.echo("timestamp,brightness,roi_r_mean,roi_g_mean,roi_b_mean,roi_brightness")
    for t in sorted(results):
        raw = results[t]
        if raw is None:
            typer.echo(f"{t:.1f},255.0,0.0,0.0,0.0,0.0")
            continue

        frame = np.frombuffer(raw, dtype=np.uint8).reshape(scaled_h, _SAMPLE_WIDTH, 3)
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


def _run_scorebar_detail_mode(
    video_path: Path, timestamps: list[float], max_workers: int, scaled_h: int
) -> None:
    """RGB probe with 3-section ROI analysis for scorebar color detection.

    Splits the scorebar ROI into left/center/right thirds and outputs
    per-section RGB means.  Used to identify 3GC color separation in
    the FL scorebar.
    """
    results: dict[float, bytes | None] = {}
    probe_fn = partial(_probe_frame_rgb, height=scaled_h)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(probe_fn, video_path, t): t for t in timestamps}
        for future in as_completed(futures):
            t = futures[future]
            results[t] = future.result()

    x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
    x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
    y1 = int(scaled_h * _SCOREBAR_ROI_Y_START)
    y2 = int(scaled_h * _SCOREBAR_ROI_Y_END)
    roi_w = x2 - x1
    sec_w = roi_w // 3

    header = (
        "timestamp,roi_brightness,"
        "left_r,left_g,left_b,"
        "center_r,center_g,center_b,"
        "right_r,right_g,right_b"
    )
    typer.echo(header)

    for t in sorted(results):
        raw = results[t]
        if raw is None:
            typer.echo(f"{t:.1f},0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0")
            continue

        frame = np.frombuffer(raw, dtype=np.uint8).reshape(scaled_h, _SAMPLE_WIDTH, 3)
        roi = frame[y1:y2, x1:x2, :]
        roi_brightness = float(roi.mean())

        left = roi[:, :sec_w, :]
        center = roi[:, sec_w : 2 * sec_w, :]
        right = roi[:, 2 * sec_w :, :]

        vals = []
        for section in (left, center, right):
            vals.extend(
                [
                    float(section[:, :, 0].mean()),
                    float(section[:, :, 1].mean()),
                    float(section[:, :, 2].mean()),
                ]
            )

        typer.echo(
            f"{t:.1f},{roi_brightness:.1f}," + ",".join(f"{v:.1f}" for v in vals)
        )
