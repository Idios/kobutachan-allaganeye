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

import sys
import time
from pathlib import Path

import typer

from allaganeye.commands.split_matches import (
    _audio_status_str,
    _auto_sample_interval,
    _build_metadata_payload,
    _build_system_info,
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
    _resolve_gpu_mode_with_probe,
    _run_audio_scan,
    _run_detection,
    _save_cache,
    _workers_summary_str,
    build_brightness_samples,
)
from allaganeye.config import SplitConfig
from allaganeye.detection.metadata_writer import write_metadata_atomic
from allaganeye.detection.progress_emitter import ProgressEmitter
from allaganeye.exceptions import DetectionError
from allaganeye.video.detector import DetectionStats
from allaganeye.video.probe import probe_video


def run_detect(
    video_path: Path,
    config: SplitConfig,
    *,
    verbose: bool = False,
    quiet: bool = False,
    progress_format: str = "text",
) -> None:
    """Run detection and write ``metadata.json`` without splitting (#463).

    The ``matches[].output_file`` entries use placeholder names
    (``match_NNN.mp4``) relative to ``config.output_dir`` so that a later
    ``allaganeye split --from-metadata`` produces the same filenames the
    legacy ``allaganeye split <video>`` flow would have used.

    ``progress_format`` (#569) controls how progress is reported:

    * ``"text"`` (default): the existing click progress bars + typer
      status lines for human consumption.
    * ``"json"``: one JSON object per line on stdout for the Tauri GUI
      wrapper.  Suppresses every other stdout write (``Probing: ...``,
      ``Metadata: ...``, etc.) so the GUI can parse cleanly.  Errors and
      ``-v`` traceback still go to stderr.
    """
    json_mode = progress_format == "json"
    # In json mode the GUI consumes stdout as a structured stream, so we
    # treat every typer.echo call site as if --quiet were set (errors
    # still flow through stderr via the cli.py error handlers).
    show = not quiet and not json_mode
    progress_emitter: ProgressEmitter | None = None
    if json_mode:
        progress_emitter = ProgressEmitter(enabled=True, stream=sys.stdout)
        progress_emitter.emit("start", source=str(video_path))

    captured_brightness: dict[float, float] = {}

    def on_brightness(results: dict[float, float]) -> None:
        # #569 -- single-shot capture: detector calls this once after
        # Pass 1 with the full timestamp/brightness map. We cache it
        # locally so the metadata.json writer can downsample for the
        # complete-screen timeline.
        captured_brightness.update(results)

    total_start = time.monotonic()
    detected_at = _iso_utc_now()

    if verbose and show:
        _print_environment_header(config.output_dir)

    if show:
        typer.echo(f"Probing: {video_path.name}")
    metadata = probe_video(video_path)
    if json_mode and progress_emitter is not None:
        progress_emitter.emit(
            "probing",
            duration_s=metadata["duration"],
            width=metadata["width"],
            height=metadata["height"],
            fps=metadata["fps"],
            codec=metadata.get("codec"),
        )
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
    use_gpu = False
    gpu_vendor: str | None = None
    available_vendors: list[str] = []
    if not config.no_cache:
        boundaries = _load_cache(cache_path, video_path, effective_interval, config)
        if boundaries is not None:
            if show and verbose:
                _display_cache_hit_params(cache_path, config)
            if show:
                _display_results(boundaries, metadata, video_path, verbose, cached=True)
            if json_mode and progress_emitter is not None:
                progress_emitter.emit(
                    "cache_hit",
                    boundaries=len(boundaries),
                )

    if boundaries is None:
        use_gpu, gpu_vendor, available_vendors = _resolve_gpu_mode_with_probe(
            config.use_gpu,
            config.gpu_vendor,
            metadata.get("codec"),
            show,
            verbose,
        )

        if verbose and show and effective_interval != config.sample_interval:
            typer.echo(
                f"  Auto-adjusted sample interval: "
                f"{config.sample_interval}s -> {effective_interval}s "
                f"(video is {_format_duration(metadata['duration'])})"
            )

        audio_hits = _run_audio_scan(video_path, config, show=show, verbose=verbose)

        if show and verbose:
            # run_split の cache-miss summary と同形 (PR #823 R2)。vtuber token
            # は検出 mode の provenance を stdout に残す (cache-hit 側は
            # _display_cache_hit_params が担う)。
            typer.echo(
                f"Detecting match boundaries "
                f"(interval={effective_interval}s, "
                f"threshold={config.blackout_threshold}, "
                f"workers={_workers_summary_str(config.workers)}, "
                f"min_match={config.min_match_duration}s, "
                f"min_blackout={config.min_blackout_duration}s, "
                f"audio={_audio_status_str(config.no_audio)}, "
                f"vtuber={'on' if config.vtuber else 'off'}, "
                f"masked={'on' if config.masked else 'off'})"
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
            gpu_vendor=gpu_vendor,
            progress_emitter=progress_emitter,
            brightness_callback=on_brightness,
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

    # #591 -- cache hit のときは _resolve_gpu_mode を通らないので
    # available_vendors が空 list のまま。GUI export が「現在の環境」を
    # 反映できるように probe し直す。cache miss path では既に
    # _resolve_gpu_mode で probe 済みなのでその値を再利用する。
    if not available_vendors:
        from allaganeye.system_info import probe_gpu_vendors

        available_vendors = probe_gpu_vendors()
    system_info = _build_system_info(
        available_vendors=available_vendors,
        vendor_used=gpu_vendor if use_gpu else None,
    )

    if progress_emitter is not None:
        progress_emitter.emit("writing_metadata")

    brightness_samples = build_brightness_samples(captured_brightness)

    # #586: capture wall-clock end of the detect pipeline immediately
    # before writing metadata.json, so GUI CompleteScreen can compute
    # elapsed = detection_completed_at - detection_started_at without
    # storing a stale duration.
    detection_completed_at = _iso_utc_now()
    payload = _build_metadata_payload(
        video_path=video_path,
        source_duration=metadata["duration"],
        source_fps=metadata["fps"],
        detected_at=detected_at,
        detection_started_at=detected_at,
        detection_completed_at=detection_completed_at,
        effective_interval=effective_interval,
        config=config,
        boundaries=boundaries,
        output_files=placeholder_paths,
        gaps=gaps,
        system_info=system_info,
        brightness_samples=brightness_samples,
    )
    metadata_path = config.output_dir / "metadata.json"
    write_metadata_atomic(metadata_path, payload)

    if show:
        typer.echo(f"\nMetadata: {metadata_path}")

    _emit_total_time(total_start, verbose, show)

    if progress_emitter is not None:
        progress_emitter.emit(
            "done",
            metadata_path=str(metadata_path),
            matches=len(boundaries),
        )
