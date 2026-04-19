"""Mono PCM audio extraction from video files via ffmpeg."""

import subprocess
from pathlib import Path

import numpy as np

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import find_ffmpeg


def extract_pcm(
    video_path: Path,
    *,
    sample_rate: int = 22050,
    start: float | None = None,
    duration: float | None = None,
) -> np.ndarray:
    """Extract mono PCM as float32 in [-1, 1] from a video file.

    Uses ffmpeg to decode and resample the audio stream.  Returns the
    full audio when ``start``/``duration`` are not provided.

    Raises ``VideoProcessingError`` when ffmpeg is missing, times out, or
    returns a non-zero status.  Empty output (e.g. video with no audio
    track) raises the same error.
    """
    cmd = [find_ffmpeg(), "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(video_path)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += [
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=1800)
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise VideoProcessingError(
            f"ffmpeg audio extraction timed out for {video_path}"
        ) from e

    if proc.returncode != 0:
        stderr_text = proc.stderr.decode(errors="replace")
        raise VideoProcessingError(
            f"ffmpeg audio extraction failed for {video_path}",
            context={
                "command": " ".join(str(c) for c in cmd),
                "return_code": proc.returncode,
                "stderr_tail": stderr_text[-2000:],
            },
        )

    if len(proc.stdout) == 0:
        raise VideoProcessingError(
            f"No audio data extracted from {video_path} (video may have no audio track)"
        )

    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
