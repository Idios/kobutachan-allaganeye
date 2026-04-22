"""Detect command: runs detection only and writes ``metadata.json`` (#463).

Splits the historical ``allaganeye split <video>`` pipeline so GUI (#463
data layer) can invoke detection without paying the ffmpeg split cost.

This module deliberately reuses the private helpers in
:mod:`allaganeye.commands.split_matches` (``_run_detection`` etc.) rather
than extracting them a second time -- ``run_split`` already drives them
correctly and we want parity of behaviour, not a fork.  When the shared
module matures further we can hoist those helpers into
``allaganeye.detection`` proper; for now keeping them in
``split_matches`` preserves every regression test that imports them.
"""

from __future__ import annotations

import time
from pathlib import Path

import typer

from allaganeye.commands.split_matches import (
    _auto_sample_interval,
    _build_metadata_payload,
    _display_cache_hit_params,
    _display_gaps,
    _display_results,
    _emit_total_time,
    _find_gaps,
    _format_duration,
    _iso_utc_now,
    _load_cache,
    _print_environment_header,
    _print_detection_stats,
    _resolve_gpu_mode,
    _run_audio_scan,
    _run_detection,
    _save_cache,
)
from allaganeye.config import SplitConfig
from allaganeye.detection.metadata_writer import write_metadata_atomic
from allaganeye.exceptions import DetectionError
from allaganeye.video.detector import DetectionStats
from allaganeye.video.probe import probe_video


def run_detect(
    video_path: Path,
    config: SplitConfig,
    *,
    verbose: bool = False,
    quiet: bool = False,
) -> None:
    """Run detection and write ``metadata.json`` without splitting (#463).

    The ``matches[].output_file`` entries use placeholder names
    (``match_NNN.mp4``) relative to ``config.output_dir`` so that a later
    ``allaganeye split --from-metadata`` produces the same filenames the
    legacy ``allaganeye split <video>`` flow would have used.
    """
    show = not quiet
    total_start = time.monotonic()
    detected_at = _iso_utc_now()

    if verbose and show:
        _print_environment_header(config.output_dir)

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

    effective_interval = _auto_sample_interval(
        metadata["duration"], config.sample_interval
    )

    cache_path = config.output_dir / ".detection_cache.json"
    boundaries = None
    if not config.no_cache:
        boundaries = _load_cache(cache_path, video_path, effective_interval, config)
        if boundaries is not None:
            if show and verbose:
                _display_cache_hit_params(cache_path, config)
            if show:
                _display_results(boundaries, metadata, video_path, verbose, cached=True)

    if boundaries is None:
        use_gpu = _resolve_gpu_mode(
            config.use_gpu, metadata.get("codec"), show, verbose
        )

        if verbose and show and effective_interval != config.sample_interval:
            typer.echo(
                f"  Auto-adjusted sample interval: "
                f"{config.sample_interval}s -> {effective_interval}s "
                f"(video is {_format_duration(metadata['duration'])})"
            )

        audio_hits = _run_audio_scan(video_path, config, show=show, verbose=verbose)

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

        if verbose and show and detect_stats is not None:
            _print_detection_stats(detect_stats)

        if show:
            _display_results(boundaries, metadata, video_path, verbose)

        _save_cache(
            cache_path, video_path, metadata, effective_interval, config, boundaries
        )

    gaps = _find_gaps(boundaries, metadata["duration"], min_gap=300.0)
    if show and verbose and gaps:
        _display_gaps(gaps)

    # Build metadata payload with placeholder output_file names that
    # ``split --from-metadata`` will realise as actual files.
    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        from allaganeye.exceptions import AllaganEyeError

        raise AllaganEyeError(
            f"Cannot create output directory {config.output_dir}: {e}"
        ) from e

    # Placeholder names are relative to ``output_dir``; ``_build_metadata_payload``
    # serialises them via ``Path.as_posix`` so the resulting ``output_file``
    # entries match what ``split --from-metadata`` will produce (just the
    # basename, parent is implicit from the metadata location).
    placeholder_paths = [
        Path(f"match_{i + 1:03d}.mp4") for i, _ in enumerate(boundaries)
    ]

    payload = _build_metadata_payload(
        video_path=video_path,
        source_duration=metadata["duration"],
        detected_at=detected_at,
        effective_interval=effective_interval,
        config=config,
        boundaries=boundaries,
        output_files=placeholder_paths,
        gaps=gaps,
    )
    metadata_path = config.output_dir / "metadata.json"
    write_metadata_atomic(metadata_path, payload)

    if show:
        typer.echo(f"\nMetadata: {metadata_path}")

    _emit_total_time(total_start, verbose, show)
