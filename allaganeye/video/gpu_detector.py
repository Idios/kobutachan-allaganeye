"""GPU-accelerated match detection using chunked parallel ffmpeg decode."""

import logging
import math
import os
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.video.detector import (
    _FRAME_SIZE,
    _SAMPLE_HEIGHT,
    _SAMPLE_WIDTH,
    _generate_timestamps,
)

logger = logging.getLogger(__name__)

# Target wall-time per chunk for dynamic chunk sizing (#437).
# Long videos would otherwise wait 2-3 minutes before the first chunk
# completes with the old fixed 16 chunks; chopping into smaller pieces
# lets the progress bar label update more frequently.
_TARGET_CHUNK_WALL_SECS = 90.0

# Upper bound on the number of chunks (#437). Too many chunks pay fixed
# ffmpeg startup cost per chunk and can overwhelm GPU scheduling.
_MAX_CHUNKS = 32

_GPU_DECODER_MAP: dict[str, dict[str, str]] = {
    "nvidia": {
        "h264": "h264_cuvid",
        "hevc": "hevc_cuvid",
        "av1": "av1_cuvid",
        # vp9: #538 / #549 で除外。ffmpeg 8.1 の vp9_cuvid が
        # nv12 + csp:gbr を出力し swscaler gray 変換が
        # EOPNOTSUPP で失敗するため、NVIDIA 経路から外す。
        # soft decode (else branch -hwaccel auto) は実測
        # speed 2.64x で chunk 並列に十分。ffmpeg 側の修正が
        # 入った時点で復活検討。
        "vp8": "vp8_cuvid",
        "mpeg1video": "mpeg1_cuvid",
        "mpeg2video": "mpeg2_cuvid",
        "mpeg4": "mpeg4_cuvid",
    },
    "amd": {
        # AMD は AMF decoder ではなく d3d11va 経由で native decoder を
        # ハードウェア化する (#553 結論)。AMF decoder の出力 pix_fmt
        # `amf` は swscaler と不整合で `fps -> scale -> format=gray` が
        # EOPNOTSUPP で fail するが、d3d11va は GPU 上 D3D11 surface に
        # decode したあと filter graph 先頭の `hwdownload,format=nv12,...`
        # で system memory に降ろせるので allaganeye の filter pipeline と
        # 相性が取れる。
        "h264": "h264",
        "hevc": "hevc",
        "av1": "av1",
        # vp9 / mpeg* も d3d11va で動作可能だが OBS 録画では稀なので
        # 現状未登録。必要になったら追加。
    },
    "intel": {
        # #550 で追加。Tiger Lake (11th gen Iris Xe) 以降は
        # h264 / hevc / av1 を QSV decode 可能。`_HWACCELS_NEED_HWDOWNLOAD`
        # に "qsv" を追加してあるので _decode_chunk が
        # `-hwaccel_output_format qsv` + filter chain 先頭の
        # `hwdownload,format=nv12,` を自動付与し、QSV surface を system
        # memory に降ろしてから fps -> scale -> format=gray に渡す。
        # VP9 は QSV decoder 自体は ffmpeg 8.1 に存在 (`vp9_qsv`) するが
        # 本 issue ではスコープ外で除外 (将来別 issue で追加検討)。
        # 古い世代 (Skylake 等) で av1_qsv が「unsupported (-3)」で
        # 失敗するケースは _decode_chunk が VideoProcessingError を上げ、
        # detect_match_boundaries が CPU fallback する (実機検証:
        # i7-1185G7 / Iris Xe では av1_qsv 非対応で CPU fallback 動作確認済み)。
        "h264": "h264_qsv",
        "hevc": "hevc_qsv",
        "av1": "av1_qsv",
    },
}

_VENDOR_HWACCEL_MAP: dict[str, str] = {
    "nvidia": "cuda",
    "amd": "d3d11va",  # #553 generic D3D11 hwaccel + native decoder
    "intel": "qsv",  # #550 Intel Quick Sync Video
}

