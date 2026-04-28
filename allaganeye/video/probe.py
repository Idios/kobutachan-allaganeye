"""Video metadata extraction using ffprobe."""

import json
import subprocess
from pathlib import Path
from typing import TypedDict

from allaganeye.exceptions import (
    STDERR_TAIL_BYTES,
    InputFileError,
    VideoProcessingError,
)
from allaganeye.ffmpeg_path import find_ffprobe


class ProbeResult(TypedDict):
    """Metadata returned by probe_video()."""

    duration: float
    width: int
    height: int
    fps: float
    codec: str
    audio_codec: str | None


def _parse_frame_rate(rate_str: str) -> float:
    """Parse a frame rate string like '30/1' or '60000/1001'. Returns 0.0 on failure."""
    try:
        num, den = rate_str.split("/")
        fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError, AttributeError):
        return 0.0
    return fps if fps > 0 else 0.0


def probe_video(video_path: Path) -> ProbeResult:
    """Extract video metadata using ffprobe.

    Returns dict with keys: duration, width, height, fps, codec, audio_codec.
    """
    try:
        result = subprocess.run(
            [
                find_ffprobe(),
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffprobe not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise VideoProcessingError(
            f"ffprobe timed out after 30s for {video_path}"
        ) from e
    except subprocess.CalledProcessError as e:
        stderr_text = e.stderr if isinstance(e.stderr, str) else ""
        raise VideoProcessingError(
            "ffprobe failed",
            context={
                "command": " ".join(str(c) for c in e.cmd) if e.cmd else "",
                "return_code": e.returncode,
                "stderr_tail": stderr_text[-STDERR_TAIL_BYTES:] if stderr_text else "",
            },
        ) from e

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise VideoProcessingError("ffprobe returned invalid JSON") from e

    video_stream = None
    audio_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        elif stream.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = stream

    if video_stream is None:
        raise InputFileError("No video stream found in file")

    # Parse FPS from r_frame_rate (e.g., "30/1" or "60000/1001"),
    # falling back to avg_frame_rate if r_frame_rate is unusable.
    fps = _parse_frame_rate(video_stream.get("r_frame_rate", ""))
    if fps <= 0:
        fps = _parse_frame_rate(video_stream.get("avg_frame_rate", ""))
    if fps <= 0:
        raise VideoProcessingError(
            "Cannot determine video frame rate from ffprobe output"
        )

    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise VideoProcessingError(
            "Cannot determine video duration from ffprobe output"
        )

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    if width <= 0 or height <= 0:
        raise VideoProcessingError(
            "Cannot determine video resolution from ffprobe output"
        )

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "codec": video_stream.get("codec_name", "unknown"),
        "audio_codec": audio_stream.get("codec_name", "unknown")
        if audio_stream
        else None,
    }
