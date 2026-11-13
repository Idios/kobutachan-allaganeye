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
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg

__all__ = ["build_frame_command", "iter_gray_frames"]


def build_frame_command(
    video: Path,
    *,
    fps: float,
    start: float = 0.0,
    duration: float | None = None,
) -> list[str]:
    """Build the ffmpeg argv for raw gray frame streaming.

    Kept separate from :func:`iter_gray_frames` so the argument order can be
    asserted without launching a process.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if start < 0:
        raise ValueError(f"start must be >= 0, got {start}")
    if duration is not None and duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    command = [
        find_ffmpeg(),
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(video),
    ]
    if duration is not None:
        command += ["-t", f"{duration:.3f}"]
    command += [
        "-vf",
        f"fps={fps}",
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
    frame_size: tuple[int, int],
    start: float = 0.0,
    duration: float | None = None,
) -> Iterator[tuple[float, np.ndarray]]:
    """Yield ``(timestamp, grayscale frame)`` pairs at ``fps`` frames per second.

    ``frame_size`` is ``(width, height)``; the caller gets it from
    :func:`allaganeye.video.probe.probe_video` because the raw stream carries no
    header. Timestamps are ``start + index / fps`` (the ``fps`` filter resamples
    onto a fixed grid).

    stderr goes to a temp file rather than a pipe: reading stdout and stderr
    concurrently needs a thread, and a filled stderr pipe would deadlock the
    decoder. The FFmpeg process is killed when the generator is closed early
    (Ctrl+C, ``break``), so a cancelled scan does not leave a decoder running.
    """
    width, height = frame_size
    if width <= 0 or height <= 0:
        raise ValueError(f"frame_size must be positive, got {frame_size}")
    command = build_frame_command(video, fps=fps, start=start, duration=duration)
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