_HWACCELS_NEED_HWDOWNLOAD: frozenset[str] = frozenset({"d3d11va", "qsv"})
"""GPU memory に decode する hwaccel 一覧 (#553 / #550).

これらの hwaccel は decoded frame を GPU surface のまま filter graph
に送り込むため、CPU 側で動く ``fps``/``scale``/``format=gray`` filter に
渡す前に ``hwdownload,format=nv12,`` を filter chain 先頭に挿入する
必要がある。NVIDIA CUVID decoder (e.g. ``av1_cuvid``) は decode 結果を
nv12 system memory に直接出力するため不要。

`-hwaccel_output_format` の値は hwaccel 名と一致させる:
- d3d11va -> ``d3d11`` (#553)
- qsv -> ``qsv`` (#550)。実機検証 (i7-1185G7 / Iris Xe) で h264_qsv 13.7x speed。
  ``-hwaccel_output_format nv12`` 直指定でも動くが、d3d11va と同じ
  パターンに揃え hwdownload filter で system memory に降ろす方が
  vendor 間の挙動を一本化できる
"""

_VENDOR_PREFERENCE: tuple[str, ...] = ("nvidia", "amd", "intel")
"""Auto-select 時の vendor 優先順 (#546 / #553 / #550). dGPU (NVIDIA) を最優先、
次に AMD (#553 / #578 で d3d11va 経由実装済み), 最後に Intel
(#550 で QSV 経由実装済み)。3 vendor すべて _VENDOR_HWACCEL_MAP に登録済みで
auto-select の対象。NVIDIA dGPU + Intel iGPU / AMD APU + Intel iGPU のような
組み合わせでは preference 順で上位 vendor が選ばれる。"""

_HWACCEL_OUTPUT_FORMAT_MAP: dict[str, str] = {
    # `-hwaccel_output_format` の値マップ (#553 / #550)。
    # `_HWACCELS_NEED_HWDOWNLOAD` の各 hwaccel に対応する surface format。
    # ffmpeg は `-hwaccel <X> -hwaccel_output_format <Y>` の <Y> として
    # hwaccel 自身の surface format 名 (d3d11 / qsv 等) を要求する。
    "d3d11va": "d3d11",
    "qsv": "qsv",
}

# Backward-compat alias: 既存の `_CUVID_CODEC_MAP` 参照 (テスト等) を
# 壊さないため NVIDIA 用 dict を指す。新規コードは `_GPU_DECODER_MAP`
# を使用 (#546)。L3 以降で削除検討。
_CUVID_CODEC_MAP: dict[str, str] = _GPU_DECODER_MAP["nvidia"]


def _select_gpu_vendor(
    requested: str | None,
    available: list[str],
    *,
    preference: tuple[str, ...] = _VENDOR_PREFERENCE,
) -> str | None:
    """Resolve the vendor to use (#546).

    - ``requested`` が ``None`` / ``"auto"``: ``available`` x ``preference``
      かつ実装済み (``_VENDOR_HWACCEL_MAP`` に含まれる) の最上位を選ぶ。
    - ``requested`` が explicit vendor: ``available`` に含まれればそれを
      返す。含まれなければ ``None`` (呼び出し側で ConfigValidationError)。
    """
    if not requested or requested == "auto":
        for pref in preference:
            if pref in available and pref in _VENDOR_HWACCEL_MAP:
                return pref
        return None
    if requested in available:
        return requested
    return None


