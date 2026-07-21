"""Split command: orchestrates video probing, detection, and splitting."""

import json
import logging
import math
import re
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast

import typer
from click._termui_impl import ProgressBar as _ClickProgressBar  # subclass 用 (#365)

from allaganeye.audio.matcher import BgmHit
from allaganeye.config import SplitConfig
from allaganeye.detection.format import (
    format_duration as _format_duration,
    format_timestamp as _format_timestamp,
    iso_utc_now as _iso_utc_now,
)
from allaganeye.detection.metadata_writer import (
    read_metadata,
    write_metadata_atomic,
)
from allaganeye.detection.progress_emitter import ProgressEmitter
from allaganeye.detection.warnings import build_warnings, sanitize_warnings
from allaganeye.exceptions import (
    AllaganEyeError,
    DetectionError,
    InputFileError,
    VideoProcessingError,
)
from allaganeye.metadata_types import (
    BrightnessSamples,
    CaptureRegions,
    Match,
    Metadata,
    MetadataWarning,
    SystemInfo,
)
from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline
from allaganeye.video.detector import (
    DetectionStats,
    MatchBoundary,
    detect_match_boundaries,
)
from allaganeye.video.probe import ProbeResult, probe_video
from allaganeye.video.splitter import split_video


class Gap(TypedDict):
    """A significant gap between detected matches."""

    start: float
    end: float
    duration: float


logger = logging.getLogger(__name__)

# v3 (#821): masked auto-fallback (flag なしでも 0-blackout で発火) の導入で
# 「missing masked = 標準 path と同一挙動」が成立しなくなったため、pre-#821
# cache を全面 invalidate する (v2 cache が hit し続けると masked 動画の誤結果
# が再利用され、新 detector が走らない)。
# v4 (#805 段階2): post-match trailing の disposition が削除 (旧 = post_match
# segment を drop した shape) から非破壊フラグ (新 = post_match=True で残す shape)
# に変わったため、検出出力 (cached boundaries) の shape が変わる。旧 v3 cache が
# hit し続けると削除済み結果 (試合 1 本欠落) が silent に再利用されるので bump
# する。cache key params (keep_trailing 含む) 自体は不変。
_CACHE_VERSION = 4

# masked_algo version: identifies the masked-path detection algorithm baked
# into cached boundaries. Only used for cache invalidation on masked-affected
# runs (params.masked=True or auto-fallback used).
# version 1 = pre-#822 position-independent localize masked path
# version 2 = #822 anchor presence + Layer 2 (9-probe strict majority)
# version 3 = #822 Onsal recalibration: 15-probe quorum>=2 + zero-gap merge
_MASKED_ALGO_VERSION = 3

