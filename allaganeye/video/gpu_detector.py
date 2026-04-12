"""GPU-accelerated match detection using chunked parallel ffmpeg decode."""

import logging
import os
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.video.detector import _FRAME_SIZE, _SAMPLE_HEIGHT, _SAMPLE_WIDTH

logger = logging.getLogger(__name__)

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
    fallback_checked = False

    cuvid_decoder = _CUVID_CODEC_MAP.get(codec or "")

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
                chunk_results, stderr_text = future.result()
            except VideoProcessingError:
                gpu_failed = True
                pool.shutdown(wait=False, cancel_futures=True)
                break

            # Check GPU usage from the first completed chunk
            if not fallback_checked:
                fallback_checked = True
                _check_gpu_usage(stderr_text, codec, cuvid_decoder)

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


def _check_gpu_usage(
    stderr_text: str, codec: str | None, cuvid_decoder: str | None
) -> None:
    """Log GPU decode status based on ffmpeg stderr output."""
    if cuvid_decoder and cuvid_decoder in stderr_text:
        logger.info("GPU decode active: %s", cuvid_decoder)
    elif "hwaccel" in stderr_text.lower() or "cuda" in stderr_text.lower():
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
) -> tuple[dict[float, float], str]:
    """Decode a single chunk using GPU-accelerated ffmpeg.

    Returns ``(results_dict, stderr_text)`` so the caller can inspect
    GPU usage from the first completed chunk.
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

    stderr_text = proc.stderr.decode(errors="replace")

    if proc.returncode != 0:
        raise VideoProcessingError(f"GPU decode failed: {stderr_text[-500:]}")

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

    return results, stderr_text