def scan_gpu(
    video_path: Path,
    duration: float,
    sample_interval: float,
    blackout_threshold: float,
    progress_callback: Callable[[int, int, int], None] | None = None,
    codec: str | None = None,
    chunk_progress_callback: Callable[[int, int, float], None] | None = None,
    chunk_dispatch_callback: Callable[[int], None] | None = None,
    vendor: str | None = None,
) -> dict[float, float]:
    """GPU mode: chunked parallel decode with cuvid hardware decoder.

    Splits the video timeline into chunks and runs one long-lived ffmpeg
    process per chunk with GPU-accelerated decoding.  Each process uses
    ``fps=1/{interval}`` to output one frame per interval, which is read
    from stdout and analyzed for brightness.

    Returns dict mapping timestamp -> brightness, same as CPU mode.

    ``chunk_progress_callback`` is called as ``(done, total, eta_seconds)``
    each time a chunk completes.  ETA is derived from the average
    per-chunk wall time so it becomes accurate after the first few
    completions.  Emitted BEFORE the per-frame ``progress_callback``
    burst so the UI label updates before the bar jumps (#333).

    ``chunk_dispatch_callback`` is called once with the final chunk count
    immediately BEFORE the decode threads start, so the caller can show
    "[dispatching N chunks, first result pending...]" while users wait
    for the first chunk to complete (#437, which was an incomplete fix
    for #333 on long videos).

    Chunk count scales with duration: long videos are broken into more
    pieces so the UI label updates every ~90s wall time (controlled by
    ``_TARGET_CHUNK_WALL_SECS``) capped at ``_MAX_CHUNKS``.  Short videos
    keep the historical behavior (``min(cpu_count, 16)``) so their
    dispatch overhead isn't inflated.

    Raises VideoProcessingError if GPU decode fails for all chunks.
    """
    # Parallelism cap: number of ffmpeg processes running concurrently.
    # Bounded by CPU count and 16 to keep GPU memory pressure sane.
    max_parallel = min(os.cpu_count() or 4, 16)
    # Chunk count: may exceed ``max_parallel`` for long videos, in which
    # case chunks are processed in waves.  More chunks = more label
    # updates during Pass 1 (#437).
    target_from_duration = (
        math.ceil(duration / _TARGET_CHUNK_WALL_SECS) if duration > 0 else 1
    )
    num_chunks = min(max(max_parallel, target_from_duration), _MAX_CHUNKS)
    chunk_duration = duration / num_chunks

    # Pre-compute the global sample grid (same one ``_scan_cpu`` uses) so
    # GPU and CPU agree on the keys of the resulting dict (#392).  We
    # still let each chunk's ffmpeg process use its native off-grid
    # ``-ss chunk_start`` (to keep chunk boundaries balanced) but map
    # the N-th emitted frame to the N-th pre-assigned grid timestamp --
    # exactly the same labeling trick ``_decode_chunk_cpu`` uses.  Before
    # this change, GPU labeled frames with ``chunk_start + k*interval``
    # which is off-grid for chunks whose start isn't a multiple of
    # ``sample_interval``; downstream grouping then saw different
    # blackout region boundaries from CPU, causing #392's 1m47s miss.
    global_grid = _generate_timestamps(duration, sample_interval)
    chunks: list[tuple[float, float, list[float]]] = []
    for i in range(num_chunks):
        chunk_start = i * chunk_duration
        chunk_end = min((i + 1) * chunk_duration, duration)
        chunk_timestamps = [t for t in global_grid if chunk_start <= t < chunk_end]
        if chunk_timestamps:
            chunks.append((chunk_start, chunk_end, chunk_timestamps))

    # Chunks without any grid point (very short videos) are dropped, so
    # report the actual dispatched count via progress_callback.
    num_chunks = len(chunks) if chunks else 1

    total_expected = len(global_grid) or 1
    results: dict[float, float] = {}
    blackout_count = 0
    completed = 0
    gpu_failed = False
    fallback_checked = False

    # Resolve decoder for the selected vendor (#546). Falls back to the
    # legacy NVIDIA-only map when ``vendor`` is None so existing callers
    # (unit tests that invoke scan_gpu without vendor) keep working.
    vendor_map = _GPU_DECODER_MAP.get(vendor or "nvidia", _GPU_DECODER_MAP["nvidia"])
    hw_decoder = vendor_map.get(codec or "")
    scan_start = time.monotonic()
    chunks_done = 0

    # #437: Notify the UI layer BEFORE any chunk starts so long-video
    # users see movement (label update) instead of 0% stall for 2-3
    # minutes while the first chunk decodes.
    if chunk_dispatch_callback is not None:
        chunk_dispatch_callback(num_chunks)

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {
            pool.submit(
                _decode_chunk,
                video_path,
                chunk_start,
                chunk_end,
                sample_interval,
                codec,
                chunk_timestamps,
                vendor,
            ): (chunk_start, chunk_end)
            for chunk_start, chunk_end, chunk_timestamps in chunks
        }
        for future in as_completed(futures):
            chunk_start, chunk_end = futures[future]
            try:
                chunk_results, stderr_text = future.result()
            except VideoProcessingError:
                gpu_failed = True
                pool.shutdown(wait=False, cancel_futures=True)
                break

            # Check GPU usage from the first completed chunk
            if not fallback_checked:
                fallback_checked = True
                _check_gpu_usage(stderr_text, codec, hw_decoder)

            chunks_done += 1
            if chunk_progress_callback is not None:
                elapsed = time.monotonic() - scan_start
                remaining = num_chunks - chunks_done
                # Linear extrapolation from completion ratio.  Chunks run
                # in parallel but have similar sizes, so the rate at which
                # they finish is a reasonable proxy for remaining wall
                # time.  Conservative (overshoots slightly near the start,
                # accurate near the end) -- users prefer that to overshoot.
                eta = elapsed * remaining / chunks_done if remaining > 0 else 0.0
                chunk_progress_callback(chunks_done, num_chunks, eta)

            for t, brightness in chunk_results.items():
                results[t] = brightness
                completed += 1
                if brightness < blackout_threshold:
                    blackout_count += 1
                if progress_callback is not None:
                    progress_callback(completed, total_expected, blackout_count)

    if gpu_failed:
        raise VideoProcessingError("GPU decode failed, falling back to CPU")

    # #439: Force the progress bar to 100% when GPU chunk-boundary
    # rounding leaves a few frames short of ``total_expected``.  Without
    # this emit, the Detecting bar freezes at 99% until Refining opens
    # on the next line -- cosmetic but confusing.
    if progress_callback is not None and completed < total_expected:
        dropped = total_expected - completed
        logger.info(
            "GPU decode returned %d of %d frames (%d boundary drop(s))",
            completed,
            total_expected,
            dropped,
        )
        progress_callback(total_expected, total_expected, blackout_count)

    return results


