"""Sequential grayscale frame reader for L4 signal extraction (#1106).

``allaganeye indicators`` needs frames on a controlled time grid (0.1 s) from an
arbitrary recording. The detector has its own chunked decoder tuned for
brightness statistics; this module is the simple sequential counterpart: one
long-lived ffmpeg process streaming raw gray frames.

ffmpeg argument order matters and is easy to get wrong:

* ``-ss`` **before** ``-i`` is the accurate input seek. ffmpeg decodes from the
  preceding keyframe and discards up to the requested timestamp, so the first
  emitted frame really is the one at ``start``.
* ``-t`` **after** ``-i`` is the output duration. Placing it before ``-i`` turns
  it into an *input* option, which shifts every output timestamp (measured: a
  0.4 s input ``-t`` moved frames by roughly a GOP). Every reported timestamp
  would then be silently wrong, so the order is pinned by
  ``tests/test_indicators_frames.py::test_command_puts_t_after_i``.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.system_info import probe_gpu_vendors
from allaganeye.video.gpu_detector import (
    _GPU_DECODER_MAP,
    _HWACCEL_OUTPUT_FORMAT_MAP,
    _HWACCELS_NEED_HWDOWNLOAD,
    _VENDOR_HWACCEL_MAP,
    _VENDOR_PREFERENCE,
)

__all__ = [
    "HwaccelSpec",
    "build_frame_command",
    "iter_gray_frames",
    "resolve_hwaccel",
]


@dataclass(frozen=True)
class HwaccelSpec:
    """ハードウェアデコードの ffmpeg 引数 (#1151)。

    ``args`` は ``-i`` より前に置く (`-hwaccel` / ``-hwaccel_output_format`` /
    ``-c:v <decoder>``)。``filter_prefix`` は GPU surface のまま出てくる vendor
    (d3d11va / qsv) で filter の先頭に必要な ``hwdownload,format=nv12,``。
    """

    vendor: str
    args: tuple[str, ...]
    filter_prefix: str = ""


def resolve_hwaccel(codec: str | None) -> HwaccelSpec | None:
    """利用可能な GPU から hwaccel 引数を組む。使えなければ ``None`` (CPU)。

    vendor 選択と codec -> decoder の対応は `gpu_detector` の表をそのまま使う。
    未知の codec / GPU なしのときは **CPU に倒す** (推測で decoder を渡すと
    ffmpeg が即死し、そのチャンクだけ欠損する)。
    """
    if not codec:
        return None
    vendors = probe_gpu_vendors()
    vendor = next(
        (
            candidate
            for candidate in _VENDOR_PREFERENCE
            if candidate in vendors and candidate in _VENDOR_HWACCEL_MAP
        ),
        None,
    )
    if vendor is None:
        return None
    decoder = _GPU_DECODER_MAP.get(vendor, {}).get(codec)
    if decoder is None:
        return None
    hwaccel = _VENDOR_HWACCEL_MAP[vendor]
    args: list[str] = ["-hwaccel", hwaccel]
    output_format = _HWACCEL_OUTPUT_FORMAT_MAP.get(hwaccel)
    if output_format is not None:
        args += ["-hwaccel_output_format", output_format]
    args += ["-c:v", decoder]
    prefix = "hwdownload,format=nv12," if hwaccel in _HWACCELS_NEED_HWDOWNLOAD else ""
    return HwaccelSpec(vendor=vendor, args=tuple(args), filter_prefix=prefix)


def build_frame_command(
    video: Path,
    *,
    fps: float,
    start: float = 0.0,
    duration: float | None = None,
    crop: tuple[int, int, int, int] | None = None,
    hwaccel: HwaccelSpec | None = None,
) -> list[str]:
    """Build the ffmpeg argv for raw gray frame streaming.

    Kept separate from :func:`iter_gray_frames` so the argument order can be
    asserted without launching a process.

    ``crop`` is ``(x, y, width, height)`` in source pixels (#1140). The scan only
    looks at the text band, so cropping inside ffmpeg keeps ~2 MB per frame from
    crossing the pipe. The filter order is ``format=gray`` first and ``crop``
    second: cropping the decoded yuv420p plane would round odd x/y to the chroma
    grid, while the gray (luma) plane is exact.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if start < 0:
        raise ValueError(f"start must be >= 0, got {start}")
    if duration is not None and duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    filters: list[str] = []
    if hwaccel is not None and hwaccel.filter_prefix:
        filters.append(hwaccel.filter_prefix.rstrip(","))
    if crop is not None:
        x, y, width, height = crop
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise ValueError(f"crop must be (x >= 0, y >= 0, w > 0, h > 0), got {crop}")
        filters.append("format=gray")
        filters.append(f"crop={width}:{height}:{x}:{y}")
    filters.append(f"fps={fps}")
    command = [
        find_ffmpeg(),
        "-v",
        "error",
    ]
    if hwaccel is not None:
        command += list(hwaccel.args)
    command += [
        "-ss",
        f"{start:.3f}",
        "-i",
        str(video),
    ]
    if duration is not None:
        command += ["-t", f"{duration:.3f}"]
    command += [
        "-vf",
        ",".join(filters),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    return command


def iter_gray_frames(
    video: Path,
    *,
    fps: float,
    frame_size: tuple[int, int] | None = None,
    start: float = 0.0,
    duration: float | None = None,
    crop: tuple[int, int, int, int] | None = None,
    hwaccel: HwaccelSpec | None = None,
) -> Iterator[tuple[float, np.ndarray]]:
    """Yield ``(timestamp, grayscale frame)`` pairs at ``fps`` frames per second.

    ``frame_size`` is ``(width, height)`` of the **emitted** frame; the caller
    gets it from :func:`allaganeye.video.probe.probe_video` because the raw
    stream carries no header. Timestamps are ``start + index / fps`` (the ``fps``
    filter resamples onto a fixed grid).

    When ``crop`` ``(x, y, w, h)`` is given the frames come out ``w x h`` (the
    text band) and ``frame_size`` may be omitted (#1140). Passing a
    ``frame_size`` that disagrees with the crop is rejected instead of silently
    reading the pipe at the wrong stride.

    stderr goes to a temp file rather than a pipe: reading stdout and stderr
    concurrently needs a thread, and a filled stderr pipe would deadlock the
    decoder. The FFmpeg process is killed when the generator is closed early
    (Ctrl+C, ``break``), so a cancelled scan does not leave a decoder running.
    """
    if crop is not None:
        crop_width, crop_height = crop[2], crop[3]
        if frame_size is not None and tuple(frame_size) != (crop_width, crop_height):
            raise ValueError(
                f"frame_size {frame_size} does not match the crop size "
                f"{(crop_width, crop_height)}"
            )
        width, height = crop_width, crop_height
    else:
        if frame_size is None:
            raise ValueError("frame_size is required when no crop is given")
        width, height = frame_size
    if width <= 0 or height <= 0:
        raise ValueError(f"frame_size must be positive, got {(width, height)}")
    command = build_frame_command(
        video, fps=fps, start=start, duration=duration, crop=crop, hwaccel=hwaccel
    )
    frame_bytes = width * height
    return_code = 0
    message = ""
    completed = False
    with tempfile.TemporaryFile() as error_log:
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=error_log
            )
        except OSError as e:
            # 壊れた ffmpeg / 実行権限なし / ALLAGANEYE_FFMPEG の誤指し。
            # ここを素通りさせると `OSError` が CLI の error ハンドラをすり抜ける。
            raise VideoProcessingError(
                f"cannot launch ffmpeg ({command[0]}) for {video}: {e}"
            ) from e
        assert process.stdout is not None
        index = 0
        try:
            while True:
                buffer = process.stdout.read(frame_bytes)
                if not buffer:
                    # stdout の EOF は「既に reap 済み」を意味しない (ffmpeg は終了処理で
                    # 先に stdout を閉じる)。ここでは kill せず wait で回収する。
                    completed = True
                    break
                if len(buffer) < frame_bytes:
                    # 中途半端な最終フレーム = デコーダが frame の途中で死んだ。
                    # 捨てて成功扱いにすると不完全なデータで判定を続けることになる。
                    raise VideoProcessingError(
                        f"truncated frame after {index} frames from {video}: "
                        f"expected {frame_bytes} bytes, got {len(buffer)}"
                    )
                frame = np.frombuffer(buffer, np.uint8).reshape(height, width)
                yield start + index / fps, frame
                index += 1
        finally:
            process.stdout.close()
            if not completed and process.poll() is None:
                # 早期 close (Ctrl+C / break) だけ kill する。
                process.kill()
            return_code = process.wait()
            error_log.seek(0)
            message = error_log.read().decode("utf-8", errors="replace").strip()
    # ここに来るのはループが正常終了した場合だけ (例外 / 早期 close は飛ばす)。
    if return_code != 0:
        raise VideoProcessingError(
            f"ffmpeg failed while decoding {video} (exit {return_code}, {index} frames): "
            f"{message}"
        )
