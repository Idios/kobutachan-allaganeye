"""GPU-accelerated match detection using chunked parallel ffmpeg decode."""

import os
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.video.detector import _FRAME_SIZE, _SAMPLE_HEIGHT, _SAMPLE_WIDTH

_CUVID_CODEC_MAP: dict[str, str] = {
    "h264": "h264_cuvid",
    "hevc": "hevc_cuvid",
    "av1": "av1_cuvid",
    "vp9": "vp9_cuvid",
    "vp8": "vp8_cuvid",
    "mpeg1video": "mpeg1_cuvid",
    "mpeg2video": "mpeg2_cuvid",
    "mpeg4": "mpeg4_cuvid",
}


def scan_gpu(
    video_path: Path,
    duration: float,
    sample_interval: float,
    blackout_threshold: float,
    progress_callback: Callable[[int, int, int], None] | None = None,
    codec: str | None = None,
) -> dict[float, float]:
    """GPU mode: chunked parallel decode with cuvid hardware decoder.

    Splits the video timeline into chunks and runs one long-lived ffmpeg
    process per chunk with GPU-accelerated decoding.  Each process uses
    ``fps=1/{interval}`` to output one frame per interval, which is read
    from stdout and analyzed for brightness.

    Returns dict mapping timestamp → brightness, same as CPU mode.

    Raises VideoProcessingError if GPU decode fails for all chunks.
    """
    num_chunks = min(os.cpu_count() or 4, 16)
    chunk_duration = duration / num_chunks

    chunks: list[tuple[float, float]] = []
    for i in range(num_chunks):
        chunk_start = i * chunk_duration
        chunk_end = min((i + 1) * chunk_duration, duration)
        chunks.append((chunk_start, chunk_end))

    total_expected = int(duration / sample_interval)
    results: dict[float, float] = {}
    blackout_count = 0
    completed = 0
    gpu_failed = False

    with ThreadPoolExecutor(max_workers=num_chunks) as pool:
        futures = {
            pool.submit(
                _decode_chunk,
                video_path,
                chunk_start,
                chunk_end,
                sample_interval,
                codec,
            ): (chunk_start, chunk_end)
            for chunk_start, chunk_end in chunks
        }
        for future in as_completed(futures):
            chunk_start, chunk_end = futures[future]
            try:
                chunk_results = future.result()
            except VideoProcessingError:
                gpu_failed = True
                pool.shutdown(wait=False, cancel_futures=True)
                break
            for t, brightness in chunk_results.items():
                results[t] = brightness
                completed += 1
                if brightness < blackout_threshold:
                    blackout_count += 1
                if progress_callback is not None:
                    progress_callback(completed, total_expected, blackout_count)

    if gpu_failed:
        raise VideoProcessingError("GPU decode failed, falling back to CPU")

    return results


def _decode_chunk(
    video_path: Path,
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    codec: str | None = None,
) -> dict[float, float]:
    """Decode a single chunk using GPU-accelerated ffmpeg.

    Runs one ffmpeg process that decodes from chunk_start to chunk_end,
    outputting one frame per sample_interval via the fps filter.

    When *codec* maps to a known cuvid decoder, uses explicit
    ``-hwaccel cuda -c:v <codec>_cuvid`` for reliable GPU decode.
    Falls back to ``-hwaccel auto`` for unknown codecs.
    """
    chunk_duration = chunk_end - chunk_start
    fps_value = 1.0 / sample_interval

    cuvid_decoder = _CUVID_CODEC_MAP.get(codec or "")
    if cuvid_decoder:
        hwaccel_args = ["-hwaccel", "cuda", "-c:v", cuvid_decoder]
    else:
        hwaccel_args = ["-hwaccel", "auto"]

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
        f"fps={fps_value},scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
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

    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace")[-500:]
        raise VideoProcessingError(f"GPU decode failed: {stderr}")

    # Parse raw frames from stdout
    data = proc.stdout
    results: dict[float, float] = {}
    frame_idx = 0
    offset = 0

    while offset + _FRAME_SIZE <= len(data):
        frame = np.frombuffer(data[offset : offset + _FRAME_SIZE], dtype=np.uint8)
        brightness = float(frame.mean())
        timestamp = round(chunk_start + frame_idx * sample_interval, 4)
        if timestamp < chunk_end:
            results[timestamp] = brightness
        offset += _FRAME_SIZE
        frame_idx += 1

    return results