def _check_gpu_usage(
    stderr_text: str, codec: str | None, cuvid_decoder: str | None
) -> None:
    """Log GPU decode status based on ffmpeg stderr output."""
    lowered = stderr_text.lower()
    if cuvid_decoder and cuvid_decoder in stderr_text:
        logger.info("GPU decode active: %s", cuvid_decoder)
    elif "d3d11va" in lowered:
        logger.info("GPU decode active (d3d11va)")
    elif "qsv" in lowered:
        logger.info("GPU decode active (qsv)")
    elif "hwaccel" in lowered or "cuda" in lowered:
        logger.info("GPU decode active (hwaccel auto)")
    else:
        logger.warning(
            "GPU acceleration not active for codec '%s', falling back to CPU decode",
            codec or "unknown",
        )


def _decode_chunk(
    video_path: Path,
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    codec: str | None = None,
    chunk_timestamps: list[float] | None = None,
    vendor: str | None = None,
) -> tuple[dict[float, float], str]:
    """Decode a single chunk using GPU-accelerated ffmpeg.

    Returns ``(results_dict, stderr_text)`` so the caller can inspect
    GPU usage from the first completed chunk.

    When *chunk_timestamps* is supplied, the N-th emitted frame is mapped
    to ``chunk_timestamps[N]`` (the global sample grid) instead of
    ``chunk_start + N*sample_interval`` (#392).  Mirrors
    ``_decode_chunk_cpu``'s labeling so CPU and GPU produce dicts keyed
    identically on the same physical content.  Falls back to the chunk-
    local formula when ``chunk_timestamps`` is None for backwards
    compatibility with the unit tests that invoke the function directly.

    When *vendor* is provided (#546), the ffmpeg command uses the
    vendor-specific decoder (e.g. ``-hwaccel qsv -c:v av1_qsv``).  When
    vendor is None, falls back to the legacy NVIDIA CUVID path to keep
    existing unit tests working.

    For hwaccels in ``_HWACCELS_NEED_HWDOWNLOAD`` (currently d3d11va #553
    and qsv #550), ffmpeg outputs frames to a GPU surface rather than
    system memory.  The wrapper then adds
    ``-hwaccel_output_format <surface_fmt>`` (mapped via
    ``_HWACCEL_OUTPUT_FORMAT_MAP``) and prepends ``hwdownload,format=nv12,``
    to the ``-vf`` chain so the subsequent fps/scale/format=gray filters
    receive system-memory nv12 frames.
    """
    chunk_duration = chunk_end - chunk_start
    fps_value = 1.0 / sample_interval

    decoder: str | None = None
    hwaccel_name: str | None = None
    if vendor and codec:
        decoder = _GPU_DECODER_MAP.get(vendor, {}).get(codec)
        hwaccel_name = _VENDOR_HWACCEL_MAP.get(vendor)
    # Legacy path: vendor=None -> NVIDIA CUVID (tests call _decode_chunk
    # directly without vendor, so keep the historical behavior).
    if decoder is None and vendor is None:
        decoder = _CUVID_CODEC_MAP.get(codec or "")
        if decoder:
            hwaccel_name = "cuda"

    needs_hwdownload = (
        hwaccel_name is not None and hwaccel_name in _HWACCELS_NEED_HWDOWNLOAD
    )
    if decoder and hwaccel_name:
        hwaccel_args = ["-hwaccel", hwaccel_name]
        if needs_hwdownload:
            # d3d11va / qsv は decode 結果を GPU surface に置くため、
            # filter graph に渡す前に system memory への download が
            # 必要 (#553 / #550)。`-hwaccel_output_format` で surface
            # format を明示 (d3d11va -> d3d11, qsv -> qsv) し、後段の
            # hwdownload filter と整合させる。
            surface_fmt = _HWACCEL_OUTPUT_FORMAT_MAP.get(hwaccel_name, hwaccel_name)
            hwaccel_args += ["-hwaccel_output_format", surface_fmt]
        hwaccel_args += ["-c:v", decoder]
    else:
        hwaccel_args = ["-hwaccel", "auto"]

    vf_prefix = "hwdownload,format=nv12," if needs_hwdownload else ""

    cmd = [
        find_ffmpeg(),
        *hwaccel_args,
        "-ss",
        str(chunk_start),
        "-t",
        str(chunk_duration),
        "-i",
        str(video_path),
        "-vf",
        f"{vf_prefix}fps={fps_value},scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=max(300, int(chunk_duration * 2)),
        )
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise VideoProcessingError(
            f"GPU decode timed out for chunk {chunk_start}"
        ) from e

    stderr_text = proc.stderr.decode(errors="replace")

    if proc.returncode != 0:
        raise VideoProcessingError(
            "GPU decode failed",
            context={
                "command": " ".join(str(c) for c in cmd),
                "return_code": proc.returncode,
                "chunk": f"{chunk_start:.1f}-{chunk_end:.1f}",
                "stderr_tail": stderr_text[-2000:],
            },
        )

    # Parse raw frames from stdout
    data = proc.stdout
    results: dict[float, float] = {}
    frame_idx = 0
    offset = 0

    if chunk_timestamps is not None:
        # Caller supplied pre-computed global grid timestamps -- map by
        # index so CPU and GPU agree on dict keys (#392).  Stop when the
        # pre-assigned list runs out even if ffmpeg emitted extra frames
        # (can happen with keyframe-aligned -ss seeks near chunk_end).
        while offset + _FRAME_SIZE <= len(data) and frame_idx < len(chunk_timestamps):
            frame = np.frombuffer(data[offset : offset + _FRAME_SIZE], dtype=np.uint8)
            results[chunk_timestamps[frame_idx]] = float(frame.mean())
            offset += _FRAME_SIZE
            frame_idx += 1
    else:
        # Legacy path: derive timestamp from chunk_start + k*interval.
        # Kept for existing callers / unit tests that invoke _decode_chunk
        # directly without a pre-computed list.  New code should always
        # pass chunk_timestamps from scan_gpu.
        while offset + _FRAME_SIZE <= len(data):
            frame = np.frombuffer(data[offset : offset + _FRAME_SIZE], dtype=np.uint8)
            brightness = float(frame.mean())
            timestamp = round(chunk_start + frame_idx * sample_interval, 4)
            if timestamp < chunk_end:
                results[timestamp] = brightness
            offset += _FRAME_SIZE
            frame_idx += 1

    return results, stderr_text