# vtuber_algo version: identifies the vtuber-path detection algorithm baked
# into cached boundaries. Only used for cache invalidation on vtuber-affected
# runs (config.vtuber=True or params.vtuber=True).
# version 1 = pre-#895 legacy band-crop blackout path (key absent = 1)
# version 2 = #895 timeline segmentation (V0-V2, presence x motion)
# version 3 = #895 P2 V3/V4 integration (gap refinement + at-anchor validation)
_VTUBER_ALGO_VERSION = 3


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

    total_start = time.monotonic()
    detected_at = _iso_utc_now()

    if verbose and show:
        _print_environment_header(config.output_dir)

    # Step 1: Probe video metadata
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
            # Surface the detection context that the cached run used (#380).
            # Without this, verbose+cached prints only "Detected ... (cached)"
            # which strips the parameter summary users rely on for
            # troubleshooting (interval / threshold / audio state).
            if show and verbose:
                _display_cache_hit_params(cache_path, config)
            if show:
                _display_results(boundaries, metadata, video_path, verbose, cached=True)
            gaps = _find_gaps(boundaries, metadata["duration"], min_gap=300.0)
            if show and verbose and gaps:
                _display_gaps(gaps)
            if config.dry_run:
                if show:
                    typer.echo("\nDry run: skipping split")
                _emit_total_time(total_start, verbose, show)
                return
            # #805 段階2: cache が post_match=True の shape を保持しうる (v4 cache
            # bump)。post_match (MP4 不生成) は disk 予算に計上しない。active のみ
            # 渡す (post_match が無い常態では active == boundaries で bit-exact)。
            active_boundaries, _ = _partition_post_match(boundaries)
            _check_disk_space(
                video_path, active_boundaries, metadata["duration"], config, show=show
            )
            # #591 -- cache hit でも GUI export が使う system_info は
            # 「現在の環境」を反映したい (録画から数日後に GPU 構成を
            # 変えた可能性) ので、ここで probe し直す。vendor_used は
            # cache hit のため None (今回 detect していない)。
            from allaganeye.system_info import probe_gpu_vendors

            cached_system_info = _build_system_info(
                available_vendors=probe_gpu_vendors(),
                vendor_used=None,
            )
            split_start = time.monotonic()
            _split_and_write_metadata(
                video_path,
                boundaries,
                gaps,
                metadata,
                config,
                effective_interval=effective_interval,
                detected_at=detected_at,
                system_info=cached_system_info,
                # cache-hit: resolved path は当該 boundaries を生成した検出の
                # 記録値 (cache top-level) を引き継ぐ。
                masked_fallback_used=_read_cached_masked_fallback(cache_path),
                capture_regions=_read_cached_capture_regions(cache_path),
                quiet=quiet,
            )
            # #805 段階2: MP4 化したのは active のみ (post_match は除外)。
            _emit_splitting_elapsed(split_start, len(active_boundaries), verbose, show)
            _emit_total_time(total_start, verbose, show)
            return

    # Resolve GPU/CPU mode + vendor: auto-select based on codec + probe
    # when not explicit (#334, #546, #591). probe で検出された全 vendor は
    # GUI export encoder 自動選択 (#591) で metadata.json system_info に
    # 保存するため、3-tuple 版 ``_resolve_gpu_mode_with_probe`` を呼ぶ。
    use_gpu, gpu_vendor, available_vendors = _resolve_gpu_mode_with_probe(
        config.use_gpu,
        config.gpu_vendor,
        metadata.get("codec"),
        show,
        verbose,
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

    if show and verbose:
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

    # #644 -- Pass 1 で計測された輝度マップを捕捉して metadata.json に書く
    # ため、`_run_detection` に brightness_callback を渡す。detect.py の
    # run_detect (line 230-260) と同じパターン。callback が呼ばれない経路
    # (cache hit や Pass 1 skip) では captured_brightness が空のまま残り、
    # `_split_and_write_metadata` 呼び出し時に None を渡す。
    captured_brightness: dict[float, float] = {}

    def _on_brightness(samples: dict[float, float]) -> None:
        captured_brightness.update(samples)

    # #821 -- masked fallback の resolved path を捕捉 (request flag と分離)。
    masked_fallback_used = False

    def _on_masked_fallback() -> None:
        nonlocal masked_fallback_used
        masked_fallback_used = True

    # #810 -- 最終的に有効だった capture region を捕捉して cache / metadata へ。
    captured_region: CaptureRegions | None = None

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
        brightness_callback=_on_brightness,
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

    # Display pipeline statistics (verbose only)
    if verbose and show and detect_stats is not None:
        _print_detection_stats(detect_stats)
        if captured_region is not None:
            typer.echo(f"  Region: {_format_region_token(captured_region)}")

    # Display detection results
    if show:
        _display_results(boundaries, metadata, video_path, verbose)

    # Show significant gaps (verbose only)
    gaps = _find_gaps(boundaries, metadata["duration"], min_gap=300.0)
    if verbose and show and gaps:
        _display_gaps(gaps)

    # Save detection cache
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

    # Step 3: Split (unless dry-run)
    if config.dry_run:
        if show:
            typer.echo("\nDry run: skipping split")
        _emit_total_time(total_start, verbose, show)
        return

    # #805 段階2: post_match (MP4 不生成) は disk 予算に計上しない。active
    # のみ渡す (post_match が無い常態では active == boundaries で bit-exact)。
    active_boundaries, _ = _partition_post_match(boundaries)
    _check_disk_space(
        video_path, active_boundaries, metadata["duration"], config, show=show
    )
    # #591 -- detect 経路で確定した vendor を vendor_used に記録。CPU
    # 強制 (use_gpu=False) のときは vendor_used=None (実際使ってない)。
    detected_system_info = _build_system_info(
        available_vendors=available_vendors,
        vendor_used=gpu_vendor if use_gpu else None,
    )
    # #644 -- captured_brightness が空なら build_brightness_samples が None を
    # 返す (split_matches.py:1373-1374 `if not raw_brightness: return None`)。
    # detect.py:239 (run_detect) と同パターン: guard なしで build_brightness_samples
    # を呼び、None を _split_and_write_metadata に渡す。_build_metadata_payload が
    # None で brightness_samples キーを skip するため、cache hit / Pass 1 skip 経路
    # では metadata.json に書かれない (既存仕様「Pass 1 が走った場合のみ」と整合)。
    brightness_samples = build_brightness_samples(captured_brightness)
    split_start = time.monotonic()
    _split_and_write_metadata(
        video_path,
        boundaries,
        gaps,
        metadata,
        config,
        effective_interval=effective_interval,
        detected_at=detected_at,
        system_info=detected_system_info,
        brightness_samples=brightness_samples,
        masked_fallback_used=masked_fallback_used,
        # #805 段階2: warnings is always empty -- the W1
        # post_match_trailing_dropped emission was removed; the non-destructive
        # post_match flag on the Match now records a post-match trailing segment.
        warnings=build_warnings(),
        capture_regions=captured_region,
        quiet=quiet,
    )
    # #805 段階2: MP4 化したのは active のみ (post_match は除外)。verbose の
    # split 件数は書き出した MP4 数を報告する。
    _emit_splitting_elapsed(split_start, len(active_boundaries), verbose, show)
    _emit_total_time(total_start, verbose, show)


def run_split_from_metadata(
    metadata_path: Path,
    config: SplitConfig,
    *,
    verbose: bool = False,
    quiet: bool = False,
) -> None:
    """Split a video using a previously generated ``metadata.json`` (#463).

    Reads the JSON produced by ``allaganeye detect <video>`` (or a legacy
    ``allaganeye split <video>`` run), resolves the source video path, and
    runs only the ffmpeg ``-c copy`` split phase.  Detection is skipped.

    The source path stored in ``metadata.json`` is resolved relative to the
    metadata file's directory when it is not absolute, so a metadata file
    that travels alongside its output directory keeps working after a move.

    Output files are written into ``config.output_dir`` (not necessarily the
    metadata file's directory), and the metadata file is **rewritten** with
    updated ``output_file`` entries that reflect the new paths.
    """
    show = not quiet
    total_start = time.monotonic()

    payload = read_metadata(metadata_path)

    source_value = payload.get("source")
    if not isinstance(source_value, str) or not source_value:
        raise InputFileError(
            f"metadata file {metadata_path} missing required field 'source'"
        )
    source_path = Path(source_value)
    if not source_path.is_absolute():
        source_path = (metadata_path.parent / source_path).resolve()
    if not source_path.exists():
        raise InputFileError(
            f"source video referenced by {metadata_path} not found: {source_path}"
        )

    matches = payload.get("matches")
    if not isinstance(matches, list) or not matches:
        raise InputFileError(
            f"metadata file {metadata_path} has no match entries to split"
        )

    boundaries: list[MatchBoundary] = []
    for entry in matches:
        if not isinstance(entry, dict):
            raise InputFileError(
                f"metadata file {metadata_path} has a non-object match entry"
            )
        try:
            start = float(entry["start_time"])
            end = float(entry["end_time"])
        except (KeyError, TypeError, ValueError) as e:
            raise InputFileError(
                f"metadata file {metadata_path} has a match entry missing "
                f"start_time/end_time: {e}"
            ) from e
        type_value = entry.get("type", "unknown")
        boundary: MatchBoundary = {"start": start, "end": end, "type": type_value}
        # #805 段階2: detect 由来の post_match Match を再 split で MP4 化せず、
        # 新 metadata でも flag を保持するため boundary に復元する。truthy のとき
        # のみ set (通常 match は flag-free のまま = detector の convention 準拠)。
        # `_split_and_write_metadata` の partition が active と分離し、active のみ
        # split + output_file 付与、post_match は除外 + flag 保持で rewrite する。
        if entry.get("post_match"):
            boundary["post_match"] = True
        boundaries.append(boundary)

    gaps_raw = payload.get("gaps", [])
    gaps: list[Gap] = []
    if isinstance(gaps_raw, list):
        for g in gaps_raw:
            if not isinstance(g, dict):
                continue
            try:
                gaps.append(
                    {
                        "start": float(g["start_time"]),
                        "end": float(g["end_time"]),
                        "duration": float(g["duration"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                # Forgiving: gaps are informational only.
                continue

    probe = probe_video(source_path)

    detected_at_value = payload.get("detected_at")
    detected_at = (
        detected_at_value if isinstance(detected_at_value, str) else _iso_utc_now()
    )

    # #586 -- preserve detect timing across `--from-metadata` invocations.
    # 再検知してないので元 metadata の検知開始/完了時刻を引き継ぎ、GUI
    # 「所要」が「検知時の所要」を表示し続けるようにする。pre-#586 metadata
    # では両フィールド欠落 -> None を渡して _split_and_write_metadata の
    # fallback (started=detected_at / completed=_iso_utc_now()) に委譲。
    old_started_at = payload.get("detection_started_at")
    old_completed_at = payload.get("detection_completed_at")
    preserve_started_at = old_started_at if isinstance(old_started_at, str) else None
    preserve_completed_at = (
        old_completed_at if isinstance(old_completed_at, str) else None
    )

    # #644 -- preserve brightness_samples across `--from-metadata`.
    # 元 metadata に brightness_samples があれば新 metadata にもそのまま
    # コピーする。PR #626 の detection_started_at / detection_completed_at
    # と同じ preserve パターン。元に無ければ None を渡して新 metadata でも
    # 欠落させる (cache hit / pre-#569 metadata 経路と同じ挙動)。
    # JSON payload は Any 型なので isinstance チェック後に cast で
    # BrightnessSamples (TypedDict) に narrow する。schema 検証は
    # _build_metadata_payload 側の TypedDict 構造に委譲。
    old_brightness_samples = payload.get("brightness_samples")
    preserve_brightness_samples: BrightnessSamples | None = (
        cast("BrightnessSamples", old_brightness_samples)
        if isinstance(old_brightness_samples, dict)
        else None
    )

    # #805 段階1 -- preserve warnings across `--from-metadata`. detect ->
    # split --from-metadata -o <same dir> が記録済み warning を silent に
    # 上書きしないよう、元 metadata の warnings を引き継ぐ (#586 timing /
    # #644 brightness と同じ preserve パターン)。本ランは再検知しないので
    # 新たな drop 痕跡は生成されない。writer は schema 検証しないため、壊れた
    # entry や schema 違反 optional field が freshly written metadata.json に
    # 漏れないよう sanitize_warnings で coerce する (非 dict / code 欠落 entry の
    # drop + 不正 field の strip)。
    preserve_warnings = sanitize_warnings(payload.get("warnings"))

    # #810 -- preserve capture_regions across `--from-metadata`. 本ランは再検知
    # しないため元 metadata の領域記録を引き継ぐ (#644 brightness_samples と
    # 同じ preserve パターン)。
    # codex adversarial-review F1 (2026-07-07 Idios confirmed): malformed preserve は
    # sanitize して omit + warning (sanitize_warnings #805 と同型)。
    # 元に capture_regions が absent (None) なら warning なし・欠落のまま。
    old_capture_regions = payload.get("capture_regions")
    if old_capture_regions is not None:
        preserve_capture_regions = _sanitize_capture_regions(old_capture_regions)
        if preserve_capture_regions is None:
            logger.warning(
                "Dropping malformed capture_regions from %s "
                "(shape validation failed -- field omitted from rewritten metadata)",
                metadata_path,
            )
    else:
        preserve_capture_regions = None

    detection_params = payload.get("detection_params")
    if isinstance(detection_params, dict):
        effective_interval = float(
            detection_params.get("sample_interval", config.sample_interval)
        )
    else:
        effective_interval = config.sample_interval

    if show:
        typer.echo(f"Splitting {len(boundaries)} match(es) from {metadata_path.name}")
    if verbose and show:
        typer.echo(f"  Source: {source_path}")

    # #805 段階2: post_match (MP4 不生成) は disk 予算に計上しない。active
    # のみ渡す (post_match が無い常態では active == boundaries で bit-exact)。
    active_boundaries, _ = _partition_post_match(boundaries)
    _check_disk_space(
        source_path, active_boundaries, probe["duration"], config, show=show
    )
    # #591 -- split-only path は detect しないので vendor_used=None。
    # GUI export が encoder 選択に使う「現在の環境」を反映するため、
    # ここで probe し直して metadata を更新する (前回 detect の値で
    # 上書き)。
    from allaganeye.system_info import probe_gpu_vendors

    split_only_system_info = _build_system_info(
        available_vendors=probe_gpu_vendors(),
        vendor_used=None,
    )
    split_start = time.monotonic()
    _split_and_write_metadata(
        source_path,
        boundaries,
        gaps,
        probe,
        config,
        effective_interval=effective_interval,
        detected_at=detected_at,
        detection_started_at=preserve_started_at,
        detection_completed_at=preserve_completed_at,
        system_info=split_only_system_info,
        brightness_samples=preserve_brightness_samples,
        # from-metadata: 入力 metadata に記録された resolved path を引き継ぐ
        # (本ランは detect しないため)。
        masked_fallback_used=bool(
            (detection_params or {}).get("masked_fallback_used", False)
        ),
        # #805 段階1: 元 metadata の warnings を preserve (再検知しないため)。
        warnings=preserve_warnings,
        capture_regions=preserve_capture_regions,
        quiet=quiet,
    )
    # #805 段階2: MP4 化したのは active のみ (post_match は除外)。
    _emit_splitting_elapsed(split_start, len(active_boundaries), verbose, show)
    _emit_total_time(total_start, verbose, show)


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
        # Mark uncertain segments ("unknown" = recording started/ended
        # mid-match) so users can tell them apart from full "fl_match" runs
        # without opening metadata.json (#382). fl_match stays unmarked to
        # avoid noise in the common case.
        type_marker = "  [unknown]" if b.get("type") == "unknown" else ""
        typer.echo(
            f"  Match {i}: {_format_timestamp(b['start']):>7s} - "
            f"{_format_timestamp(b['end']):>7s}  ({_format_duration(dur)})"
            f"{type_marker}"
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


_REGION_TOKEN_MAX_LEN = 32
"""verbose region token に埋め込む free string の表示上限 (round-3 R3-4)。"""


def _clean_region_text(value: object) -> str:
    """改竄 cache 由来 free string の端末 hygiene (round-3 R3-4)。

    非印字文字 (ANSI escape 等の制御文字) を '?' に置換し、長さを cap する。
    raw 診断表示の意図 (round-1/2 裁定) は保ちつつ端末制御系の注入だけを塞ぐ。
    """
    text = str(value)
    cleaned = "".join(ch if ch.isprintable() else "?" for ch in text)
    if len(cleaned) > _REGION_TOKEN_MAX_LEN:
        cleaned = cleaned[:_REGION_TOKEN_MAX_LEN] + "..."
    return cleaned


def _format_region_token(regions: object) -> str:
    """capture region の verbose 1 行表示 (#810)。縮退を silent にしない。

    cache-hit 経路では raw cache 記録値 (無検証) を受けるため、malformed 入力でも
    crash しない tolerant contract: 欠落 / 非 dict は "unknown"、座標が実数でない
    (bool 含む) 場合は "invalid" を返す (round-1 #1: 非数値 x/y/w/h で ``:.2f`` が
    ValueError になる regression の防御)。free string (source / fallback_reason)
    は `_clean_region_text` で端末 hygiene を通す (round-3 R3-4)。
    """
    if not isinstance(regions, dict):
        return "unknown"
    coarse = regions.get("coarse")
    if not isinstance(coarse, dict):
        return "unknown"
    source = coarse.get("source", "?")
    if source == "fallback":
        label = "full_frame"
    else:
        coords = [coarse.get(k) for k in ("x", "y", "w", "h")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in coords):
            return "invalid"
        x, y, w, h = coords
        label = f"{_clean_region_text(source)}({x:.2f},{y:.2f},{w:.2f},{h:.2f})"
    reason = regions.get("fallback_reason")
    return f"{label}, fallback={_clean_region_text(reason)}" if reason else label


def _display_cache_hit_params(cache_path: Path, config: SplitConfig) -> None:
    """Echo the cached run's detection parameters for verbose + cache-hit (#380).

    When ``.detection_cache.json`` hits, ``run_split`` early-returns before
    the cache-miss path prints its ``Detecting match boundaries (...)``
    summary, which strips every parameter a troubleshoot report relies on.
    This surfaces the same params from the cache itself so verbose output
    stays informative whether or not Pass 1/2 ran.

    Always emits the ``Cache hit: ...`` header so users running with ``-v``
    can see that verbose output is active even when the cache can't be
    introspected.  Failure modes (I/O error, malformed JSON, missing
    params section) are surfaced as ``(unavailable: <reason>)`` rather
    than returning silently -- the split itself is unaffected, but the
    verbose summary makes the degraded state visible.
    """
    header = f"Cache hit: detection params from {cache_path.name}"

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except OSError as e:
        logger.debug("Cannot re-read cache for verbose params: %s", cache_path)
        typer.echo(header)
        typer.echo(f"  (unavailable: cache file unreadable - {type(e).__name__})")
        return
    except json.JSONDecodeError:
        logger.debug("Cache file not valid JSON for verbose params: %s", cache_path)
        typer.echo(header)
        typer.echo("  (unavailable: cache file is not valid JSON)")
        return

    params = data.get("params")
    if not isinstance(params, dict) or not params:
        typer.echo(header)
        typer.echo("  (unavailable: cache file has no params section)")
        return

    # The cached ``audio`` state is recorded in ``params.no_audio`` (bool).
    # Live-probe AUDIO_FROZEN so the verbose line mirrors `_run_audio_scan`
    # behaviour for the current run, same as the cache-miss summary.
    cached_no_audio = bool(params.get("no_audio", config.no_audio))
    # vtuber / masked / keep_trailing は cache key に含まれるため hit 時は config と
    # 一致するが、表示は cache 記録値を正とする (legacy cache は key なし = False)。
    cached_vtuber = bool(params.get("vtuber", False))
    cached_masked = bool(params.get("masked", False))
    cached_keep_trailing = bool(params.get("keep_trailing", False))
    # resolved path (top-level、key 非対象)。auto-fallback 時は masked=off でも
    # masked_fallback=on になる (#821)。
    cached_fallback = bool(data.get("masked_fallback_used", False))
    # masked_algo は masked 影響 run のみ表示 (診断上意味を持つのは masked 経路のみ)。
    # 破損 cache で int() 変換不能な値でも display 専用なので raise せず "?" にフォールバック
    # (int 化可能な値 "3"/3.0 等は変換される; 安全性は値等価でのみ hit するため不変)。
    try:
        cached_algo: int | str = int(params.get("masked_algo", 1))
    except (ValueError, TypeError):
        cached_algo = "?"
    # NOTE: _load_cache の masked_affected と異なり config.masked を含めない
    # (こちらは cache 記録値の診断表示で、invalidation 判定ではない。live config
    # と cache が食い違う case は params 比較が先に miss させるため到達しない)。
    masked_affected = cached_masked or cached_fallback
    # vtuber_algo は vtuber 影響 run のみ表示 (masked_algo と同型)。
    try:
        cached_vtuber_algo_display: int | str = int(params.get("vtuber_algo", 1))
    except (ValueError, TypeError):
        cached_vtuber_algo_display = "?"
    # region も他 token 同様 raw cache 記録値を正として表示する (#810)。legacy
    # cache では metadata.json 側が FULL_FRAME を合成しても表示は unknown の
    # まま (「cache に何が記録されているか」の診断表示であり意図的な差)。

    algo_token = f", masked_algo={cached_algo}" if masked_affected else ""
    vtuber_algo_token = (
        f", vtuber_algo={cached_vtuber_algo_display}" if cached_vtuber else ""
    )
    typer.echo(header)
    typer.echo(
        "  "
        f"sample_interval={params.get('sample_interval', '?')}s, "
        f"threshold={params.get('blackout_threshold', '?')}, "
        f"min_match={params.get('min_match_duration', '?')}s, "
        f"min_blackout={params.get('min_blackout_duration', '?')}s, "
        f"audio={_audio_status_str(cached_no_audio)}, "
        f"vtuber={'on' if cached_vtuber else 'off'}, "
        f"masked={'on' if cached_masked else 'off'}, "
        f"keep_trailing={'on' if cached_keep_trailing else 'off'}, "
        f"masked_fallback={'on' if cached_fallback else 'off'}"
        f"{algo_token}"
        f"{vtuber_algo_token}, "
        f"region={_format_region_token(data.get('capture_regions'))}"
    )


def _workers_summary_str(workers: int | None) -> str:
    """Format workers count for verbose summary, resolving ``auto`` (#389).

    When ``config.workers is None`` the CLI delegates to
    ``_resolve_workers`` which picks ``min(cpu_count, 24)``.  Users with
    performance issues need to see the *resolved* number to diagnose
    under-parallelised runs, not just the ``auto`` placeholder.
    """
    if workers is not None:
        return str(workers)

    from allaganeye.video.detector import _resolve_workers

    resolved = _resolve_workers(None)
    return f"auto ({resolved})"


def _audio_status_str(no_audio: bool) -> str:
    """Return audio-scan status string for verbose summary (#384).

    Must stay in sync with ``_run_audio_scan``: if the audio module is
    frozen, the scan is skipped regardless of ``--no-audio``, and the
    verbose summary must reflect that instead of reading ``config.no_audio``
    blindly.
    """
    from allaganeye.audio import AUDIO_FROZEN

    if AUDIO_FROZEN:
        return "frozen"
    return "off" if no_audio else "on"


def _run_audio_scan(
    video_path: Path,
    config: SplitConfig,
    *,
    show: bool,
    verbose: bool,
) -> list[BgmHit] | None:
    """Scan the video for Fanfare peaks, returning hits or None.

    Returns ``None`` when audio promotion is disabled (``--no-audio``),
    when the audio module is frozen (``AUDIO_FROZEN``), or when the scan
    fails for a recoverable reason (missing audio track, ffmpeg error).
    Callers then proceed with scorebar-only filtering.
    """
    from allaganeye.audio import AUDIO_FROZEN

    if AUDIO_FROZEN:
        logger.debug("Audio module frozen (#327) -- skipping Fanfare scan")
        return None

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


# Codecs where GPU decode is typically faster than CPU parallel probing.
# AV1 / VP9 added per #414. Hardware requirements:
# - NVDEC AV1 = RTX 30 series or later
# - Intel QSV AV1 = Arc / Gen12 or later
# - AMD VCN AV1 = VCN 4.0 or later
# VP9 is widely supported on older GPU generations (NVDEC Maxwell+).
_GPU_PREFERRED_CODECS = {"h264", "hevc", "av1", "vp9"}


def _resolve_gpu_mode(
    use_gpu: bool | None,
    gpu_vendor_option: str | None,
    codec: str | None,
    show: bool,
    verbose: bool,
) -> tuple[bool, str | None]:
    """Resolve GPU/CPU mode and vendor (backward-compat 2-tuple wrapper).

    新規呼び出し側 (#591 の system_info 構築など) は probe 結果も使うため
    ``_resolve_gpu_mode_with_probe`` を呼ぶ。既存呼び出し / 既存テストは
    引き続きこの薄い 2-tuple ラッパで動く。
    """
    use_gpu_concrete, vendor, _available = _resolve_gpu_mode_with_probe(
        use_gpu, gpu_vendor_option, codec, show, verbose
    )
    return use_gpu_concrete, vendor


def _resolve_gpu_mode_with_probe(
    use_gpu: bool | None,
    gpu_vendor_option: str | None,
    codec: str | None,
    show: bool,
    verbose: bool,
) -> tuple[bool, str | None, list[str]]:
    """Resolve GPU/CPU mode and vendor from user flags + probe (#334, #546, #553, #550, #591).

    - *use_gpu*: None で自動 codec 判定、True/False で明示指示。
    - *gpu_vendor_option*: None / "auto" で自動選択、"nvidia" / "amd" /
      "intel" で明示指定。``_VENDOR_HWACCEL_MAP`` に未登録の vendor や
      probe に見つからない vendor を要求すると ``ConfigValidationError``
      (exit 5)。現時点で nvidia / amd / intel すべて実装済み。

    Returns ``(use_gpu_concrete, selected_vendor, available_vendors)``
    tuple.  *vendor* が ``None`` の場合は GPU 経路で ``-hwaccel auto`` が
    使われる。*available_vendors* は ``probe_gpu_vendors()`` の生結果で、
    GUI export が encoder 自動選択 (#591) に使うため metadata.json
    ``system_info`` セクションに保存される。
    """
    from allaganeye.exceptions import ConfigValidationError
    from allaganeye.system_info import probe_gpu_vendors
    from allaganeye.video.gpu_detector import (
        _VENDOR_HWACCEL_MAP,
        _select_gpu_vendor,
    )

    available = probe_gpu_vendors()

    # Explicit vendor request validation (#546 / #553 / #550): 未実装 or 未検出は exit 5。
    # 現時点で _VENDOR_HWACCEL_MAP は nvidia / amd / intel すべて含むので
    # この分岐は config 側 (auto/nvidia/amd/intel) の validation を抜ける
    # 将来の vendor 追加忘れに対する defensive guard。
    if gpu_vendor_option and gpu_vendor_option != "auto":
        if gpu_vendor_option not in _VENDOR_HWACCEL_MAP:
            raise ConfigValidationError(
                f"--gpu-vendor {gpu_vendor_option}: 現在未実装です。"
                " --gpu-vendor auto / nvidia / amd / intel のいずれかを使用してください。"
            )
        if gpu_vendor_option not in available:
            raise ConfigValidationError(
                f"--gpu-vendor {gpu_vendor_option} を要求されましたが、"
                f"環境で検出された GPU vendor は {available or '(なし)'} です。"
                " --gpu-vendor auto または --no-gpu を使用してください。"
            )

    vendor = _select_gpu_vendor(gpu_vendor_option, available)

    if use_gpu is not None:
        if show and verbose and use_gpu and vendor:
            typer.echo(f"  GPU vendor: {vendor}")
        return use_gpu, vendor, available

    codec_match = (codec or "").lower() in _GPU_PREFERRED_CODECS
    # Codec match is the primary signal (#334 の既存挙動を維持)。
    # vendor=None (probe_gpu_vendors() が空 / 未実装 vendor のみ検出)
    # でも use_gpu=True を返し、scan_gpu の legacy path
    # (-hwaccel auto) に入る。ffmpeg 側で GPU decode に失敗した場合は
    # CPU fallback される (既存の動作)。
    selected = codec_match
    if show and verbose:
        mode = "GPU" if selected else "CPU"
        typer.echo(f"  Auto-selected {mode} mode (codec: {codec or 'unknown'})")
        if selected and vendor:
            typer.echo(f"  GPU vendor: {vendor}")
    return selected, vendor if selected else None, available


def _build_system_info(
    *,
    available_vendors: list[str],
    vendor_used: str | None,
) -> SystemInfo:
    """Build the ``system_info`` dict for ``metadata.json`` (#591, extended #761).

    GUI export 画面 (Phase 4 / `enumerate_h264_encoders`) が
    ``gpu_vendors_available`` と ``vendor_preference`` を読んで NVENC /
    QSV / AMF / libx264 を auto-select する。``gpu_vendor_used`` は
    実際 detect 経路で使った vendor (CPU 強制 / cache hit / split-only
    では ``None``)。``gpu`` は GPU モデル名の文字列リスト (#761) で、
    GUI export の NVENC parallel slot 数 SKU 検索 (``probe_nvenc_engine_count``)
    に使用する。
    """
    from allaganeye.system_info import get_gpu_info_lines
    from allaganeye.video.gpu_detector import _VENDOR_PREFERENCE

    return {
        "gpu_vendors_available": list(available_vendors),
        "gpu_vendor_used": vendor_used,
        "vendor_preference": list(_VENDOR_PREFERENCE),
        "gpu": get_gpu_info_lines(),
    }


def _run_detection(
    video_path: Path,
    metadata: ProbeResult,
    effective_interval: float,
    config: SplitConfig,
    *,
    audio_hits: list[BgmHit] | None = None,
    quiet: bool = False,
    stats: DetectionStats | None = None,
    use_gpu: bool = False,
    gpu_vendor: str | None = None,
    progress_emitter: ProgressEmitter | None = None,
    brightness_callback: Callable[[dict[float, float]], None] | None = None,
    masked_fallback_callback: Callable[[], None] | None = None,
    region_callback: Callable[[RegionTimeline], None] | None = None,
) -> list[MatchBoundary]:
    """Run detection with progress bars for each phase (#328, #329, #331).

    #569 -- when *progress_emitter* is supplied (GUI / Tauri wrapper),
    the click TTY progress bars are replaced by JSON-line events on the
    emitter's stream.  ``quiet`` / ``progress_emitter`` are mutually
    exclusive in spirit; if both are provided the emitter wins (so a
    quiet-from-CLI-call-site GUI subprocess still emits events).
    *brightness_callback* is forwarded transparently into
    ``detect_match_boundaries`` so callers can capture the Pass 1
    brightness map for downstream consumers (e.g. the GUI complete
    screen's brightness timeline).
    """
    detect_kwargs = {
        "duration_hint": metadata["duration"],
        "sample_interval": effective_interval,
        "blackout_threshold": config.blackout_threshold,
        "min_match_duration": config.min_match_duration,
        "min_blackout_duration": config.min_blackout_duration,
        "gpu_vendor": gpu_vendor,
        "use_gpu": use_gpu,
        # L3 B6: VTuber game-inset recording -> scorebar-band anchor region.
        # False (default) keeps FULL_FRAME = OBS bit-exact behavior.
        "vtuber": config.vtuber,
        # L3 masked-OBS (#753): chat-mask overlay -> mask-free region fallback.
        # False (default) only auto-triggers on 0-blackout; True forces it.
        "masked": config.masked,
        "workers": config.workers,
        "src_resolution": (metadata["width"], metadata["height"]),
        "codec": metadata.get("codec"),
        "audio_hits": audio_hits,
        "stats": stats,
        "brightness_callback": brightness_callback,
        "masked_fallback_callback": masked_fallback_callback,
        "region_callback": region_callback,
        # #805: opt-out flag. keep_trailing skips the #797 post-match trailing
        # flagging entirely so a trailing no-scorebar segment is left unflagged
        # (default False = bit-exact).
        "keep_trailing": config.keep_trailing,
        # #576: rational fps propagation (probe -> detector).
        "source_fps": metadata.get("fps"),
        "source_fps_num": metadata.get("fps_num"),
        "source_fps_den": metadata.get("fps_den"),
    }

    if progress_emitter is not None:
        # GUI / json mode: wire the same callbacks but emit JSON lines
        # instead of advancing click progressbars.  No TTY work at all.
        total_duration = metadata["duration"]
        estimated_samples = max(1, int(total_duration / effective_interval))

        def gui_on_progress(completed: int, total: int, blackout_count: int) -> None:
            progress_emitter.emit_progress(
                "scan",
                completed,
                total,
                blackout_frames=blackout_count,
            )

        def gui_on_chunk_dispatch(num_chunks: int) -> None:
            progress_emitter.emit("chunk_dispatch", chunks=num_chunks)

        def gui_on_chunk(done: int, total: int, eta_seconds: float) -> None:
            progress_emitter.emit(
                "chunk",
                completed=done,
                total=total,
                eta_s=eta_seconds if eta_seconds > 0 else None,
            )

        def gui_on_refine(completed: int, total: int) -> None:
            progress_emitter.emit_progress("refine", completed, total)

        def gui_on_scorebar(completed: int, total: int) -> None:
            progress_emitter.emit_progress("scorebar", completed, total)

        # Announce Pass 1 entry so the GUI can pre-populate the bar at 0%
        # before the first chunk completes (otherwise the bar sits empty
        # until ~10s into a long video).
        progress_emitter.emit_progress("scan", 0, estimated_samples)
        return detect_match_boundaries(
            video_path,
            **detect_kwargs,
            progress_callback=gui_on_progress,
            refine_progress_callback=gui_on_refine,
            scorebar_progress_callback=gui_on_scorebar,
            chunk_progress_callback=gui_on_chunk,
            chunk_dispatch_callback=gui_on_chunk_dispatch,
        )

    if not quiet:
        total_duration = metadata["duration"]
        estimated_samples = max(1, int(total_duration / effective_interval))

        # Three-bar progress design (#368 / #393 / #434):
        #
        # - Detecting (Pass 1 scan, known length = estimated_samples)
        # - Refining (Pass 2 probes, total published via first callback)
        # - Scorebar (classification, total published via first callback)
        #
        # Each bar is opened with a manual ``__enter__`` and closed with
        # ``__exit__`` *before* the next bar opens so click's ``\r`` rewrite
        # can never overwrite an active bar (that caused Detecting to
        # vanish, #368) and the Pass 2 -> Scorebar transition no longer
        # mixes units (100% -> 99% rollover, #393).  ``try/finally`` guards
        # against exceptions leaving a bar dangling on the TTY.
        #
        # #434 multi-line eager display: when stdout is a TTY we pre-print
        # waiting placeholders for Refining / Scorebar BELOW the Detecting
        # line so users see all three phases from the start.  Each
        # placeholder is overwritten by its bar when the corresponding
        # callback first fires.  Non-TTY (CI / redirected output) falls
        # back to the historical sequential bars to avoid garbling logs
        # with ANSI escapes.
        eager_phases = _stdout_supports_eager_phases()
        if eager_phases:
            typer.echo("Detecting [starting...]".ljust(_PROGRESS_LABEL_WIDTH + 24))
            typer.echo(
                "Refining   [waiting for Pass 1 to finish]".ljust(
                    _PROGRESS_LABEL_WIDTH + 30
                )
            )
            typer.echo(
                "Scorebar   [waiting for Pass 2 to finish]".ljust(
                    _PROGRESS_LABEL_WIDTH + 30
                )
            )
            sys.stdout.write("\033[3A")  # cursor up 3 lines back to Detecting
            sys.stdout.flush()

        detecting_bar = _eta_progressbar(
            estimated_samples,
            "Detecting",
            suppress_click_eta=use_gpu,
        )
        detecting_bar.__enter__()
        detecting_state = {"last_pos": 0, "closed": False}
        # ``placeholder_present`` tracks whether the ``[waiting...]`` line
        # for that phase is still on screen.  Set ``True`` only when the
        # eager pre-print actually ran; flipped to ``False`` when the bar
        # opens (placeholder erased) or the Pass 2 skip path replaces it
        # with ``[skipped: no regions]``.  Used by the ``finally`` cleanup
        # so a Pass 1 / Pass 2 exception doesn't leave stale ``[waiting]``
        # text dangling above the traceback (#434 error path).
        refine_state: dict = {
            "bar": None,
            "last": 0,
            "placeholder_present": eager_phases,
        }
        scorebar_state: dict = {
            "bar": None,
            "last": 0,
            "placeholder_present": eager_phases,
        }

        def _close_detecting_if_open() -> None:
            """Emit newline after Pass 1 so the next bar starts cleanly."""
            if not detecting_state["closed"]:
                detecting_bar.__exit__(None, None, None)
                detecting_state["closed"] = True

        def _close_refine_if_open() -> None:
            if refine_state["bar"] is not None:
                refine_state["bar"].__exit__(None, None, None)
                refine_state["bar"] = None

        def _close_scorebar_if_open() -> None:
            if scorebar_state["bar"] is not None:
                scorebar_state["bar"].__exit__(None, None, None)
                scorebar_state["bar"] = None

        def _erase_current_line() -> None:
            """Clear the cursor's line so the next bar overwrites a placeholder.

            No-op outside the eager-display path since there is no
            placeholder to clear (#434).
            """
            if eager_phases:
                sys.stdout.write("\033[2K")
                sys.stdout.flush()

        def on_progress(completed: int, total: int, blackout_count: int) -> None:
            advance = completed - detecting_state["last_pos"]
            if advance > 0:
                detecting_bar.update(advance)
            detecting_state["last_pos"] = completed

        def on_chunk_dispatch(num_chunks: int) -> None:
            # First feedback before any chunk completes (#437).
            # Long videos (2h+) used to sit at "Detecting 0%" for 2-3
            # minutes while the first chunk decoded; this shows users
            # the work has started and how many chunks to expect.
            # Include "ETA: --:--:--" placeholder so users see a consistent
            # ETA position from dispatch through chunk completion (#365
            # Idios feedback: pre-update でも ETA を出す改善、CPU mode
            # の commit 6e48381 と一貫する). Once the first chunk
            # completes, ``on_chunk`` overwrites this label with the
            # caller-computed ETA.
            detecting_bar.label = (
                f"Detecting [dispatching {num_chunks} chunks, ETA: --:--:--]".ljust(
                    _PROGRESS_LABEL_WIDTH
                )
            )
            detecting_bar.render_progress()

        def on_chunk(done: int, total: int, eta_seconds: float) -> None:
            # Update label so users see movement between chunk completions
            # on GPU mode (otherwise the bar stays at 0% then jumps, #333).
            if eta_seconds > 0:
                detecting_bar.label = (
                    f"Detecting [chunk {done}/{total}, "
                    f"ETA ~{_format_eta(eta_seconds)}]".ljust(_PROGRESS_LABEL_WIDTH)
                )
            else:
                detecting_bar.label = f"Detecting [chunk {done}/{total}]".ljust(
                    _PROGRESS_LABEL_WIDTH
                )

        def on_refine(completed: int, total: int) -> None:
            # First Pass 2 callback: close Detecting (emits newline) and
            # open the Refining bar on a fresh line.
            if refine_state["bar"] is None:
                _close_detecting_if_open()
                _erase_current_line()  # erase ``Refining [waiting]`` placeholder
                refine_state["placeholder_present"] = False
                refine_state["bar"] = _eta_progressbar(total, "Refining")
                refine_state["bar"].__enter__()
                refine_state["last"] = 0
            advance = completed - refine_state["last"]
            if advance > 0:
                refine_state["bar"].update(advance)
            refine_state["last"] = completed

        def on_scorebar(completed: int, total: int) -> None:
            # First scorebar callback: close Refining (or Detecting if
            # Pass 2 had no regions) and open the Scorebar bar fresh.
            if scorebar_state["bar"] is None:
                refine_was_open = refine_state["bar"] is not None
                _close_refine_if_open()
                _close_detecting_if_open()
                if eager_phases and not refine_was_open:
                    # Pass 2 had no regions; cursor is on the Refining
                    # placeholder. Replace it with a "skipped" marker and
                    # advance one line to land on the Scorebar placeholder.
                    sys.stdout.write("\033[2KRefining   [skipped: no regions]\n")
                    sys.stdout.flush()
                    refine_state["placeholder_present"] = False
                _erase_current_line()  # erase ``Scorebar [waiting]`` placeholder
                scorebar_state["placeholder_present"] = False
                scorebar_state["bar"] = _eta_progressbar(total, "Scorebar")
                scorebar_state["bar"].__enter__()
                scorebar_state["last"] = 0
            advance = completed - scorebar_state["last"]
            if advance > 0:
                scorebar_state["bar"].update(advance)
            scorebar_state["last"] = completed

        try:
            result = detect_match_boundaries(
                video_path,
                **detect_kwargs,
                progress_callback=on_progress,
                refine_progress_callback=on_refine,
                scorebar_progress_callback=on_scorebar,
                chunk_progress_callback=on_chunk,
                chunk_dispatch_callback=on_chunk_dispatch,
            )
        finally:
            # Close in reverse open-order; if detection raised we still
            # tidy the TTY.
            _close_scorebar_if_open()
            _close_refine_if_open()
            _close_detecting_if_open()
            # Clean up any ``[waiting...]`` placeholder lines still on
            # screen so a Pass 1 / Pass 2 exception's traceback isn't
            # printed below stale "waiting" text (#434 error path).
            # The ``_close_*_if_open`` calls above land the cursor on the
            # next un-rendered phase line, so erasing in order matches
            # the cursor's downward march.
            if refine_state["placeholder_present"]:
                sys.stdout.write("\033[2K\n")
            if scorebar_state["placeholder_present"]:
                sys.stdout.write("\033[2K\n")
            if (
                refine_state["placeholder_present"]
                or scorebar_state["placeholder_present"]
            ):
                sys.stdout.flush()

        return result

    return detect_match_boundaries(video_path, **detect_kwargs)


_DISK_SPACE_SAFETY_MARGIN = 1.1
"""Safety margin multiplier for estimated output size (10% overhead)."""

_DISK_SPACE_WARNING_RATIO = 0.8
"""Warn when estimated output exceeds this fraction of free space."""


def _estimate_output_size(
    video_path: Path,
    boundaries: list[MatchBoundary],
    source_duration: float,
) -> int:
    """Estimate total output size in bytes.

    Assumes -c copy produces the same bitrate as input.  Returns
    estimated bytes including a 10% safety margin.
    """
    try:
        source_size = video_path.stat().st_size
    except OSError:
        return 0
    if source_duration <= 0:
        return 0

    total_match_duration = sum(b["end"] - b["start"] for b in boundaries)
    ratio = total_match_duration / source_duration
    return int(source_size * ratio * _DISK_SPACE_SAFETY_MARGIN)


def _format_bytes(n: int) -> str:
    """Format bytes as human-readable string (e.g. '45.2 GB')."""
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    return f"{n / 1024:.1f} KB"


def _check_disk_space(
    video_path: Path,
    boundaries: list[MatchBoundary],
    source_duration: float,
    config: SplitConfig,
    *,
    show: bool = True,
) -> None:
    """Check if output disk has enough space for the split output (#338).

    Raises AllaganEyeError if free space is insufficient.  Shows a warning
    if free space is tight but sufficient.  Skipped when output dir cannot
    be resolved (e.g. network path).
    """
    estimated = _estimate_output_size(video_path, boundaries, source_duration)
    if estimated <= 0:
        return

    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(config.output_dir)
    except OSError:
        logger.debug("Cannot check disk space for %s", config.output_dir)
        return

    free = usage.free

    if estimated > free:
        # Quote the path if it contains spaces
        video_str = str(video_path)
        if " " in video_str:
            video_str = f'"{video_str}"'
        raise AllaganEyeError(
            f"Not enough disk space for split output.\n"
            f"  Estimated output: {_format_bytes(estimated)}\n"
            f"  Free space: {_format_bytes(free)} ({config.output_dir.resolve().drive or config.output_dir})\n"
            f"\n"
            f"Detection results are cached. Free up space and re-run:\n"
            f"  allaganeye split {video_str}"
        )

    if estimated > free * _DISK_SPACE_WARNING_RATIO and show:
        typer.echo(
            f"Warning: free space is tight "
            f"(estimated: {_format_bytes(estimated)}, "
            f"free: {_format_bytes(free)})",
            err=True,
        )


_PROGRESS_LABEL_WIDTH = 11
"""Column width for progress bar labels (Detecting/Refining/Splitting)."""


def _stdout_supports_eager_phases() -> bool:
    """Whether stdout is a TTY suitable for the multi-line eager phase display (#434).

    Centralizing the check lets tests substitute behaviour with
    ``monkeypatch`` without touching ``sys.stdout`` directly (capsys
    replaces stdout with a non-TTY buffer, so the production-mode
    check would always be false during tests).
    """
    return sys.stdout.isatty()


class _ETAProgressBar(_ClickProgressBar):
    """Progress bar with explicit 'ETA: H:MM:SS' label (#365).

    click のデフォルト ``%(info)s`` placeholder は ``<percent>  <eta>``
    をラベルなしで展開するだけのため、ユーザーには時刻文字列だけが見え、
    経過時間/残り時間/動画内位置のどれか判別できない (#329 元 issue,
    PR #343 不完全修正、#365 で再対応)。

    本 subclass は ``format_progress_line`` を override し以下に統一:

        Detecting  ###################---  93% ETA: 0:00:22

    ``eta_known=False`` (update 未呼び出し / make_step の 1 秒 debounce
    gate 内) のときも ETA セクションを出し ``ETA: --:--:--`` placeholder
    を表示する (Idios feedback for #365: pre-update でも ETA を出す改善)。

    ``show_eta=False`` (GPU mode #438 の ``suppress_click_eta=True``
    経路) では ETA セクションを出さず percent のみ表示。caller 側が
    self-computed ETA を label に組み込む既存挙動と互換。

    ``finished=True`` (100% 完了) では ETA: 00:00:00 を出さず percent
    のみ表示 (click 親 class と整合)。

    依存する click 8.x の public method:
      - ``format_bar()``    -- bar 文字列
      - ``format_pct()``    -- "  N%" or "NN%" (左 padding あり)
      - ``format_eta()``    -- "H:MM:SS" or "" (eta_known=False / show_eta=False のとき空)
      - ``self.label``      -- ljust 済みラベル
      - ``self.show_eta``   -- ETA 表示フラグ
      - ``self.eta_known``  -- ETA 計算可能フラグ (1 update 後に True)
    """

    def format_progress_line(self) -> str:
        bar = self.format_bar()
        pct = self.format_pct()
        if self.show_eta and not self.finished:
            # eta_known=False (update 未呼び出し / make_step の 1 秒 debounce gate 内)
            # のとき format_eta() は空文字列を返すので、'--:--:--' placeholder で
            # 常時 ETA を表示する (Idios feedback: pre-update でも ETA を出す改善、#365)。
            eta = self.format_eta() or "--:--:--"
            return f"{self.label}{bar} {pct} ETA: {eta}"
        return f"{self.label}{bar} {pct}"


def _eta_progressbar(
    length: int, label: str, *, suppress_click_eta: bool = False
) -> _ETAProgressBar:
    """Create a progress bar with explicit ETA label (#329 / #365).

    Labels are left-justified to ``_PROGRESS_LABEL_WIDTH`` so that
    Detecting / Refining / Scorebar / Splitting bars align vertically.

    When ``suppress_click_eta`` is True (GPU mode, #438), click's own
    ETA is hidden (``show_eta=False``); caller supplies a self-computed
    ETA in the label instead. ``_ETAProgressBar.format_progress_line``
    consumes ``show_eta`` to skip the 'ETA: ' tail in that path.
    """
    return _ETAProgressBar(
        iterable=None,
        length=length,
        label=label.ljust(_PROGRESS_LABEL_WIDTH),
        bar_template="",  # 未使用 (format_progress_line を override したため)
        # click.progressbar() factory 経由では empty_char='-' / width=36 が default
        # だが、ProgressBar.__init__ class 直接インスタンス化では empty_char=' ' /
        # width=30 と異なる default を持つ。issue #365 期待動作
        # `Detecting  ####---  93% ETA: 0:00:22` の `####---` (dash empty char +
        # 36 width) を維持するため明示する (PR #687 review feedback #1+#2 対応)。
        fill_char="#",
        empty_char="-",
        width=36,
        show_eta=not suppress_click_eta,
        show_percent=True,
    )


def _partition_post_match(
    boundaries: list[MatchBoundary],
) -> tuple[list[MatchBoundary], list[MatchBoundary]]:
    """Split boundaries into (active, post_match).

    Active = boundaries written to MP4 + given an output_file. post_match =
    non-destructive trailing flag (#805 段階2): retained in metadata, excluded
    from MP4 output. Order-preserving; the two lists partition the input.
    """
    active = [b for b in boundaries if not b.get("post_match")]
    post_match = [b for b in boundaries if b.get("post_match")]
    return active, post_match


def _split_and_write_metadata(
    video_path: Path,
    boundaries: list[MatchBoundary],
    gaps: list[Gap],
    metadata: ProbeResult,
    config: SplitConfig,
    *,
    effective_interval: float,
    detected_at: str,
    detection_started_at: str | None = None,
    detection_completed_at: str | None = None,
    system_info: SystemInfo,
    brightness_samples: BrightnessSamples | None = None,
    masked_fallback_used: bool = False,
    warnings: list[MetadataWarning] | None = None,
    capture_regions: CaptureRegions | None = None,
    quiet: bool = False,
) -> None:
    """Split video and write metadata.json (#591: system_info required).

    ``detection_started_at`` / ``detection_completed_at`` (#586): both
    optional. ``None`` means「本ランで取得」(started = detected_at の値、
    completed = writer 直前の ``_iso_utc_now()``)。``run_split`` /
    ``run_detect`` は新規検知なので両方 ``None`` を渡し fresh capture を
    使う。``run_split_from_metadata`` は元 metadata の値を保持して GUI
    「所要」が「検知時の所要」を表示し続けるよう、明示的に値を渡す。
    """
    show = not quiet
    source_duration = metadata["duration"]
    if detection_started_at is None:
        detection_started_at = detected_at

    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise AllaganEyeError(
            f"Cannot create output directory {config.output_dir}: {e}"
        ) from e

    # #805 段階2: active (MP4 生成対象) と post_match (flag 方式、MP4 不生成) に分離。
    # post_match が無い場合は active == boundaries で現状と bit-exact。
    active_boundaries, post_match_boundaries = _partition_post_match(boundaries)

    # Split with progress bar (#331)
    if show:
        total = len(active_boundaries)
        with _eta_progressbar(total, "Splitting") as progress:

            def on_split_progress(completed: int, total: int) -> None:
                progress.update(1)

            output_files = split_video(
                video_path,
                active_boundaries,
                config.output_dir,
                progress_callback=on_split_progress,
            )
    else:
        output_files = split_video(video_path, active_boundaries, config.output_dir)

    # Write metadata (#463: ``note`` field retired; caveats documented in
    # docs/cli-spec.md and docs/metadata-spec.md instead of being embedded
    # in the payload). #586: completed_at は明示指定がなければ writer 直前
    # の ``_iso_utc_now()``。``--from-metadata`` 経路は元 metadata の値を
    # caller (run_split_from_metadata) が引き継いで渡す。
    if detection_completed_at is None:
        detection_completed_at = _iso_utc_now()
    result = _build_metadata_payload(
        video_path=video_path,
        source_duration=source_duration,
        source_fps=metadata["fps"],
        detected_at=detected_at,
        detection_started_at=detection_started_at,
        detection_completed_at=detection_completed_at,
        effective_interval=effective_interval,
        config=config,
        boundaries=active_boundaries,
        post_match_boundaries=post_match_boundaries,
        output_files=output_files,
        gaps=gaps,
        system_info=system_info,
        brightness_samples=brightness_samples,
        masked_fallback_used=masked_fallback_used,
        warnings=warnings,
        capture_regions=capture_regions,
    )
    metadata_path = config.output_dir / "metadata.json"
    write_metadata_atomic(metadata_path, result)

    typer.echo(f"\nOutput: {config.output_dir}")
    for f in output_files:
        typer.echo(f"  {f.name}")
    typer.echo(f"Metadata: {metadata_path}")


def _build_metadata_payload(
    *,
    video_path: Path,
    source_duration: float,
    source_fps: float,
    detected_at: str,
    detection_started_at: str,
    detection_completed_at: str,
    effective_interval: float,
    config: SplitConfig,
    boundaries: list[MatchBoundary],
    post_match_boundaries: list[MatchBoundary] | None = None,
    output_files: list[Path],
    gaps: list[Gap],
    system_info: SystemInfo,
    brightness_samples: BrightnessSamples | None = None,
    masked_fallback_used: bool = False,
    warnings: list[MetadataWarning] | None = None,
    capture_regions: CaptureRegions | None = None,
) -> Metadata:
    """Build the ``metadata.json`` payload dict (schema v1, #463 / #569 / #586 / #591 / #810).

    Kept private to this module; ``commands.detect`` builds a variant
    (no ``output_files``) via its own helper.

    ``schema_version`` (#515) declares the payload revision so future
    readers can migrate or refuse older / newer files. v1 is the current
    schema; see ``docs/metadata-spec.md`` section "schema_version".

    ``source_fps`` (#465 review): the recording frame rate from ffprobe.
    GUI uses this to compute frame-accurate +-1F seek (formerly assumed
    60 fps). 120fps / 240fps recordings now step by 1/120 / 1/240 sec.

    ``system_info`` (#591): GPU vendor probe snapshot used by GUI export
    encoder selection (NVENC / QSV / AMF / libx264). Optional field added
    in v1; readers without #591 simply ignore it. Build via
    ``_build_system_info``.

    ``detection_started_at`` / ``detection_completed_at`` (#586): wall-clock
    ISO 8601 UTC timestamps bracketing the detect (or detect-skipped split)
    pipeline. GUI ``CompleteScreen`` computes ``elapsed = completed -
    started`` to display the「所要」column. ``detection_started_at`` is the
    same value as ``detected_at`` (the legacy field is retained verbatim
    for backward compatibility); ``detection_completed_at`` is captured
    immediately before metadata.json is written.

    ``brightness_samples`` (#569): pre-rendered brightness timeline for
    the GUI complete screen.  Optional field; pre-#569 metadata files
    don't carry it.  Shape is ``{"interval_s": float, "values":
    list[float]}`` -- ``values[i]`` is the brightness (0-255) at
    ``i * interval_s`` seconds.  Built via :func:`build_brightness_samples`.

    The return type is the auto-generated ``Metadata`` TypedDict from
    ``allaganeye/metadata_types.py`` (regenerated from
    ``schemas/metadata.schema.json`` via ``python scripts/codegen/generate.py``,
    #612). Drift between this builder and the JSON Schema is caught
    statically by pyright.
    """
    # #805 段階2: post_match_boundaries が None のときは空リストで統一
    post_match_boundaries = post_match_boundaries or []
    payload: Metadata = {
        "schema_version": "1",
        "source": str(video_path),
        "source_duration": source_duration,
        "source_duration_display": _format_timestamp(source_duration),
        "source_fps": source_fps,
        "detected_at": detected_at,
        "detection_started_at": detection_started_at,
        "detection_completed_at": detection_completed_at,
        "detection_params": {
            "sample_interval": effective_interval,
            "blackout_threshold": config.blackout_threshold,
            "min_match_duration": config.min_match_duration,
            "min_blackout_duration": config.min_blackout_duration,
            "no_audio": config.no_audio,
            "use_gpu": config.use_gpu,
            "workers": config.workers,
            # vtuber/masked は検出 path の provenance (PR #823 R1 deferred 分)。
            # schema 上は optional (導入前 metadata との後方互換)。masked は
            # request flag、masked_fallback_used は resolved path (auto-fallback
            # 含む) で、両者は 0-blackout auto-trigger 時に乖離する (#821)。
            "vtuber": config.vtuber,
            "masked": config.masked,
            "masked_fallback_used": masked_fallback_used,
        },
        "system_info": system_info,
        # #805 段階2: active matches (output_file 有り) と post_match matches
        # (output_file 無し、post_match=True) を index 連番で結合。
        # list + list の型推論が dict[str, Unknown] になるため cast で Match に narrow。
        "matches": cast(
            "list[Match]",
            [
                {
                    "index": i + 1,
                    "start_time": b["start"],
                    "end_time": b["end"],
                    "start_display": _format_timestamp(b["start"]),
                    "end_display": _format_timestamp(b["end"]),
                    "duration": b["end"] - b["start"],
                    "duration_display": _format_duration(b["end"] - b["start"]),
                    # Narrow MatchBoundary's open-ended `type: str` (detector.py)
                    # to the JSON Schema literal so pyright accepts the assignment.
                    # Anything other than "fl_match" is normalized to "unknown"
                    # -- matches the prior dict.get fallback semantics.
                    "type": "fl_match" if b.get("type") == "fl_match" else "unknown",
                    "output_file": f.as_posix(),
                }
                for i, (b, f) in enumerate(zip(boundaries, output_files, strict=True))
            ]
            + [
                {
                    "index": len(boundaries) + j + 1,
                    "start_time": b["start"],
                    "end_time": b["end"],
                    "start_display": _format_timestamp(b["start"]),
                    "end_display": _format_timestamp(b["end"]),
                    "duration": b["end"] - b["start"],
                    "duration_display": _format_duration(b["end"] - b["start"]),
                    "type": "fl_match" if b.get("type") == "fl_match" else "unknown",
                    # #805 段階2: post_match segment は MP4 を生成しないため
                    # output_file は付けない (NotRequired)。post_match flag を付与。
                    "post_match": True,
                }
                for j, b in enumerate(post_match_boundaries)
            ],
        ),
        "gaps": [
            {
                "start_time": g["start"],
                "end_time": g["end"],
                "start_display": _format_timestamp(g["start"]),
                "end_display": _format_timestamp(g["end"]),
                "duration": g["duration"],
                "duration_display": _format_duration(g["duration"]),
            }
            for g in gaps
        ],
        # ``warnings`` defaults to None -> ``build_warnings()`` ([]) so existing
        # callers/tests stay byte-identical. A caller may still pass a pre-built
        # list (e.g. preserved from an older metadata.json) which is emitted
        # verbatim. #805 段階2 removed the only emitter (post_match_trailing_
        # dropped), so fresh-detection writes now always pass an empty list.
        "warnings": build_warnings() if warnings is None else warnings,
    }
    if brightness_samples is not None:
        payload["brightness_samples"] = brightness_samples
    # #810 -- capture region timeline。None (pre-#810 cache hit で領域未知の
    # 経路 / callback 未発火) では key 自体を省略する (brightness_samples と同型)。
    if capture_regions is not None:
        payload["capture_regions"] = capture_regions
    return payload


_BRIGHTNESS_TIMELINE_TARGET_SAMPLES = 512
"""Target sample count for the GUI complete-screen timeline (#569).

512 keeps the SVG path lightweight (well under the WebKit path-length
limit on Windows + matches the existing dummy ``buildSampleBrightness``
in the design prototype) while still capturing a 2:50 hour recording at
~20 second granularity -- fine enough that match boundaries land on a
distinct sample in practice.
"""


def build_brightness_samples(
    raw_brightness: dict[float, float],
    *,
    target_samples: int = _BRIGHTNESS_TIMELINE_TARGET_SAMPLES,
) -> BrightnessSamples | None:
    """Down-sample a Pass 1 ``{timestamp: brightness}`` map for metadata.json (#569).

    The GUI complete screen draws a brightness timeline whose width is
    fixed (~700px); rendering every probe (potentially tens of thousands
    on a 3-hour video) would bloat metadata.json and yield more SVG path
    points than the WebView can stroke smoothly.  We linearly stride the
    sorted timestamps so the resulting array is at most
    ``target_samples`` entries while preserving the start / end shape.

    Returns ``None`` for empty input so callers can ``if samples is None:
    skip`` rather than write a degenerate ``{interval_s: 0, values: []}``
    object.
    """
    if not raw_brightness:
        return None
    timestamps = sorted(raw_brightness.keys())
    n = len(timestamps)
    stride = max(1, n // max(1, target_samples))
    selected = timestamps[::stride]
    if not selected:
        return None
    if len(selected) >= 2:
        interval_s = float(selected[1] - selected[0])
    else:
        interval_s = float(timestamps[-1]) if timestamps[-1] > 0 else 1.0
    values = [round(float(raw_brightness[t]), 3) for t in selected]
    return {
        "interval_s": round(interval_s, 6),
        "values": values,
    }


def _print_environment_header(
    output_dir: Path | None = None,
) -> None:
    """Print environment info header for -v mode (#336 Phase 1 + #377 Phase 2).

    Phase 1 line: allaganeye / ffmpeg / Python / OS (unchanged).
    Phase 2 lines: CPU, GPU, memory, and disk (where the output will be
    written) -- each best-effort, each gracefully degrades to
    ``"(unavailable)"`` without aborting the split.
    """
    import platform

    from allaganeye import __version__
    from allaganeye.system_info import (
        get_cpu_info,
        get_disk_info,
        get_gpu_info_lines,
        get_memory_info,
        gpu_vendor_probe_warning,
    )

    ffmpeg_version = _probe_ffmpeg_version()
    typer.echo(
        f"allaganeye {__version__} "
        f"(ffmpeg {ffmpeg_version}, "
        f"Python {platform.python_version()}, "
        f"{platform.system()} {platform.release()})"
    )
    typer.echo(f"  CPU: {get_cpu_info()}")
    gpus = get_gpu_info_lines()
    if not gpus:
        typer.echo("  GPU: (unavailable)")
    elif len(gpus) == 1:
        typer.echo(f"  GPU: {gpus[0]}")
    else:
        typer.echo("  GPU:")
        for gpu in gpus:
            typer.echo(f"    - {gpu}")
    gpu_warning = gpu_vendor_probe_warning()
    if gpu_warning is not None:
        typer.echo(f"  ! {gpu_warning}")
    typer.echo(f"  Memory: {get_memory_info()}")
    disk_target = output_dir if output_dir is not None else Path.cwd()
    typer.echo(f"  Disk: {get_disk_info(disk_target)}")


_FFMPEG_VERSION_RE = re.compile(r"^[nv]?(\d+\.\d+(?:\.\d+)?)")
"""Strip ``n`` / ``v`` / ``git-`` prefixes and build-metadata suffixes from
ffmpeg version strings, keeping only ``major.minor[.patch]`` (#383).

Handles common shapes:
  - ``8.1-full_build-www.gyan.dev``  -> ``8.1``
  - ``n7.1``                          -> ``7.1``
  - ``4.4.2-0ubuntu0.22.04.1``        -> ``4.4.2``
  - ``git-2023-01-01-abcdef``         -> no match, caller keeps raw
"""


def _probe_ffmpeg_version() -> str:
    """Return ffmpeg ``major.minor[.patch]`` version, or '(unknown)' on failure.

    Build-metadata and distributor suffixes (``-full_build-www.gyan.dev``,
    ``-0ubuntu0.22.04.1``, etc.) are stripped so the verbose header stays
    concise (#383).  If the prefix doesn't match the expected numeric
    pattern, the raw token is returned as a fallback.
    """
    import subprocess

    from allaganeye.ffmpeg_path import find_ffmpeg

    try:
        result = subprocess.run(
            [find_ffmpeg(), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "(unknown)"

    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    # "ffmpeg version 8.1-essentials_build-www.gyan.dev Copyright ..."
    parts = first_line.split()
    if len(parts) >= 3 and parts[0] == "ffmpeg" and parts[1] == "version":
        raw = parts[2]
        match = _FFMPEG_VERSION_RE.match(raw)
        return match.group(1) if match else raw
    return "(unknown)"


def _emit_splitting_elapsed(
    split_start: float, match_count: int, verbose: bool, show: bool
) -> None:
    """Emit ``  Splitting: N matches, Xs`` for verbose stats (#387).

    Called from ``run_split`` after ``_split_and_write_metadata`` returns so
    users can see the split phase's standalone cost instead of inferring it
    from ``Total - (Pass 1 + Pass 2 + Scorebar)``.  Printed on both the
    cached and cache-miss paths so the number is always surfaced.
    """
    if verbose and show:
        elapsed = time.monotonic() - split_start
        typer.echo(f"  Splitting: {match_count} matches, {_format_duration(elapsed)}")


def _print_detection_stats(stats: DetectionStats) -> None:
    """Emit pipeline statistics in verbose mode (issue #336 Phase 1)."""
    mode = stats.get("mode")
    if mode is not None:
        pass1_samples = stats.get("pass1_samples", 0)
        pass1_blackouts = stats.get("pass1_blackout_frames", 0)
        pass1_elapsed = stats.get("pass1_elapsed_s", 0.0)
        blackout_pct = 100.0 * pass1_blackouts / pass1_samples if pass1_samples else 0.0
        typer.echo(
            f"  Pass 1 ({mode}): {pass1_samples} samples, "
            f"{pass1_blackouts} blackout frames ({blackout_pct:.1f}%), "
            f"{_format_duration(pass1_elapsed)}"
        )

    if "pass2_regions" in stats:
        pass2_elapsed = stats.get("pass2_elapsed_s", 0.0)
        typer.echo(
            f"  Pass 2: {stats['pass2_regions']} regions refined, "
            f"{_format_duration(pass2_elapsed)}"
        )

    if any(
        k in stats
        for k in (
            "scorebar_match_boundary",
            "scorebar_in_match",
            "scorebar_non_fl",
            "scorebar_unknown",
        )
    ):
        parts = [
            f"{stats.get('scorebar_match_boundary', 0)} match_boundary",
            f"{stats.get('scorebar_in_match', 0)} in_match",
            f"{stats.get('scorebar_non_fl', 0)} non_fl",
        ]
        unknown = stats.get("scorebar_unknown", 0)
        if unknown:
            parts.append(f"{unknown} unknown")
        # Append elapsed time when available (#386) for symmetry with
        # Pass 1 / Pass 2.  Gate on presence so tests that don't populate
        # the key still render a clean "X match_boundary, ..." line.
        scorebar_elapsed = stats.get("scorebar_elapsed_s")
        if scorebar_elapsed is not None:
            parts.append(_format_duration(scorebar_elapsed))
        typer.echo(f"  Scorebar: {', '.join(parts)}")

    promotions = stats.get("audio_promotions")
    if promotions is not None and promotions > 0:
        typer.echo(f"  Audio promotion: {promotions} in_match -> match_boundary")

    # Filter drop breakdown (#388): why candidates -> matches shrank.
    # scorebar in_match / non_fl counts stay on the Scorebar line above;
    # this section captures duration-based drops (below_min_match_duration
    # and residual "other") so users can tune --min-match-duration.
    candidates = stats.get("filter_candidates")
    drops = stats.get("filter_drops")
    # Skip the section entirely when there are no real candidates *and*
    # no drops: the match came from the whole-video fallback path, so
    # ``Filter: 0 candidates -> 0 matches`` would be misleading noise.
    if (
        candidates is not None
        and drops is not None
        and (candidates > 0 or sum(drops.values()) > 0)
    ):
        kept = candidates - sum(drops.values())
        typer.echo(f"  Filter: {candidates} candidates -> {kept} matches")
        # Emit only non-zero categories so the output stays terse on
        # healthy runs; zero-row lines would be noise.
        if drops.get("below_min_match_duration", 0) > 0:
            typer.echo(
                f"    {drops['below_min_match_duration']} dropped "
                f"(below min_match_duration)"
            )
        if drops.get("other", 0) > 0:
            typer.echo(f"    {drops['other']} dropped (other)")

    masked_dropped = stats.get("masked_segments_dropped", 0)
    if masked_dropped > 0:
        typer.echo(
            f"  masked L2 validation: {masked_dropped} segment(s) dropped"
            " (below quorum)"
        )

    masked_merges = stats.get("masked_l2_zero_gap_merges", 0)
    if masked_merges > 0:
        typer.echo(
            f"  masked L2 zero-gap merge: {masked_merges} pair(s) merged"
            " (flank flicker split)"
        )

    # Unknown match accounting (#433): recordings starting / ending mid-match
    # produce ``type=unknown`` segments at the timeline edges. They are part
    # of Detected count but not of the Filter "kept" formula (candidates
    # counts blackout boundaries, not edge segments), so without this line
    # users see Filter=N / Detected=N+1 and assume a counting bug.
    unknown_count = stats.get("filter_unknown", 0)
    if unknown_count > 0:
        label = "match" if unknown_count == 1 else "matches"
        typer.echo(f"  + {unknown_count} unknown {label} (録画途中試合)")

    # VTuber timeline stats (#895 P2): only present on --vtuber path; OBS run
    # has no vtuber_timeline_probes key and this block is entirely skipped.
    if "vtuber_timeline_probes" in stats:
        typer.echo(
            f"  Timeline (vtuber): {stats['vtuber_timeline_probes']} probes, "
            f"anchor conf {stats.get('vtuber_anchor_confidence', 0.0):.2f}"
        )
        typer.echo(
            f"  V3: {stats.get('vtuber_gaps_tested', 0)} gaps tested, "
            f"{stats.get('vtuber_gaps_merged', 0)} merged; "
            f"V4: {stats.get('vtuber_v4_dropped', 0)} dropped, "
            f"{stats.get('vtuber_low_confidence_segments', 0)} low-confidence"
        )


def _format_eta(seconds: float) -> str:
    """Format an ETA for in-label display (compact, e.g. '45s' or '3m20s').

    Designed for the GPU chunk progress label (#333).  Keeps width small
    so the progress bar does not overflow typical terminal widths.
    """
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    m, s = divmod(total, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _emit_total_time(total_start: float, verbose: bool, show: bool) -> None:
    """Print ``Total: HH:MM:SS`` wall-clock for the split pipeline (#381).

    Emitted on every verbose-visible exit path (cache hit + split, cache hit
    + dry-run, cache miss + split, cache miss + dry-run) so users always see
    how long the run took regardless of which branch executed.
    """
    if verbose and show:
        typer.echo(f"Total: {_format_duration(time.monotonic() - total_start)}")


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
    *,
    masked_fallback_used: bool = False,
    capture_regions: "CaptureRegions | None" = None,
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
            "vtuber": config.vtuber,
            "masked": config.masked,
            "keep_trailing": config.keep_trailing,
            "masked_algo": _MASKED_ALGO_VERSION,
            "vtuber_algo": _VTUBER_ALGO_VERSION,
        },
        # resolved path は key (params) ではなく top-level に記録する: auto-masked
        # 動画の cache 再利用は request flag の一致で正しく機能させ、provenance
        # は表示/metadata 引き継ぎ用に保持する (#821)。
        "masked_fallback_used": masked_fallback_used,
        "boundaries": boundaries,
    }
    # #810: None は key 省略 (null を書かない) -- metadata.json と同じ省略 semantics
    # (read 側は key 欠落を legacy と同じ合成ロジックで扱う)。
    if capture_regions is not None:
        cache_data["capture_regions"] = capture_regions
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        logger.debug("Failed to write detection cache to %s", cache_path)


def _read_cached_masked_fallback(cache_path: Path) -> bool:
    """cache-hit 経路用: cache に記録された resolved masked fallback を読む。

    読めない / 欠落時は False (標準 path 扱い)。cache key の一部ではないため
    `_load_cache` とは独立に読む (#821)。
    """
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("masked_fallback_used", False))


_CAPTURE_REGIONS_TOP_KEYS = frozenset({"coarse", "segments", "fallback_reason"})
_CAPTURE_REGION_COORD_KEYS = frozenset({"x", "y", "w", "h", "confidence"})
_CAPTURE_REGION_REQUIRED_KEYS = frozenset({"x", "y", "w", "h", "confidence", "source"})


def _sanitize_capture_regions(value: object) -> "CaptureRegions | None":
    """Structural sanitizer for a CaptureRegions payload read from metadata.json or cache.

    Mirrors the CaptureRegions shape in schemas/metadata.schema.json with a
    pure-Python check (no jsonschema runtime dependency). Returns the value cast
    to CaptureRegions when fully valid, else None.

    Validity contract (strict writer contract, additionalProperties:false equivalent):
    - value is a dict with exactly the keys {coarse, segments, fallback_reason}.
    - coarse is a dict with exactly the keys {x, y, w, h, confidence, source};
      x/y/w/h/confidence are real numbers (int or float; bool is explicitly rejected)
      in [0, 1]; source is a non-empty str.
    - segments is a list; each entry is a dict with exactly {time_range, region};
      time_range is a list of exactly 2 finite real numbers each >= 0
      (NaN / +-Infinity は reject -- round-3 R3-1: ``json.dumps`` は
      allow_nan=True で非標準 token を再 emit し、strict reader (GUI serde_json /
      JSON.parse) が metadata.json 全体を reject するため sanitize 側で塞ぐ);
      region follows the same rules as coarse.
    - fallback_reason is a str or None (free string, any value OK).

    Pattern and docstring style mirrors sanitize_warnings in
    allaganeye/detection/warnings.py.
    codex adversarial-review F1 (2026-07-07 Idios confirmed):
    malformed preserve -> sanitize + omit + warning (sanitize_warnings #805 same pattern).
    """
    if not isinstance(value, dict):
        return None
    if set(value.keys()) != _CAPTURE_REGIONS_TOP_KEYS:
        return None

    coarse = value.get("coarse")
    if not _is_valid_capture_region(coarse):
        return None

    segments = value.get("segments")
    if not isinstance(segments, list):
        return None
    for seg in segments:
        if not isinstance(seg, dict):
            return None
        if set(seg.keys()) != {"time_range", "region"}:
            return None
        tr = seg.get("time_range")
        if not isinstance(tr, list) or len(tr) != 2:
            return None
        for t in tr:
            if (
                isinstance(t, bool)
                or not isinstance(t, (int, float))
                or not math.isfinite(t)
                or t < 0
            ):
                return None
        if not _is_valid_capture_region(seg.get("region")):
            return None

    fallback_reason = value.get("fallback_reason")
    if fallback_reason is not None and not isinstance(fallback_reason, str):
        return None

    return cast("CaptureRegions", value)


def _is_valid_capture_region(region: object) -> bool:
    """Return True iff region is a well-formed CaptureRegion dict.

    Helper for _sanitize_capture_regions. Checks exact key set, numeric
    coordinates in [0, 1] (bool explicitly rejected), and non-empty source str.
    """
    if not isinstance(region, dict):
        return False
    if set(region.keys()) != _CAPTURE_REGION_REQUIRED_KEYS:
        return False
    for key in _CAPTURE_REGION_COORD_KEYS:
        v = region[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if not (0.0 <= v <= 1.0):
            return False
    source = region.get("source")
    if not isinstance(source, str) or not source:
        return False
    return True


def _read_cached_capture_regions(cache_path: Path) -> "CaptureRegions | None":
    """cache-hit 経路用: cache に記録された capture region timeline を読む (#810).

    pre-#810 legacy cache (field なし / explicit null) は、cache 記録の
    params.vtuber == False かつ masked_fallback_used == False なら標準 path 確定
    (領域は決定的に FULL_FRAME) なので合成して返す。vtuber / masked fallback 採用
    の legacy cache は領域が未知のため None (metadata では field 省略 = 領域不明を
    偽装しない)。

    合成条件に params.masked (request flag) を含めないのは意図的 (round-2 codex
    裁定 2026-07-07): (a) ``"masked"`` cache param と ``masked_fallback_used``
    記録は同一 commit (PR #826) で共導入のため「masked=True だが resolved flag
    未記録」の cache は歴史的に存在しない、(b) masked 要求で fallback 不採用
    (mask 不発見) の run は標準 path が FULL_FRAME で Pass 1 計測しているため、
    合成は決定的に正。resolved flag (masked_fallback_used) が正の述語。

    cache に capture_regions が present (非 null) な場合は _sanitize_capture_regions
    で shape 検証する: valid -> そのまま返す; invalid -> logger.warning + None 返す。
    present-but-garbage は "cache が破損/改竄" を意味し FULL_FRAME 合成に fall-through
    しない (present-but-garbage != legacy absent = 標準 path 確定)。

    cache が読めないときも None。`_load_cache` の hit 判定とは独立に読む
    (`_read_cached_masked_fallback` と同型)。
    codex adversarial-review F1 (2026-07-07 Idios confirmed): sanitize hardening.
    """
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cached = data.get("capture_regions")
    if cached is not None:
        # present value: sanitize. invalid means cache corruption/tampering;
        # do NOT fall through to FULL_FRAME synthesis.
        sanitized = _sanitize_capture_regions(cached)
        if sanitized is None:
            logger.warning(
                "Dropping malformed capture_regions from cache %s "
                "(corrupted or hand-edited cache value -- region unknown)",
                cache_path,
            )
        return sanitized
    # cached is None: key absent or explicit null -- legacy absent semantics.
    params = data.get("params", {})
    if not params.get("vtuber", False) and not data.get("masked_fallback_used", False):
        return cast("CaptureRegions", RegionTimeline(coarse=FULL_FRAME).to_dict())
    return None


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
    # vtuber / masked は detection path を切り替え、keep_trailing は trailing-drop
    # を skip して検出境界を変える (#805 段階1) ため、いずれも cache key に含める
    # (gate / opt-out の cache bypass 防止)。key なし legacy cache は各 flag 導入前
    # の結果 (vtuber/masked=標準 path、keep_trailing=drop ON) なので False と同値に
    # 扱う。
    if (
        params.get("sample_interval") != effective_interval
        or params.get("blackout_threshold") != config.blackout_threshold
        or params.get("min_match_duration") != config.min_match_duration
        or params.get("min_blackout_duration") != config.min_blackout_duration
        or params.get("no_audio") != config.no_audio
        or params.get("vtuber", False) != config.vtuber
        or params.get("masked", False) != config.masked
        or params.get("keep_trailing", False) != config.keep_trailing
    ):
        logger.debug("Cache parameter mismatch")
        return None

    # masked_algo key: invalidate only when masked algorithm changes AND the
    # cached run was masked-affected (params.masked=True or auto-fallback used).
    # Legacy OBS caches (fallback unused + masked off) hit regardless of key
    # absence -- no needless re-detects for unaffected users.
    # Values that fail int() coercion (broken cache) are treated as mismatch
    # (miss direction); int-coercible values compare by numeric equality.
    _raw_cached_algo = params.get("masked_algo", 1)
    try:
        cached_algo = int(_raw_cached_algo)
    except (ValueError, TypeError):
        cached_algo = -1  # forces miss for any valid _MASKED_ALGO_VERSION
    masked_affected = (
        data.get("masked_fallback_used", False)
        or params.get("masked", False)
        or config.masked
    )
    if masked_affected and cached_algo != _MASKED_ALGO_VERSION:
        logger.debug("Cache masked algo mismatch")
        return None

    # vtuber_algo key: invalidate only when vtuber algorithm changes AND the
    # cached run was vtuber-affected (params.vtuber=True or config.vtuber=True).
    # Legacy OBS caches (vtuber off) hit regardless of key absence -- no
    # needless re-detects for unaffected users (same invalidation policy as
    # masked_algo).
    _raw_cached_vtuber_algo = params.get("vtuber_algo", 1)
    try:
        cached_vtuber_algo = int(_raw_cached_vtuber_algo)
    except (ValueError, TypeError):
        cached_vtuber_algo = -1  # forces miss for any valid _VTUBER_ALGO_VERSION
    vtuber_affected = params.get("vtuber", False) or config.vtuber
    if vtuber_affected and cached_vtuber_algo != _VTUBER_ALGO_VERSION:
        logger.debug("Cache vtuber algo mismatch")
        return None

    boundaries = data.get("boundaries")
    if not isinstance(boundaries, list):
        logger.debug("Cache boundaries invalid")
        return None

    return boundaries
