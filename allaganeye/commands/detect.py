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
from typing import cast

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
    _format_region_token,
    _iso_utc_now,
    _load_cache,
    _partition_post_match,
    _read_cached_capture_regions,
    _read_cached_masked_fallback,
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
from allaganeye.detection.warnings import build_warnings
from allaganeye.exceptions import DetectionError
from allaganeye.metadata_types import CaptureRegions
from allaganeye.video.capture_region import RegionTimeline
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
    # #821 -- resolved masked fallback。cache-hit は cache 記録値を引き継ぎ、
    # cache-miss は detection callback で捕捉する。
    masked_fallback_used = False
    # #810 -- capture region timeline。cache-hit は cache 記録値を引き継ぎ、
    # cache-miss は detection callback で捕捉する。
    captured_region: CaptureRegions | None = None
    use_gpu = False
    gpu_vendor: str | None = None
    available_vendors: list[str] = []
    if not config.no_cache:
        boundaries = _load_cache(cache_path, video_path, effective_interval, config)
        if boundaries is not None:
            masked_fallback_used = _read_cached_masked_fallback(cache_path)
            captured_region = _read_cached_capture_regions(cache_path)
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

        def _on_masked_fallback() -> None:
            nonlocal masked_fallback_used
            masked_fallback_used = True

        def _on_region(timeline: RegionTimeline) -> None:
            nonlocal captured_region
            captured_region = cast("CaptureRegions", timeline.to_dict())

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
            masked_fallback_callback=_on_masked_fallback,
            region_callback=_on_region,
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
            if captured_region is not None:
                typer.echo(f"  Region: {_format_region_token(captured_region)}")

        if show:
            _display_results(boundaries, metadata, video_path, verbose)

        _save_cache(
            cache_path,
            video_path,
            metadata,
            effective_interval,
            config,
            boundaries,
            masked_fallback_used=masked_fallback_used,
            capture_regions=captured_region,
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

    # #805 段階2: active (MP4 生成対象) と post_match (flag 方式、MP4 不生成) に
    # 分離する。detector の `_flag_post_match_trailing` が最終 segment に
    # post_match=True を立てた場合、それを output_file 無しの post_match Match
    # として metadata に搬送する (`_split_and_write_metadata` と同形)。
    # post_match が無い場合 (常態) は active == boundaries で従来と bit-exact。
    active_boundaries, post_match_boundaries = _partition_post_match(boundaries)

    # Placeholder names are relative to ``output_dir``; ``_build_metadata_payload``
    # serialises them via ``Path.as_posix`` so the resulting ``output_file``
    # entries match what ``split --from-metadata`` will produce (just the
    # basename, parent is implicit from the metadata location). active のみに
    # placeholder を割り当てる (post_match は MP4 を生成しないため output_file 無し)。
    placeholder_paths = [
        Path(f"match_{i + 1:03d}.mp4") for i, _ in enumerate(active_boundaries)
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
        boundaries=active_boundaries,
        post_match_boundaries=post_match_boundaries,
        output_files=placeholder_paths,
        gaps=gaps,
        system_info=system_info,
        brightness_samples=brightness_samples,
        masked_fallback_used=masked_fallback_used,
        # #805 段階2: warnings is always empty -- the W1
        # post_match_trailing_dropped emission was removed; the non-destructive
        # post_match flag on the Match now records a post-match trailing segment.
        # post_match segment は post_match_boundaries 経由で output_file 無しの
        # Match として書かれる (`_split_and_write_metadata` と同じ partition)。
        warnings=build_warnings(),
        capture_regions=captured_region,
    )
    metadata_path = config.output_dir / "metadata.json"
    write_metadata_atomic(metadata_path, payload)

    if show:
        typer.echo(f"\nMetadata: {metadata_path}")

    _emit_total_time(total_start, verbose, show)

    if progress_emitter is not None:
        progress_emitter.emit(
            "done",
            # #805 段階2: total detected segments (active + post_match)。post_match
            # は MP4 化されないが「検出された試合数」の観測値としては数える
            # (post_match が無い常態では active と一致 = 従来挙動)。
            metadata_path=str(metadata_path),
            matches=len(boundaries),
        )
